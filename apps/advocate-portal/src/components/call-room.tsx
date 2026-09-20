'use client';

import { formatCallDuration, type CallAccess, type CallStatus } from '@legal-platform/shared';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { callClient, socketUrl } from '@/lib/call-client';
import { CallEngine, type CallPhase } from '@/lib/call-engine';
import { formatDateTime } from '@/lib/format';

type Stage = 'lobby' | 'joining' | 'in-call' | 'ended';

const MAX_RECONNECTS = 5;

const PHASE_TEXT: Record<CallPhase, string> = {
  connecting: 'Connecting…',
  waiting: 'Waiting for the other person to join…',
  negotiating: 'Setting up the call…',
  connected: 'Connected',
  reconnecting: 'Connection interrupted — trying to reconnect…',
};

function unavailableText(access: CallAccess): string {
  switch (access.reason) {
    case 'too_early':
      return `The room opens at ${formatDateTime(access.opens_at)}, shortly before the booked time.`;
    case 'window_passed':
      return 'The booked time for this consultation has passed. Ask to reschedule.';
    case 'unpaid':
      return 'The consultation room opens once the matter has been paid.';
    case 'ended':
      return 'This matter has ended, so its call room is closed.';
    case 'not_a_consultation':
      return 'Only consultations have a call room.';
    default:
      return 'This consultation can’t be joined right now.';
  }
}

function mediaErrorText(err: unknown): string {
  const name = err instanceof DOMException ? err.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Allow microphone (and camera) access in your browser, then try again.';
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return 'No microphone or camera was found. Connect one and try again, or join audio-only.';
  }
  if (name === 'NotReadableError') {
    return 'Your microphone or camera is being used by another app. Close it and try again.';
  }
  return 'Could not start your microphone or camera.';
}

const controlCls = (on: boolean) =>
  `rounded-full px-4 py-2 text-sm font-medium ${
    on ? 'bg-slate-700 text-white hover:bg-slate-600' : 'bg-slate-200 text-slate-800 hover:bg-slate-300'
  }`;

/**
 * The consultation room: lobby -> join with audio/video -> call -> ended.
 *
 * Audio and video are WebRTC, browser to browser; this component only orchestrates the media
 * devices, the signaling engine and the controls.
 */
