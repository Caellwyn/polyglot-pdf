/**
 * How a catalogue card reads a kit's readiness stamp (sprint-18 C4, bd
 * polyglot-pdf-g687).
 *
 * The backend records what publish_readiness computed into metadata.json at
 * save/publish; the card renders THAT rather than re-deriving a percentage of
 * its own. This module owns the one question the card has to answer -- "may I
 * show this number?" -- so both catalogues (RemoteCatalogue, FormCatalogue)
 * answer it identically.
 *
 * The rule (maintainer decision, 2026-08-05): a stamp that is ABSENT, STALE
 * (measured a different schema than the one on disk), or UNVERIFIED (computed
 * with no usable lint report) yields the VERIFY HINT -- never a confident
 * percentage, and deliberately never a fall-back re-scan. A fall-back would
 * reintroduce exactly the two-sources-of-truth bug this bead exists to end
 * (see bd polyglot-pdf-q3rm, where an open kit and a refreshed card showed two
 * different numbers). Accepted consequence: every kit shows the hint until it
 * is next saved, because no kit carried a stamp before this shipped.
 */
import type { ReadinessStamp } from './remoteKitStore';

/** Why a card cannot show a confident percentage. */
export type StampGap = 'absent' | 'unverified' | 'stale';

export type StampReading =
  | { kind: 'ok'; stamp: ReadinessStamp }
  | { kind: 'hint'; reason: StampGap };

/**
 * Whether a stamp may be presented as this kit's review progress.
 *
 * `currentSchemaSha1` is the hash of the schema actually in hand, when the
 * caller has one. A catalogue LISTING has no schema loaded (that is the whole
 * point of the stamp -- not re-reading every kit), so it passes undefined and
 * the staleness clause simply does not fire: a listing cannot detect an
 * out-of-band edit, and pretending otherwise would be its own lie. The clause
 * exists for callers that DO hold the schema (the open kit).
 */
export function readStamp(
  stamp: ReadinessStamp | null | undefined,
  currentSchemaSha1?: string,
): StampReading {
  if (!stamp || typeof stamp !== 'object') return { kind: 'hint', reason: 'absent' };
  if (typeof stamp.percent !== 'number' || typeof stamp.total !== 'number') {
    // A malformed stamp is absent, not zero: showing 0% for an unreadable
    // record would read as "nothing reviewed", which is a claim we cannot make.
    return { kind: 'hint', reason: 'absent' };
  }
  if (!stamp.verified) return { kind: 'hint', reason: 'unverified' };
  if (currentSchemaSha1 !== undefined && stamp.schemaSha1 !== currentSchemaSha1) {
    return { kind: 'hint', reason: 'stale' };
  }
  return { kind: 'ok', stamp };
}

/**
 * Parse a stamp straight out of a local metadata.json, where it is stored in
 * the backend's snake_case shape (the hosted /kits route already converts to
 * camelCase for the wire). Returns null for anything malformed, so a
 * hand-edited or truncated stamp yields the verify hint rather than a bogus
 * number -- LOCAL mode reads the same file the backend wrote, which is what
 * lets both catalogues share one definition of progress.
 */
export function readStampFromMetadata(
  raw: unknown,
): ReadinessStamp | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null;
  const reviewed = num(r.reviewed);
  const toReview = num(r.toReview);
  const total = num(r.total);
  const errors = num(r.errors);
  const percent = num(r.percent);
  const sha = typeof r.schema_sha1 === 'string' ? r.schema_sha1 : null;
  if (reviewed === null || toReview === null || total === null
      || errors === null || percent === null || sha === null) {
    return null;
  }
  return {
    reviewed, toReview, total, errors, percent,
    ready: r.ready === true,
    // Absent `verified` is treated as UNVERIFIED, not verified: an older or
    // hand-written stamp has made no claim that its checks ran, and the safe
    // reading of "no claim" is the hint, never a confident percentage.
    verified: r.verified === true,
    schemaSha1: sha,
    stampedAt: typeof r.stamped_at === 'string' ? r.stamped_at : null,
  };
}

/** The card's one-line explanation for each gap -- plain language, no jargon:
 * a contractor reading this has no idea what a "stamp" or a "lint report" is,
 * only whether the number in front of them can be trusted. */
export const STAMP_HINTS: Record<StampGap, string> = {
  absent: 'Review progress not measured yet -- open and save this form to check it.',
  unverified: 'Progress not fully checked -- some checks could not run.',
  stale: 'This form changed since it was last checked -- open and save it to re-check.',
};

export function stampHint(reason: StampGap): string {
  return STAMP_HINTS[reason];
}
