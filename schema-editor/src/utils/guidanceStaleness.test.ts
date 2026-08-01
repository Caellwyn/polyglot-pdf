/**
 * Guidance staleness gate -- editor half (bd polyglot-pdf-anim).
 * The BACKEND decides staleness (it wrote the hash); these tests pin how the
 * editor consumes that finding and gates review-correct on a human ack.
 */
import { describe, it, expect } from 'vitest';
import {
  GUIDANCE_STALE_RULE, currentIdentity, isAcknowledged,
  needsAckFieldIds, needsGuidanceAck, staleFieldIds,
} from './guidanceStaleness';
import {
  effectiveStatus, withGuidanceAck, withReviewNote, withReviewStatus,
} from './reviewStatus';
import type { FormField } from '../types/schema';
import type { LintFinding } from './remoteKitStore';

const BAKED = 'abc123identity';

function field(over: Partial<FormField> = {}): FormField {
  return {
    id: 'phone', name: 'Phone', spoken_name: 'phone number', type: 'text',
    section_id: 's1', pdf_field_name: 'P[0]',
    help: { instructions: 'Enter your phone number.' },
    ...over,
  } as unknown as FormField;
}

const staleFinding: LintFinding = {
  severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
  path: `fields (id=phone).help[identity:${BAKED}]`, message: 'identity changed',
  field_id: 'phone',
};

describe('staleFieldIds', () => {
  it('collects ids only from the staleness rule', () => {
    const ids = staleFieldIds([
      staleFinding,
      { severity: 'WARNING', rule: 'help-details-oversize',
        path: 'fields (id=other).help', message: 'x', field_id: 'other' },
    ]);
    expect([...ids]).toEqual(['phone']);
  });

  it('is empty for no findings / undefined', () => {
    expect(staleFieldIds(undefined).size).toBe(0);
    expect(staleFieldIds([]).size).toBe(0);
  });
});

describe('the acknowledgment gate', () => {
  it('a flagged field needs an ack; an un-flagged one never does', () => {
    const ids = staleFieldIds([staleFinding]);
    expect(needsGuidanceAck(field(), ids, BAKED)).toBe(true);
    expect(needsGuidanceAck(field({ id: 'other' } as Partial<FormField>),
      ids, BAKED)).toBe(false);
  });

  it('an UNPARSEABLE current identity fails open, never deadlocks (Opus round)', () => {
    // A flagged field whose finding path yields no identity has nothing an
    // ack could pin to -- withGuidanceAck without an identity is a no-op --
    // so gating it would trap the field behind a checkbox that records
    // nothing. Fail open: not gated. (Unreachable from today's backend; the
    // path format is contract-pinned server-side.)
    const ids = staleFieldIds([staleFinding]);
    expect(needsGuidanceAck(field(), ids, undefined)).toBe(false);
  });

  it('an ack for the CURRENT identity satisfies the gate', () => {
    const acked = withGuidanceAck(field(), BAKED, true);
    expect(isAcknowledged(acked, BAKED)).toBe(true);
    expect(needsGuidanceAck(acked, staleFieldIds([staleFinding]), BAKED)).toBe(false);
  });

  it('an ack for a SUPERSEDED identity does NOT (not a permanent waiver)', () => {
    const acked = withGuidanceAck(field(), 'old-identity', true);
    expect(isAcknowledged(acked, BAKED)).toBe(false);
    expect(needsGuidanceAck(acked, staleFieldIds([staleFinding]), BAKED)).toBe(true);
  });
});

describe('effectiveStatus integration (green means a human said so, about THIS content)', () => {
  it('demotes an explicit reviewed_correct while guidance is un-acknowledged', () => {
    const reviewed = { ...field(), _review: { status: 'reviewed_correct' } } as FormField;
    expect(effectiveStatus(reviewed, false, undefined, false)).toBe('complete');
    expect(effectiveStatus(reviewed, false, undefined, true)).toBe('review');
  });

  it('restores complete once the ack is recorded', () => {
    const acked = withGuidanceAck(
      { ...field(), _review: { status: 'reviewed_correct' } } as FormField,
      BAKED, true);
    expect(acked._review?.guidance_ack_sha1).toBe(BAKED);
    expect(acked._review?.status).toBe('reviewed_correct');   // preserved
    expect(effectiveStatus(acked, false, undefined, false)).toBe('complete');
  });

  it('a lint ERROR still outranks the guidance gate (red wins)', () => {
    expect(effectiveStatus(field(), true, undefined, true)).toBe('error');
  });
});