export function CallRoom({
  matterId,
  token,
  backHref,
  counterpart,
}: {
  matterId: string;
  token: string;
  backHref: string;
  /** "Adv. Kavya Rao" / "the client" - for the waiting message. */
  counterpart: string;
}) {
  const [stage, setStage] = useState<Stage>('lobby');
  const [phase, setPhase] = useState<CallPhase>('connecting');
  const [status, setStatus] = useState<CallStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [endMessage, setEndMessage] = useState('');
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [hasCamera, setHasCamera] = useState(false);
  const [remote, setRemote] = useState<MediaStream | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const localVideo = useRef<HTMLVideoElement>(null);
  const remoteVideo = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const engine = useRef<CallEngine | null>(null);
  const attempts = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectedAt = useRef<number | null>(null);

  // ---- lobby: is the room open? -----------------------------------------------------------
  useEffect(() => {
    if (stage !== 'lobby') return;
    let cancelled = false;
    const load = () =>
      callClient
        .status(matterId, token)
        .then((s) => !cancelled && setStatus(s))
        .catch(() => undefined);
    void load();
    const timer = setInterval(load, 10_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [stage, matterId, token]);

  // ---- attach media to the <video> elements ------------------------------------------------
  useEffect(() => {
    if (stage === 'in-call' && localVideo.current) localVideo.current.srcObject = stream.current;
  }, [stage]);
  useEffect(() => {
    if (remoteVideo.current) remoteVideo.current.srcObject = remote;
  }, [remote, stage]);

  // ---- the call timer ----------------------------------------------------------------------
  useEffect(() => {
    if (phase !== 'connected' || stage !== 'in-call') return;
    if (connectedAt.current === null) connectedAt.current = Date.now();
    const timer = setInterval(() => {
      if (connectedAt.current !== null) setElapsed((Date.now() - connectedAt.current) / 1000);
    }, 1000);
    return () => clearInterval(timer);
  }, [phase, stage]);

  const stopMedia = useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  const finish = useCallback(
    (message: string) => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
      engine.current = null;
      stopMedia();
      setRemote(null);
      setEndMessage(message);
      setStage('ended');
    },
    [stopMedia],
  );

  /** Opens a signaling connection with a fresh ticket (the first time, and after a drop). */
  const connect = useCallback(async (): Promise<void> => {
    const media = stream.current;
    if (!media) return;
    const session = await callClient.session(matterId, token);
    const next = new CallEngine(session, socketUrl(session), media, {
      onPhase: (p) => {
        setPhase(p);
        if (p === 'connected') attempts.current = 0;
      },
      onRemoteStream: setRemote,
      onNotice: setNotice,
      onEnd: (end) => {
        engine.current = null;
        if (end.retry && attempts.current < MAX_RECONNECTS) {
          attempts.current += 1;
          setPhase('reconnecting');
          retryTimer.current = setTimeout(
            () => void reconnect(),
            1000 * 2 ** (attempts.current - 1),
          );
        } else {
          finish(end.message);
        }
      },
    });
    engine.current = next;
    next.start();

    async function reconnect() {
      try {
        await connect();
      } catch (err) {
        finish(err instanceof ApiRequestError ? err.message : 'The connection was lost.');
      }
    }
  }, [matterId, token, finish]);

  const join = useCallback(
    async (withVideo: boolean) => {
      setError(null);
      setNotice(null);
      setStage('joining');
      try {
        stream.current = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: withVideo ? { width: { ideal: 1280 }, height: { ideal: 720 } } : false,
        });
      } catch (err) {
        setError(mediaErrorText(err));
        setStage('lobby');
        return;
      }
      setHasCamera(stream.current.getVideoTracks().length > 0);
      setMicOn(true);
      setCamOn(true);
      connectedAt.current = null;
      setElapsed(0);
      attempts.current = 0;
      try {
        await connect();
        setStage('in-call');
      } catch (err) {
        stopMedia();
        setError(err instanceof ApiRequestError ? err.message : 'Could not open the room.');
        setStage('lobby');
      }
    },
    [connect, stopMedia],
  );

  const hangUp = () => {
    engine.current?.hangUp();
    finish('You left the consultation.');
  };

  const toggle = (kind: 'audio' | 'video') => {
    const tracks = kind === 'audio' ? stream.current?.getAudioTracks() : stream.current?.getVideoTracks();
    const next = kind === 'audio' ? !micOn : !camOn;
    tracks?.forEach((t) => (t.enabled = next));
    if (kind === 'audio') setMicOn(next);
    else setCamOn(next);
  };

  // Leaving the page hangs up and releases the camera and microphone.
  useEffect(
    () => () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
      engine.current?.hangUp();
      stream.current?.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  // ---- render ------------------------------------------------------------------------------
  if (stage === 'ended') {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 text-center" data-call-stage="ended">
        <h2 className="text-lg font-semibold">Consultation ended</h2>
        <p className="mt-1 text-sm text-slate-600">{endMessage}</p>
        <Link
          href={backHref}
          className="mt-4 inline-block rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
        >
          Back to the matter
        </Link>
      </section>
    );
  }

  if (stage === 'lobby' || stage === 'joining') {
    const access = status?.access;
    const open = access?.allowed === true;
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6" data-call-stage={stage}>
        <h2 className="text-lg font-semibold">Consultation room</h2>
        {!access ? (
          <p className="mt-2 text-sm text-slate-500">Checking the room…</p>
        ) : open ? (
          <>
            <p className="mt-2 text-sm text-slate-600">
              {status && status.present.length > 0
                ? `${counterpart} is already in the room.`
                : `You’ll be the first in the room; ${counterpart} is notified when you join.`}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={stage === 'joining'}
                onClick={() => void join(true)}
                className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
              >
                {stage === 'joining' ? 'Joining…' : 'Join with video'}
              </button>
              <button
                type="button"
                disabled={stage === 'joining'}
                onClick={() => void join(false)}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                Join audio only
              </button>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Your browser will ask to use your microphone and camera. The call goes directly
              between you and {counterpart}, and it isn’t recorded.
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-slate-600">{unavailableText(access)}</p>
        )}
        {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
        <Link href={backHref} className="mt-4 inline-block text-xs text-slate-500 hover:text-slate-900">
          ← Back to the matter
        </Link>
      </section>
    );
  }

  return (
    <section
      className="flex flex-col gap-3"
      data-call-stage="in-call"
      data-call-phase={phase}
    >
      <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-slate-900">
        <video
          ref={remoteVideo}
          autoPlay
          playsInline
          className="h-full w-full object-cover"
          data-testid="remote-video"
        />
        {(!remote || remote.getVideoTracks().length === 0) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-300">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-700 text-2xl">
              {counterpart.replace(/^(Adv\.|the)\s+/i, '').charAt(0).toUpperCase() || '·'}
            </div>
            <p className="text-sm" aria-live="polite">
              {phase === 'connected'
                ? 'Audio call in progress'
                : phase === 'waiting'
                  ? `Waiting for ${counterpart} to join…`
                  : PHASE_TEXT[phase]}
            </p>
          </div>
        )}
        <video
          ref={localVideo}
          autoPlay
          playsInline
          muted
          className={`absolute bottom-3 right-3 h-24 w-36 -scale-x-100 rounded-lg border border-slate-600 bg-slate-800 object-cover ${
            hasCamera && camOn ? '' : 'opacity-40'
          }`}
          data-testid="local-video"
        />
        <div className="absolute left-3 top-3 rounded-full bg-black/50 px-3 py-1 text-xs text-white">
          {phase === 'connected' ? formatCallDuration(elapsed) : PHASE_TEXT[phase]}
        </div>
      </div>

      {notice && <p className="text-sm text-amber-700">{notice}</p>}

      <div className="flex items-center justify-center gap-2">
        <button
          type="button"
          onClick={() => toggle('audio')}
          aria-pressed={micOn}
          aria-label={micOn ? 'Mute microphone' : 'Unmute microphone'}
          className={controlCls(micOn)}
        >
          {micOn ? 'Mute' : 'Unmute'}
        </button>
        {hasCamera && (
          <button
            type="button"
            onClick={() => toggle('video')}
            aria-pressed={camOn}
            aria-label={camOn ? 'Turn camera off' : 'Turn camera on'}
            className={controlCls(camOn)}
          >
            {camOn ? 'Camera off' : 'Camera on'}
          </button>
        )}
        <button
          type="button"
          onClick={hangUp}
          className="rounded-full bg-rose-600 px-5 py-2 text-sm font-medium text-white hover:bg-rose-700"
        >
          Leave
        </button>
      </div>
    </section>
  );
}
