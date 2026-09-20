# 0015 - Voice and video consultations (WebRTC, no media server)

- Status: Accepted
- Date: 2026-09-20
- Deciders: Platform team

## Context

Phase 8 shipped consultations as a *booking*: pay, get scheduled, message, close - but the
consultation itself had to happen somewhere else (ADR 0010 listed voice/video as not built, because it
needs real-time infrastructure and a provider choice). For a platform meant to connect people with
advocates, "a video call with your advocate" is the product, so this adds it - on the standing rule of
free services only.

## Decisions

### 1. WebRTC, browser to browser, with no media server

Audio and video flow directly between the two participants (encrypted with DTLS-SRTP). The platform
runs only *signaling* - the small JSON handshake that lets the two browsers find each other.

- **Free**: no per-minute charge, no hosted video vendor. (Hosted providers - Twilio, Daily, LiveKit
  Cloud, Agora - are paid; a public Jitsi room is free but routes a private legal consultation through a
  third party's servers and branding.)
- **Private**: our servers never see, record or store the media. For a legal consultation that is a
  feature, and it sidesteps call-recording consent questions entirely. **Calls are not recorded.**
- **Scales trivially** for 1:1: no SFU, no transcoding.
- **Cost**: strictly one-to-one (a consultation is), no server-side recording, quality depends on the two
  connections, and some networks need a TURN relay (decision 5).

### 2. Signaling is a WebSocket in the API, authenticated by a one-minute ticket

`POST /matters/{id}/call/session` (normal Bearer auth) returns a **ticket** - a signed token valid for 60
seconds, for one matter and one user, usable **once** - and the ICE servers. The browser then opens
`WS /matters/{id}/call/ws?ticket=...`. Browsers can't set headers on a WebSocket, and putting the real
access token in a URL would leak it into proxy and server logs; a ticket is all the URL ever carries.

Defence in depth on the socket: the `Origin` header must be one of the app's own origins (a page on
another website can't open it); the ticket is checked and consumed, then **everything is re-checked
against the database at connection time** (the matter may have been cancelled, or the user suspended,
since the ticket was issued); messages are capped in size and rate; idle connections are dropped; the
socket closes at the end of the bookable window. The hub relays `signal` payloads *verbatim* to the other
participant and never parses SDP.

**Limit**: rooms live in the API process's memory, so both participants must reach the same instance.
Behind a load balancer use sticky routing on the matter id, or swap the hub for a Redis pub/sub relay
(the endpoint only uses `join / leave / relay`). Single-instance is fine for launch.

### 3. Who can call, and when (pure rules, `services/calls/rules.py`)

Only the two participants of a **paid CONSULTATION** matter that hasn't ended. Admins may see the room's
status but can never join a private consultation. If the advocate has scheduled it, the room opens 10
minutes before the booked time and closes 30 minutes after the booked length; a paid-but-unscheduled
consultation can be opened ad hoc by either side (the "on-demand" consultation of the FRD), capped at 3
hours. The first person in triggers a **"waiting in the room"** notification (in-app, plus a generic email)
to the other.

### 4. Room mechanics that avoid the classic WebRTC bugs

The *server* decides who makes the offer - whoever was in the room first is told `peer-joined` when the
other arrives - so two simultaneous offers ("glare") can't happen. One connection per user: reconnecting
from a refreshed page or a second tab replaces the old socket, and the peer is told `peer-left` then
`peer-joined` so they renegotiate cleanly. A dropped socket reconnects with a fresh ticket and exponential
backoff; a failed ICE connection restarts ICE from the offering side. Muting and turning the camera off
just toggle track `enabled`, so they never renegotiate.

### 5. ICE: free STUN by default, self-hosted TURN when needed

By default the browsers use Google's public STUN server, which sees connection metadata (never media). Some
networks (strict NATs, corporate firewalls) can't connect directly and need a **TURN relay**; coturn is free
to self-host (`infrastructure/deployment/coturn.conf.example`) but needs a machine with a public IP, so that is
a hosting choice for Phase 15. Credentials are minted per user from a shared secret (coturn's "REST API"
scheme: a username carrying its own expiry, a password that is its HMAC) - unit-tested against an independent
OpenSSL computation - so nothing is stored and a leaked credential expires by itself.

`WEBRTC_RELAY_ONLY=true` forces all media through TURN so the two parties never see each other's IP address.
If it's set without a TURN server the API refuses (`calls_misconfigured`) instead of silently exposing
addresses. Without it, the two participants' IP addresses are visible to each other, which is inherent to
peer-to-peer.

### 6. What is stored: call metadata, not media

`matter_calls` records who opened the room, when both people were connected, when it ended and why. That
answers "did the consultation happen, and for how long?" for the advocate (before closing the matter) and for
legal ops (when the two sides disagree). It also shows a no-show: a call nobody joined has no duration.

## Consequences

- Verified end to end: unit tests for the rules / ICE config / tickets / hub, integration tests for the REST and
  database side, real-WebSocket relay tests, and a live check with two browser tabs (client on `apps/web`,
  advocate on `apps/advocate-portal`) exchanging **real WebRTC audio + video** (640x360, `currentTime`
  advancing, both connected), mute / camera toggles, leave and rejoin with automatic renegotiation, the
  "waiting" notification and the recorded 214-second call. The browser had no camera, so the live check used a
  synthetic camera and microphone (canvas + oscillator); **it has not been tried on real devices, phones or
  across different networks** - do that on a staging site.
- `getUserMedia` needs a **secure context**: production must be served over HTTPS (localhost is exempt).
- **Not built**: recording, screen sharing, group calls, in-call chat (the matter's message thread is one click
  away), reminders before the booked time (needs a scheduler - Phase 15), and dial-in by phone.
- **Needs the owner / hosting**: a TURN server if the platform must work for people on restrictive networks or
  hide IP addresses (free coturn, but a public machine and open UDP ports), and sticky routing or Redis if the
  API runs on more than one instance.

## Alternatives considered

- **A media server (SFU) such as LiveKit / mediasoup / Janus**: needed for group calls and recording; heavy
  to run and unnecessary for 1:1.
- **Jitsi Meet embed**: free and quick, but the call leaves our platform and our identity checks, and a legal
  consultation would sit on a third party's servers.
- **Signaling by HTTP polling**: works across instances, but adds seconds to connection setup and constant
  load for the length of a call.
- **The access token in the WebSocket URL**: simplest, but leaks a long-lived credential into logs.
- **Server-side call recording**: valuable for disputes, but it needs consent, retention rules and secure
  storage - a legal decision, not an engineering default.