describe('withGuidanceAck serialization', () => {
  it('clearing drops the key, and the whole _review when nothing else remains', () => {
    const acked = withGuidanceAck(field(), BAKED, true);
    const cleared = withGuidanceAck(acked, BAKED, false);
    expect(cleared._review).toBeUndefined();
  });

  it('clearing preserves a real review status/note', () => {
    const withNote = withGuidanceAck(
      { ...field(), _review: { status: 'needs_followup', note: 'check me' } } as FormField,
      BAKED, true);
    const cleared = withGuidanceAck(withNote, BAKED, false);
    expect(cleared._review).toEqual({ status: 'needs_followup', note: 'check me' });
  });
});

describe('the ack pins to CURRENT content, never the frozen bake (fresh-eyes finding 1)', () => {
  const finding = (identity: string): LintFinding => ({
    severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
    path: `fields (id=phone).help[identity:${identity}]`,
    message: 'changed', field_id: 'phone',
  });

  it('reads the current identity out of the finding message', () => {
    expect(currentIdentity([finding('deadbeef')], 'phone')).toBe('deadbeef');
    expect(currentIdentity([finding('deadbeef')], 'other')).toBeUndefined();
    expect(currentIdentity([], 'phone')).toBeUndefined();
  });

  it('a SECOND drift after an ack re-raises the gate (no permanent waiver)', () => {
    // drift 1: backend reports identity H2; the human acknowledges THAT.
    const acked = withGuidanceAck(field(), 'H2', true);
    expect(needsGuidanceAck(acked, staleFieldIds([finding('H2')]), 'H2'))
      .toBe(false);                                   // satisfied for H2
    // drift 2: the human edits again -- the backend now reports H3. The BAKED
    // hash never moved, so pinning to it would have silently kept the ack
    // valid. Pinning to the CURRENT identity correctly re-raises.
    expect(needsGuidanceAck(acked, staleFieldIds([finding('H3')]), 'H3'))
      .toBe(true);
  });

  it('re-acknowledging the new content satisfies it again', () => {
    const reAcked = withGuidanceAck(withGuidanceAck(field(), 'H2', true), 'H3', true);
    expect(needsGuidanceAck(reAcked, staleFieldIds([finding('H3')]), 'H3')).toBe(false);
  });
});

describe('currentIdentity parses the TRAILING token (bd polyglot-pdf-g5vj)', () => {
  // The backend builds the path by interpolating the field id AHEAD of the
  // identity token (schema_lint.py::_check_guidance_identity_drift), so an
  // UNANCHORED regex returns the id's own embedded hex instead of the real
  // current hash. That mis-parse pins the ack to a string that can never
  // change again, making one click a PERMANENT WAIVER for the field -- the
  // exact hole current-identity pinning was built to close.
  const REAL = '1d4f89c8aa';
  const DECOY = 'deadbeef';
  const WEIRD_ID = `weird[identity:${DECOY}]id`;

  // Built exactly as the backend does, so this test breaks if the path shape
  // on either side drifts.
  const path = `fields (id=${WEIRD_ID}).help[identity:${REAL}]`;
  const finding: LintFinding = {
    severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
    path, message: 'identity changed', field_id: WEIRD_ID,
  };

  it('returns the real trailing hash, not an id-embedded decoy', () => {
    expect(currentIdentity([finding], WEIRD_ID)).toBe(REAL);
    expect(currentIdentity([finding], WEIRD_ID)).not.toBe(DECOY);
  });

  it('so the ack is NOT a permanent waiver for such a field', () => {
    // Ack the real current identity; a later drift moves it and re-gates.
    const acked = withGuidanceAck(
      field({ id: WEIRD_ID } as Partial<FormField>), REAL, true);
    const ids = staleFieldIds([finding]);
    expect(needsGuidanceAck(acked, ids, currentIdentity([finding], WEIRD_ID)))
      .toBe(false);
    const next: LintFinding = {
      ...finding,
      path: `fields (id=${WEIRD_ID}).help[identity:99aa00bb]`,
    };
    expect(needsGuidanceAck(acked, staleFieldIds([next]),
      currentIdentity([next], WEIRD_ID))).toBe(true);
  });

  it('an ordinary slugified id is unaffected', () => {
    const plain: LintFinding = {
      severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
      path: `fields (id=phone).help[identity:${REAL}]`,
      message: 'x', field_id: 'phone',
    };
    expect(currentIdentity([plain], 'phone')).toBe(REAL);
  });
});

