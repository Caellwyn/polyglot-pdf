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
import { reviewCounts } from './reviewStatus';
import type { FormField } from '../types/schema';
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

describe('percentage rounding parity with the backend mirror', () => {
  // The backend stamps a percentage and the open editor computes its own with
  // reviewCounts; if the two round differently, ONE saved kit prints two
  // numbers. Python's round() ties-to-even vs JS Math.round's ties-up made
  // exactly that (1 of 8: backend 12%, editor 13%). Same ratios the backend
  // test parametrizes, so a change to EITHER implementation breaks a test.
  //
  // Drives the REAL reviewCounts. The first version of this block asserted
  // `Math.round(...)` against a literal -- a tautology over a JS builtin that
  // could not fail however reviewCounts changed, leaving the client half of
  // the mirror unpinned while claiming to pin it (measured: swapping
  // reviewCounts' Math.round for Math.floor left all 1204 tests green; Opus
  // fresh-eyes round 3).
  const fields = (reviewed: number, total: number): FormField[] =>
    Array.from({ length: total }, (_, i) => ({
      id: `f${i}`, name: `f${i}`, type: 'text', spoken_name: `f${i}`,
      pdf_field_name: `F${i}[0]`,
      ...(i < reviewed ? { _review: { status: 'reviewed_correct' } } : {}),
    })) as unknown as FormField[];

  it.each([
    [1, 8, 13], [5, 8, 63], [3, 8, 38], [7, 8, 88], [1, 40, 3],
    [1, 3, 33], [2, 3, 67], [1, 1, 100], [0, 5, 0],
  ])('%i of %i -> %i%%', (reviewed, total, expected) => {
    const counts = reviewCounts(fields(reviewed, total), undefined);
    expect(counts.reviewed).toBe(reviewed);   // the fixture builds what it claims
    expect(counts.percentage).toBe(expected);
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
