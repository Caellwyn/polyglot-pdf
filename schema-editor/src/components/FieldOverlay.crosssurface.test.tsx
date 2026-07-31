/**
 * CROSS-SURFACE AGREEMENT (bd polyglot-pdf-l7u0).
 *
 * FieldOverlay's own docstring claims "the SAME effective status the FieldList
 * row shows, so a review sign-off agrees across surfaces" (bd u8t6). It did
 * not: the overlay called effectiveStatus with NO findings, so it ignored both
 * backend lint ERRORs (pre-existing, documented in its own comment) and the
 * guidance-acknowledgment gate (bd anim). Either omission lets the canvas paint
 * a field GREEN while the FieldList row for that SAME field renders AMBER.
 *
 * These tests render BOTH surfaces from ONE schema+findings fixture and assert
 * the colour bands agree, per the bead's exit criterion 1.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FieldOverlay } from './FieldOverlay';
import { FieldList } from './FieldList';
import { isReviewTargetFromFindings, statusFromFindings }
  from '../utils/reviewStatus';
import type { FormField, FormSchema } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

const IDENTITY = 'a1b2c3d4';

function field(over: Partial<FormField> = {}): FormField {
  return {
    id: 'phone', name: 'Phone', spoken_name: 'phone number', type: 'text',
    section_id: 's1', pdf_field_name: 'P[0]',
    help: { instructions: 'Enter your phone number.' },
    pdf_position: { page: 1, x: 100, y: 700, width: 150, height: 30 },
    // reviewed_correct: without a finding this field is GREEN on both
    // surfaces, which is what makes the disagreement visible below.
    _review: { status: 'reviewed_correct' },
    ...over,
  } as unknown as FormField;
}

function schemaOf(f: FormField): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1,
      version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 's1', label: 'Section 1', order: 1, fields: [f.id] }],
    fields: [f],
  } as unknown as FormSchema;
}

const staleFinding: LintFinding = {
  severity: 'WARNING', rule: 'guidance-identity-stale',
  path: `fields (id=phone).help[identity:${IDENTITY}]`,
  message: 'this field changed since its guidance was written',
  field_id: 'phone',
};

const errorFinding: LintFinding = {
  severity: 'ERROR', rule: 'field-unbacked',
  path: 'fields (id=phone)', message: 'no backing widget', field_id: 'phone',
};

/** The overlay's border colour band, read off the rendered element. */
function overlayBand(f: FormField, findings?: LintFinding[]): string {
  const { container, unmount } = render(
    <FieldOverlay field={f} pageHeight={792} scale={1} isSelected={false}
      lintFindings={findings} />,
  );
  const el = container.querySelector('.field-overlay') as HTMLElement;
  const border = el.style.border;
  unmount();
  if (border.includes('74, 222, 128')) return 'green';
  if (border.includes('250, 204, 21')) return 'yellow';
  if (border.includes('248, 113, 113')) return 'red';
  return `unknown(${border})`;
}

/** overlayBand, but with a document page count threaded in. */
function overlayBandWithPages(f: FormField, pageCount: number): string {
  const { container, unmount } = render(
    <FieldOverlay field={f} pageHeight={792} scale={1} isSelected={false}
      pageCount={pageCount} />,
  );
  const border = (container.querySelector('.field-overlay') as HTMLElement).style.border;
  unmount();
  if (border.includes('74, 222, 128')) return 'green';
  if (border.includes('250, 204, 21')) return 'yellow';
  if (border.includes('248, 113, 113')) return 'red';
  return `unknown(${border})`;
}

/**
 * The band the FieldList ROW actually renders, read off its status icon's
 * Tailwind colour class -- not re-derived from the helper, so this genuinely
 * compares two rendered surfaces rather than one function against itself.
 */
function listBand(f: FormField, findings?: LintFinding[]): string {
  const byField = new Map<string, LintFinding[]>();
  if (findings?.length) byField.set(f.id, findings);
  const { unmount } = render(
    <FieldList schema={schemaOf(f)} selectedFieldId={null}
      onSelectField={vi.fn()} lintFindingsByField={byField} />,
  );
  const icon = screen.getByTestId(`field-status-${f.id}`);
  const svg = icon.querySelector('svg') as SVGElement;
  const cls = svg.getAttribute('class') ?? '';
  unmount();
  if (cls.includes('text-green')) return 'green';
  if (cls.includes('text-yellow') || cls.includes('text-amber')) return 'yellow';
  if (cls.includes('text-red')) return 'red';
  return `unknown(${cls})`;
}