describe('staleFieldIds uses the centralized field_id (bd h76m.11)', () => {
  it('reads field_id, not a re-parse of path', () => {
    const odd: LintFinding = {
      severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
      path: 'some/other/shape', message: 'x', field_id: 'weird)id',
    };
    expect([...staleFieldIds([odd])]).toEqual(['weird)id']);
  });
  it('ignores a finding with a null field_id', () => {
    expect(staleFieldIds([{ severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
      path: 'p', message: 'm', field_id: null }]).size).toBe(0);
  });
});

describe('the ack survives the other _review writers (fresh-eyes, closeout round 2)', () => {
  // withReviewStatus / withReviewNote used to rebuild _review from scratch,
  // silently DROPPING guidance_ack_sha1 on the ordinary flow: tick the ack
  // box, then mark reviewed_correct (or type a note) -- the gate re-ambered
  // with no visible cause. The fourth instance of the same conceptual bug
  // (a layer not carrying the ack token when state moves through it).
  it('a status change keeps the ack', () => {
    const acked = withGuidanceAck(field(), BAKED, true);
    const signed = withReviewStatus(acked, 'reviewed_correct');
    expect(signed._review?.guidance_ack_sha1).toBe(BAKED);
    expect(needsGuidanceAck(signed, staleFieldIds([staleFinding]), BAKED)).toBe(false);
    // ...including a reset to unreviewed: withdrawing the sign-off does not
    // withdraw the separate "the guidance still reads right" assertion.
    expect(withReviewStatus(signed, 'unreviewed')._review?.guidance_ack_sha1)
      .toBe(BAKED);
  });

  it('a note edit keeps the ack; clearing the note keeps it too', () => {
    const acked = withGuidanceAck(field(), BAKED, true);
    const noted = withReviewNote(acked, 'double-checked the booklet');
    expect(noted._review?.guidance_ack_sha1).toBe(BAKED);
    expect(withReviewNote(noted, '')._review?.guidance_ack_sha1).toBe(BAKED);
  });

  it('a neutral field with no ack still serializes clean (key dropped)', () => {
    expect(withReviewStatus(field(), 'unreviewed')._review).toBeUndefined();
    expect(withReviewNote(field(), '')._review).toBeUndefined();
  });
});

describe('needsAckFieldIds (the completion counters aggregation)', () => {
  // Identities here MUST be hex: currentIdentity's production regex only
  // matches [identity:<hex>], so a non-hex literal silently parses to
  // undefined and every assertion passes through the fail-open branch
  // instead of the comparison it claims to pin (Opus round 2: the first
  // version of this block was exactly that -- vacuously green).
  const hexFinding = (id: string, identity: string): LintFinding => ({
    severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
    path: `fields (id=${id}).help[identity:${identity}]`,
    message: 'identity changed', field_id: id,
  });

  it('collects stale fields lacking an ack for their CURRENT identity', () => {
    const unacked = field();
    const acked = withGuidanceAck(
      field({ id: 'other' } as Partial<FormField>), 'beef22', true);
    const findings = [hexFinding('phone', 'abc123'),
                      hexFinding('other', 'beef22')];
    // `phone` is stale and un-acked -> in. `other` is stale but acked for its
    // current identity -> out. The set is what getCompletionStats consumes.
    expect([...needsAckFieldIds([unacked, acked], findings)]).toEqual(['phone']);
  });

  it('an ack for a SUPERSEDED identity stays IN the set (no permanent waiver)', () => {
    const staleAcked = withGuidanceAck(field(), 'aaa000', true);
    expect([...needsAckFieldIds([staleAcked], [hexFinding('phone', 'abc123')])])
      .toEqual(['phone']);
  });

  it('an UNPARSEABLE identity fails open in the counters too (row parity)', () => {
    // Same fail-open as needsGuidanceAck: the % figure and the row icons
    // must tell the same story even on a malformed finding path.
    const reviewed = field({
      _review: { status: 'reviewed_correct' },
    } as Partial<FormField>);
    const unparseable: LintFinding = {
      severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
      path: 'fields (id=phone).help', message: 'x', field_id: 'phone',
    };
    expect(needsAckFieldIds([reviewed], [unparseable]).size).toBe(0);
  });

  it('is empty with no stale findings, and never throws on undefined input', () => {
    expect(needsAckFieldIds(undefined, [staleFinding]).size).toBe(0);
    expect(needsAckFieldIds([field()], []).size).toBe(0);
    expect(needsAckFieldIds([field()], undefined).size).toBe(0);
  });
});
