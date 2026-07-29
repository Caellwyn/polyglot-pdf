/**
 * Guidance staleness gate -- editor half (bd polyglot-pdf-anim).
 * The BACKEND decides staleness (it wrote the hash); these tests pin how the
 * editor consumes that finding and gates review-correct on a human ack.
 */
import { describe, it, expect } from 'vitest';
import {
  GUIDANCE_STALE_RULE, currentIdentity, isAcknowledged,
  needsGuidanceAck, staleFieldIds,
} from './guidanceStaleness';
import { effectiveStatus, withGuidanceAck } from './reviewStatus';
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
