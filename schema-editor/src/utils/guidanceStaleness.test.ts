/**
 * Guidance staleness gate -- editor half (bd polyglot-pdf-anim).
 * The BACKEND decides staleness (it wrote the hash); these tests pin how the
 * editor consumes that finding and gates review-correct on a human ack.
 */
import { describe, it, expect } from 'vitest';
import {
  GUIDANCE_STALE_RULE, bakedIdentity, isAcknowledged, needsGuidanceAck,
  staleFieldIds,
} from './guidanceStaleness';
import { effectiveStatus, withGuidanceAck } from './reviewStatus';
import type { FormField, FormSchema } from '../types/schema';
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

function schemaWith(f: FormField, identity?: string): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T', version: '1', language: 'en' },
    parts: [], sections: [{ id: 's1', label: 'S', order: 1, fields: [f.id] }],
    fields: [f],
    _bakeoff: { authoring: { instructions_enrich: {
      provenance: { [f.id]: { source: 'llm-verified',
        ...(identity ? { identity_sha1: identity } : {}) } },
      flags: [] } } },
  } as unknown as FormSchema;
}

const staleFinding: LintFinding = {
  severity: 'WARNING', rule: GUIDANCE_STALE_RULE,
  path: 'fields (id=phone).help', message: 'identity changed', field_id: 'phone',
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

describe('bakedIdentity', () => {
  it('reads the recorded hash out of provenance', () => {
    expect(bakedIdentity(schemaWith(field(), BAKED), 'phone')).toBe(BAKED);
  });
  it('is undefined when unrecorded or the schema shape is junk', () => {
    expect(bakedIdentity(schemaWith(field()), 'phone')).toBeUndefined();
    expect(bakedIdentity({} as FormSchema, 'phone')).toBeUndefined();
    expect(bakedIdentity(
      { _bakeoff: 'nope' } as unknown as FormSchema, 'phone')).toBeUndefined();
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
