/**
 * The card's "may I show this number?" rule (sprint-18 C4, bd polyglot-pdf-g687).
 *
 * The rule exists because the alternative -- falling back to a client-side
 * re-scan when no stamp is available -- is exactly the two-sources-of-truth bug
 * bd polyglot-pdf-q3rm fixed: an open kit and a refreshed card showing two
 * different percentages for the same work. So an untrustworthy stamp must
 * yield a HINT, never a number.
 */
import { describe, it, expect } from 'vitest';
import { readStamp, readStampFromMetadata, stampHint } from './readinessStamp';
import type { ReadinessStamp } from './remoteKitStore';

const stamp = (over: Partial<ReadinessStamp> = {}): ReadinessStamp => ({
  reviewed: 3, toReview: 1, total: 4, errors: 0, percent: 75,
  ready: false, verified: true, schemaSha1: 'abc123', ...over,
});

describe('readStamp', () => {
  it('accepts a verified stamp', () => {
    const r = readStamp(stamp());
    expect(r.kind).toBe('ok');
    expect(r.kind === 'ok' && r.stamp.percent).toBe(75);
  });

  it('treats absent / null / undefined alike', () => {
    expect(readStamp(undefined)).toEqual({ kind: 'hint', reason: 'absent' });
    expect(readStamp(null)).toEqual({ kind: 'hint', reason: 'absent' });
  });

  it('withholds the number from an UNVERIFIED stamp even at 100%', () => {
    // The counts may look complete, but they were computed with no usable lint
    // report -- presenting them as checked is the confident-then-409 lie.
    const r = readStamp(stamp({ verified: false, percent: 100, ready: true }));
    expect(r).toEqual({ kind: 'hint', reason: 'unverified' });
  });

  it('flags a stamp measured against a DIFFERENT schema as stale', () => {
    expect(readStamp(stamp(), 'zzz999')).toEqual({ kind: 'hint', reason: 'stale' });
    expect(readStamp(stamp(), 'abc123').kind).toBe('ok');
  });

  it('does not fire the staleness clause when the caller has no schema', () => {
    // A catalogue LISTING holds no schema (not re-reading every kit is the
    // whole point of the stamp), so it cannot detect an out-of-band edit --
    // and must not pretend to. undefined means "no comparison available".
    expect(readStamp(stamp(), undefined).kind).toBe('ok');
  });

  it('treats a malformed stamp as absent, NOT as 0%', () => {
    // Rendering 0% for an unreadable record would assert "nothing is
    // reviewed", which is a claim we cannot make.
    expect(readStamp({ percent: 'x' } as unknown as ReadinessStamp))
      .toEqual({ kind: 'hint', reason: 'absent' });
    expect(readStamp({ ...stamp(), total: undefined } as unknown as ReadinessStamp))
      .toEqual({ kind: 'hint', reason: 'absent' });
  });
});

describe('readStampFromMetadata (local mode: the backend-written snake_case)', () => {
  const raw = {
    reviewed: 3, toReview: 1, total: 4, errors: 0, percent: 75,
    ready: false, verified: true, schema_sha1: 'abc123',
    stamped_at: '2026-08-05T00:00:00+00:00',
  };

  it('parses the stored shape into the shared camelCase stamp', () => {
    expect(readStampFromMetadata(raw)).toEqual({
      reviewed: 3, toReview: 1, total: 4, errors: 0, percent: 75,
      ready: false, verified: true, schemaSha1: 'abc123',
      stampedAt: '2026-08-05T00:00:00+00:00',
    });
  });

  it('round-trips through readStamp so local and hosted read one rule', () => {
    const parsed = readStampFromMetadata(raw);
    expect(readStamp(parsed).kind).toBe('ok');
  });

  it('returns null for anything malformed or missing', () => {
    expect(readStampFromMetadata(undefined)).toBeNull();
    expect(readStampFromMetadata('nope')).toBeNull();
    expect(readStampFromMetadata({})).toBeNull();
    // A missing hash cannot be scoped to a schema -> not a usable stamp.
    expect(readStampFromMetadata({ ...raw, schema_sha1: undefined })).toBeNull();
    // Non-finite numbers would render as "NaN%".
    expect(readStampFromMetadata({ ...raw, percent: Number.NaN })).toBeNull();
  });

  it('treats an ABSENT verified flag as unverified, not verified', () => {
    // An older or hand-written stamp made no claim that its checks ran; the
    // safe reading of "no claim" is the hint.
    const parsed = readStampFromMetadata({ ...raw, verified: undefined });
    expect(parsed?.verified).toBe(false);
    expect(readStamp(parsed)).toEqual({ kind: 'hint', reason: 'unverified' });
  });
});

describe('stampHint', () => {
  it('explains each gap in plain language, naming no internals', () => {
    for (const reason of ['absent', 'unverified', 'stale'] as const) {
      const text = stampHint(reason);
      expect(text.length).toBeGreaterThan(0);
      // The reader is a contractor, not an engineer: no jargon leaks.
      expect(text.toLowerCase()).not.toContain('lint');
      expect(text.toLowerCase()).not.toContain('stamp');
      expect(text.toLowerCase()).not.toContain('sha');
    }
  });
});
