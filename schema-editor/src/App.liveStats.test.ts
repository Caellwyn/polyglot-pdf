/**
 * liveStats honours the guidance-ack gate (bd anim, Opus round 4).
 *
 * The catalogue bar's live % is computed by App's liveStats; its second
 * argument (the lint findings) is what lets reviewCounts exclude a
 * reviewed_correct field whose guidance drifted un-acknowledged. This pins
 * the FUNCTION including that wiring; the two JSX call sites are pinned by
 * the TYPE -- `lintFindings` is a required parameter precisely so the
 * gate-blind `liveStats(schema)` revert fails tsc (Opus round 5) -- and the
 * ValidationPanel + FieldList component tests cover the same gate on their
 * surfaces.
 */
import { describe, it, expect } from 'vitest';
import { liveStats } from './App';
import type { FormSchema } from './types/schema';
import type { LintFinding } from './utils/remoteKitStore';

const schemaWith = (review: object): FormSchema => ({
  source: 'pdf',
  form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
  parts: [],
  sections: [{ id: 's1', label: 'S', order: 1, fields: ['gated'] }],
  fields: [{
    id: 'gated', name: 'G', type: 'text', spoken_name: 'g',
    pdf_field_name: 'G[0]', section_id: 's1',
    help: { instructions: 'x' }, _review: review,
  }],
} as unknown as FormSchema);

const staleFinding: LintFinding = {
  severity: 'WARNING', rule: 'guidance-identity-stale',
  path: 'fields (id=gated).help[identity:abc123]', field_id: 'gated',
  message: 'guidance may be out of date',
};

describe('liveStats honours the guidance-ack gate (bd anim)', () => {
  it('a gated reviewed_correct field drops out of the live %', () => {
    const gated = schemaWith({ status: 'reviewed_correct' });
    expect(liveStats(gated, undefined).percent).toBe(100);       // gate-blind without findings
    expect(liveStats(gated, [staleFinding]).percent).toBe(0);    // gated once they arrive
  });

  it('an ack for the current identity restores the %', () => {
    const acked = schemaWith({
      status: 'reviewed_correct', guidance_ack_sha1: 'abc123',
    });
    expect(liveStats(acked, [staleFinding]).percent).toBe(100);
  });
});