describe('FieldOverlay agrees with FieldList (bd polyglot-pdf-l7u0)', () => {
  it('a clean reviewed field is GREEN on both surfaces (the control)', () => {
    const f = field();
    expect(overlayBand(f)).toBe('green');
    expect(listBand(f)).toBe('green');
  });

  it('a field with a backend lint ERROR is RED on both, not green on canvas', () => {
    // The PRE-EXISTING omission: the overlay had no findings threaded in at
    // all, so a reviewed_correct field with a hard lint ERROR painted green on
    // the canvas while the row went red.
    const f = field();
    expect(listBand(f, [errorFinding])).toBe('red');
    expect(overlayBand(f, [errorFinding])).toBe('red');
    expect(overlayBand(f, [errorFinding])).toBe(listBand(f, [errorFinding]));
  });

  it('un-acknowledged stale guidance is AMBER on both, not green on canvas', () => {
    // The second omission (bd anim): reviewed_correct is demoted by the gate,
    // so the row ambers. The overlay must follow.
    const f = field();
    expect(listBand(f, [staleFinding])).toBe('yellow');
    expect(overlayBand(f, [staleFinding])).toBe('yellow');
  });

  it('once acknowledged, BOTH surfaces return to green together', () => {
    const acked = field({
      _review: { status: 'reviewed_correct', guidance_ack_sha1: IDENTITY },
    } as Partial<FormField>);
    expect(listBand(acked, [staleFinding])).toBe('green');
    expect(overlayBand(acked, [staleFinding])).toBe('green');
  });

  it('an ack pinning a SUPERSEDED identity keeps both amber', () => {
    const staleAck = field({
      _review: { status: 'reviewed_correct', guidance_ack_sha1: 'OLD-H2' },
    } as Partial<FormField>);
    expect(listBand(staleAck, [staleFinding])).toBe('yellow');
    expect(overlayBand(staleAck, [staleFinding])).toBe('yellow');
  });

  it('a lint ERROR outranks the guidance gate on the canvas too (red wins)', () => {
    const f = field();
    const both = [staleFinding, errorFinding];
    expect(listBand(f, both)).toBe('red');
    expect(overlayBand(f, both)).toBe('red');
  });

  it('threading pageCount cannot re-colour a SIGNED-OFF field (no side effect)', () => {
    // PDFViewer now passes pageCount={numPages}, which FieldOverlay never
    // received before. Fresh-eyes flagged this as a possible unintended
    // re-colouring. It is NOT: an out-of-range page feeds `needsReview`, not
    // `errors`, and per the g63j rule an explicit reviewed_correct sign-off
    // outranks automatic amber. So a signed-off field is green either way.
    // Pinned so the new prop's blast radius stays provably nil.
    const offDoc = field({          // reviewed_correct, page 9 of a 1-page doc
      pdf_position: { page: 9, x: 100, y: 700, width: 150, height: 30 },
    } as Partial<FormField>);
    expect(overlayBand(offDoc)).toBe('green');                    // no pageCount
    expect(overlayBandWithPages(offDoc, 1)).toBe('green');        // with pageCount
  });

  it('...but an UNREVIEWED out-of-range field is amber either way', () => {
    // The automatic band DOES govern an unreviewed field -- and it is already
    // amber without pageCount (unreviewed is always amber, bd g63j), so
    // threading the prop still changes no colour. This is what makes the new
    // prop safe rather than merely untested.
    const unreviewed = field({
      _review: undefined,
      pdf_position: { page: 9, x: 100, y: 700, width: 150, height: 30 },
    } as Partial<FormField>);
    expect(overlayBand(unreviewed)).toBe('yellow');
    expect(overlayBandWithPages(unreviewed, 1)).toBe('yellow');
  });

  it('the review-JUMP agrees with the row icon on every field state', () => {
    // Third surface (bd polyglot-pdf-l7u0, fresh-eyes round 8). FieldList
    // routed its icon through statusFromFindings but re-assembled the gate's
    // two booleans by hand for "next to review" -- identical results at the
    // time, but a change to the gate's inputs would land on one path and not
    // the other, and a jump that skips a visibly-amber row reports "nothing
    // left to review" while flagged rows sit on screen. Both now derive from
    // the same findings; this pins that they cannot disagree.
    const cases: Array<[string, FormField, LintFinding[]]> = [
      ['clean reviewed', field(), []],
      ['lint ERROR', field(), [errorFinding]],
      ['stale unacked', field(), [staleFinding]],
      ['stale acked', field({
        _review: { status: 'reviewed_correct', guidance_ack_sha1: IDENTITY },
      } as Partial<FormField>), [staleFinding]],
      ['superseded ack', field({
        _review: { status: 'reviewed_correct', guidance_ack_sha1: 'OLD' },
      } as Partial<FormField>), [staleFinding]],
      ['unreviewed', field({ _review: undefined } as Partial<FormField>), []],
    ];
    for (const [label, f, findings] of cases) {
      const status = statusFromFindings(f, findings);
      const isTarget = isReviewTargetFromFindings(f, findings);
      // A field is a jump target exactly when it is NOT settled green.
      expect(isTarget, `${label}: jump/icon disagree`).toBe(status !== 'complete');
    }
  });

  it('DEGRADES to previous behavior with no findings prop (criterion 2)', () => {
    // A call site that has no lint report omits the prop entirely. The overlay
    // must render exactly as before rather than crashing.
    const f = field();
    expect(() => overlayBand(f, undefined)).not.toThrow();
    expect(overlayBand(f, undefined)).toBe('green');
    // ...and an un-reviewed field is still amber without any findings at all.
    const unreviewed = field({ _review: undefined } as Partial<FormField>);
    expect(overlayBand(unreviewed, undefined)).toBe('yellow');
  });
});
