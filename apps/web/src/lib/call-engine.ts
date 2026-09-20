import {
  describeCallClose,
  parseCallServerMessage,
  type CallClientMessage,
  type CallSession,
  type CallSignal,
} from '@legal-platform/shared';

/** Where a call is, from the person's point of view. */
export type CallPhase = 'connecting' | 'waiting' | 'negotiating' | 'connected' | 'reconnecting';

export interface CallEnd {
  message: string;
  /** Whether a fresh ticket and a new connection could get the person back in. */
  retry: boolean;
}

export interface CallEngineEvents {
  onPhase: (phase: CallPhase) => void;
  onRemoteStream: (stream: MediaStream | null) => void;
  onEnd: (end: CallEnd) => void;
  onNotice: (message: string) => void;
}

const PING_MS = 25_000;

/**
 * One consultation connection: the signaling WebSocket plus the WebRTC peer connection.
 *
 * The server decides who makes the offer: whoever was in the room first is told `peer-joined`
 * when the other arrives, so there is never a clash of two simultaneous offers. Audio and video
 * go browser to browser (or through the TURN relay, encrypted end to end) - the socket only
 * carries the handshake.
 *
 * Muting or switching the camera off is done by the caller with `track.enabled`, which needs no
 * renegotiation.
 */
export class CallEngine {
  private ws: WebSocket | null = null;
  private pc: RTCPeerConnection | null = null;
  private pending: RTCIceCandidateInit[] = [];
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private finished = false;
  private initiator = false;

  constructor(
    private readonly session: CallSession,
    private readonly url: string,
    private readonly localStream: MediaStream,
    private readonly events: CallEngineEvents,
  ) {}

  start(): void {
    this.events.onPhase('connecting');
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.pingTimer = setInterval(() => this.send({ type: 'ping' }), PING_MS);
    };
    ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') void this.onMessage(event.data);
    };
    ws.onclose = (event: CloseEvent) => {
      if (this.finished) return;
      this.teardown();
      this.events.onEnd(describeCallClose(event.code));
    };
  }

  /** The person hung up. */
  hangUp(): void {
    if (this.finished) return;
    this.send({ type: 'bye' });
    this.teardown();
  }

  /** For debugging and tests: the live peer connection, if any. */
  peerConnection(): RTCPeerConnection | null {
    return this.pc;
  }

  // ---- signaling ---------------------------------------------------------------------------

  private async onMessage(raw: string): Promise<void> {
    const message = parseCallServerMessage(raw);
    if (!message || this.finished) return;
    try {
      switch (message.type) {
        case 'joined':
          this.events.onPhase(message.peer_present ? 'negotiating' : 'waiting');
          break;
        case 'peer-joined':
          // We were here first: start from a clean connection and make the offer.
          this.initiator = true;
          this.closePeer();
          await this.makeOffer(false);
          break;
        case 'peer-left':
          this.closePeer();
          this.events.onRemoteStream(null);
          this.events.onPhase('waiting');
          break;
        case 'signal':
          await this.onSignal(message.data);
          break;
        case 'ended':
          this.teardown();
          this.events.onEnd({ message: 'The consultation window has ended.', retry: false });
          break;
        case 'error':
          if (message.code !== 'peer_absent') this.events.onNotice('A call error occurred.');
          break;
        case 'pong':
          break;
      }
    } catch {
      this.events.onNotice('Something went wrong while setting up the call.');
    }
  }

  private async onSignal(signal: CallSignal): Promise<void> {
    if (signal.kind === 'offer') {
      const pc = this.ensurePeer();
      await pc.setRemoteDescription({ type: 'offer', sdp: signal.sdp });
      await this.flushCandidates(pc);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      this.send({
        type: 'signal',
        data: { kind: 'answer', sdp: pc.localDescription?.sdp ?? answer.sdp ?? '' },
      });
    } else if (signal.kind === 'answer') {
      if (!this.pc) return;
      await this.pc.setRemoteDescription({ type: 'answer', sdp: signal.sdp });
      await this.flushCandidates(this.pc);
    } else if (signal.candidate) {
      const init: RTCIceCandidateInit = {
        candidate: signal.candidate.candidate,
        sdpMid: signal.candidate.sdpMid ?? null,
        sdpMLineIndex: signal.candidate.sdpMLineIndex ?? null,
        usernameFragment: signal.candidate.usernameFragment ?? null,
      };
      // Candidates can overtake the offer they belong to; hold them until it has been applied.
      if (this.pc?.remoteDescription) await this.addCandidate(this.pc, init);
      else this.pending.push(init);
    }
  }

  private async makeOffer(iceRestart: boolean): Promise<void> {
    const pc = this.ensurePeer();
    const offer = await pc.createOffer({ iceRestart });
    await pc.setLocalDescription(offer);
    this.send({
      type: 'signal',
      data: { kind: 'offer', sdp: pc.localDescription?.sdp ?? offer.sdp ?? '' },
    });
    this.events.onPhase('negotiating');
  }

  // ---- the peer connection -----------------------------------------------------------------

  private ensurePeer(): RTCPeerConnection {
    if (this.pc) return this.pc;
    const pc = new RTCPeerConnection({
      iceServers: this.session.ice_servers as RTCIceServer[],
      iceTransportPolicy: this.session.ice_transport_policy,
    });
    for (const track of this.localStream.getTracks()) pc.addTrack(track, this.localStream);
    pc.onicecandidate = (event) => {
      if (event.candidate) {
        const c = event.candidate;
        this.send({
          type: 'signal',
          data: {
            kind: 'candidate',
            candidate: {
              candidate: c.candidate,
              sdpMid: c.sdpMid,
              sdpMLineIndex: c.sdpMLineIndex,
              usernameFragment: c.usernameFragment,
            },
          },
        });
      }
    };
    pc.ontrack = (event) => {
      const [stream] = event.streams;
      if (stream) this.events.onRemoteStream(stream);
    };
    pc.onconnectionstatechange = () => this.onConnectionState(pc);
    this.pc = pc;
    return pc;
  }

  private onConnectionState(pc: RTCPeerConnection): void {
    if (pc !== this.pc || this.finished) return;
    switch (pc.connectionState) {
      case 'connected':
        this.events.onPhase('connected');
        break;
      case 'disconnected':
        this.events.onPhase('reconnecting');
        break;
      case 'failed':
        this.events.onPhase('reconnecting');
        // Only the side that makes offers restarts ICE, so the two never do it at once.
        if (this.initiator) void this.makeOffer(true).catch(() => undefined);
        break;
      default:
        break;
    }
  }

  private async flushCandidates(pc: RTCPeerConnection): Promise<void> {
    const queued = this.pending;
    this.pending = [];
    for (const init of queued) await this.addCandidate(pc, init);
  }

  private async addCandidate(pc: RTCPeerConnection, init: RTCIceCandidateInit): Promise<void> {
    try {
      await pc.addIceCandidate(init);
    } catch {
      // A candidate for a connection that has since been replaced; safe to drop.
    }
  }

  private closePeer(): void {
    if (this.pc) {
      this.pc.onicecandidate = null;
      this.pc.ontrack = null;
      this.pc.onconnectionstatechange = null;
      this.pc.close();
      this.pc = null;
    }
    this.pending = [];
  }

  private send(message: CallClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
  }

  private teardown(): void {
    this.finished = true;
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
    this.closePeer();
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) this.ws.close(1000);
    this.ws = null;
  }
}
