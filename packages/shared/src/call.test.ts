import { describe, expect, it } from 'vitest';
import {
  CALL_CLOSE,
  describeCallClose,
  formatCallDuration,
  isCallSignal,
  parseCallServerMessage,
} from './call';

const frame = (value: unknown) => JSON.stringify(value);

describe('parseCallServerMessage', () => {
  it('reads every message the server sends', () => {
    expect(
      parseCallServerMessage(frame({ type: 'joined', role: 'ADVOCATE', peer_present: false })),
    ).toEqual({ type: 'joined', role: 'ADVOCATE', peer_present: false });
    expect(parseCallServerMessage(frame({ type: 'peer-joined' }))).toEqual({ type: 'peer-joined' });
    expect(parseCallServerMessage(frame({ type: 'peer-left' }))).toEqual({ type: 'peer-left' });
    expect(parseCallServerMessage(frame({ type: 'pong' }))).toEqual({ type: 'pong' });
    expect(parseCallServerMessage(frame({ type: 'ended', reason: 'time_limit' }))).toEqual({
      type: 'ended',
      reason: 'time_limit',
    });
    expect(parseCallServerMessage(frame({ type: 'error', code: 'peer_absent' }))).toEqual({
      type: 'error',
      code: 'peer_absent',
    });
  });

  it('relays offers, answers and candidates', () => {
    const offer = { kind: 'offer', sdp: 'v=0' };
    expect(parseCallServerMessage(frame({ type: 'signal', data: offer }))).toEqual({
      type: 'signal',
      data: offer,
    });
    const candidate = { kind: 'candidate', candidate: { candidate: 'candidate:1 1 udp 1 1.2.3.4 5 typ host' } };
    expect(parseCallServerMessage(frame({ type: 'signal', data: candidate }))?.type).toBe('signal');
    // The end-of-candidates marker is a null candidate.
    expect(
      parseCallServerMessage(frame({ type: 'signal', data: { kind: 'candidate', candidate: null } })),
    ).not.toBeNull();
  });

  it.each([
    ['not json', 'nope'],
    ['a bare string', '"joined"'],
    ['an array', '[1]'],
    ['an unknown type', frame({ type: 'launch' })],
    ['joined without a role', frame({ type: 'joined', peer_present: true })],
    ['joined with a bad role', frame({ type: 'joined', role: 'ADMIN', peer_present: true })],
    ['joined with a non-boolean', frame({ type: 'joined', role: 'CONSUMER', peer_present: 'yes' })],
    ['a signal with no data', frame({ type: 'signal' })],
    ['a signal with an unknown kind', frame({ type: 'signal', data: { kind: 'rollback' } })],
    ['an offer with no sdp', frame({ type: 'signal', data: { kind: 'offer' } })],
  ])('rejects %s', (_label, raw) => {
    expect(parseCallServerMessage(raw)).toBeNull();
  });

  it('tolerates a missing reason or code', () => {
    expect(parseCallServerMessage(frame({ type: 'ended' }))).toEqual({ type: 'ended', reason: 'ended' });
    expect(parseCallServerMessage(frame({ type: 'error' }))).toEqual({ type: 'error', code: 'error' });
  });
});

describe('isCallSignal', () => {
  it('accepts only well-formed signals', () => {
    expect(isCallSignal({ kind: 'answer', sdp: 'x' })).toBe(true);
    expect(isCallSignal({ kind: 'candidate', candidate: null })).toBe(true);
    expect(isCallSignal({ kind: 'candidate', candidate: { candidate: 5 } })).toBe(false);
    expect(isCallSignal(null)).toBe(false);
    expect(isCallSignal('offer')).toBe(false);
  });
});

describe('describeCallClose', () => {
  it('says what happened, and whether reconnecting can help', () => {
    expect(describeCallClose(CALL_CLOSE.REPLACED)).toMatchObject({ retry: false });
    expect(describeCallClose(CALL_CLOSE.REPLACED).message).toMatch(/another tab/);
    expect(describeCallClose(CALL_CLOSE.NOT_ALLOWED).retry).toBe(false);
    expect(describeCallClose(CALL_CLOSE.IDLE_OR_TIME_LIMIT).message).toMatch(/window has ended/);
    expect(describeCallClose(1000).retry).toBe(false);
  });

  it('treats a dropped connection as worth retrying', () => {
    expect(describeCallClose(1006).retry).toBe(true);
    expect(describeCallClose(1001).retry).toBe(true);
    expect(describeCallClose(CALL_CLOSE.BAD_TICKET).retry).toBe(true); // a fresh ticket may work
  });
});

describe('formatCallDuration', () => {
  it('formats minutes and hours', () => {
    expect(formatCallDuration(0)).toBe('0:00');
    expect(formatCallDuration(5)).toBe('0:05');
    expect(formatCallDuration(75)).toBe('1:15');
    expect(formatCallDuration(3725)).toBe('1:02:05');
  });

  it('never goes negative or shows fractions', () => {
    expect(formatCallDuration(-3)).toBe('0:00');
    expect(formatCallDuration(59.9)).toBe('0:59');
  });
});
