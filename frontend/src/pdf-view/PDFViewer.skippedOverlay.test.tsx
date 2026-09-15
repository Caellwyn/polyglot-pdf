/**
 * A SKIPPED FIELD IS VISIBLY DISTINCT ON THE PDF OVERLAY (bd polyglot-pdf-c9dfo).
 *
 * `fillStateFor` returning 'skipped' is only half the fix -- the state has to
 * reach the rendered box, and it has to LOOK different from a blank. Before
 * this, a deliberately-skipped required field painted exactly like one the user
 * never touched: markFieldSkipped stores {value: null, skipped: true}, and the
 * empty check fired on the null before anything read the flag.
 *
 * That silence contradicted the contract schemaFormState.ts states for
 * markFieldSkipped -- a skipped field "renders visibly distinct as skipped --
 * needs follow-up ... NOT a silent blank". True in the form view, which paints
 * a Skipped badge. False here.
 *
 * It matters more since bd polyglot-pdf-ykfx0 gave Preview its own skip
 * control: a user can now create this state without leaving the PDF surface,
 * and the popover note that confirms it disappears when the popover closes. The
 * overlay is the only lasting evidence.
 *
 * These tests assert the rendered RESULT, not the palette constants -- a test
 * comparing BORDERS.skipped to a hard-coded colour string would pass while the
 * state never reached the DOM, and would have to be edited for any restyle.
 * What must hold is that skipped differs from blank, and is not confusable with
 * the field the assistant is currently on.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import type { FormField } from '../schema-forms/types/schema';

afterEach(() => cleanup());

vi.mock('./PDFPage', () => ({
  PDFPage: () => <div data-testid="mock-pdf-page" />,
}));

import { PDFViewer } from './PDFViewer';

const FIELD: FormField = {
  id: 'uscis_number',
  name: 'USCIS Number',
  spoken_name: 'USCIS number',
  section_id: 's1',
  type: 'text',
  validation: { required: true },
  pdf_position: { page: 1, x: 100, y: 100, width: 120, height: 14 },
} as any;

function renderWith(entry: unknown, currentFieldId: string | null = null) {
  render(
    <PDFViewer
      document={{} as any}
      numPages={1}
      scale={1}
      fields={[FIELD]}
      fieldValues={entry === undefined ? {} : { [FIELD.id]: entry }}
      currentFieldId={currentFieldId}
    />,
  );
  return screen.getByTestId(`pdf-field-overlay-${FIELD.id}`);
}

/** The inline border+background the overlay actually painted. */
function paintOf(box: HTMLElement): { border: string; background: string } {
  return { border: box.style.border, background: box.style.backgroundColor };
}

const SKIPPED = { value: null, skipped: true, confirmed: true };

describe('a skipped field does not paint as a blank (bd polyglot-pdf-c9dfo)', () => {
  it('carries the skipped state through to the rendered box', () => {
    const box = renderWith(SKIPPED);
    expect(
      box.getAttribute('data-fill-state'),
      'the state must reach the DOM, not just fillStateFor',
    ).toBe('skipped');
  });

  it('paints DIFFERENTLY from an untouched field -- the actual defect', () => {
    const skipped = paintOf(renderWith(SKIPPED));
    cleanup();
    const untouched = paintOf(renderWith(undefined));

    // This is the assertion the bug would fail. Both were previously 'empty',
    // so both got a 1px grey border and a transparent background.
    expect(
      skipped,
      'a deliberate skip must be visually distinguishable from a field the ' +
        'user never answered -- otherwise the follow-up it needs is invisible',
    ).not.toEqual(untouched);

    // And specifically: it carries a tint. 'empty' is transparent, and on a
    // printed form a border alone can be lost against a ruled box.
    expect(skipped.background).not.toBe('transparent');
    expect(skipped.background).not.toBe('');
  });

  it('is not confusable with the field the assistant is currently on', () => {
    const skipped = paintOf(renderWith(SKIPPED));
    cleanup();
    const current = paintOf(renderWith({ value: null }, FIELD.id));

    expect(
      skipped,
      'skipped must not look like current -- the form view uses amber for its ' +
        'Skipped badge, but amber is already current on this surface',
    ).not.toEqual(current);
  });

  it('is not confusable with a filled or confirmed field either', () => {
    const skipped = paintOf(renderWith(SKIPPED));
    cleanup();
    const filled = paintOf(renderWith({ value: 'A123' }));
    cleanup();
    const confirmed = paintOf(renderWith({ value: 'A123', confirmed: true }));

    expect(skipped).not.toEqual(filled);
    expect(skipped).not.toEqual(confirmed);
  });

  it('an ordinary empty field still paints as before', () => {
    // The negative half: this must not have become a blanket restyle of every
    // blank box.
    const box = renderWith({ value: null });
    expect(box.getAttribute('data-fill-state')).toBe('empty');
    expect(box.style.backgroundColor).toBe('transparent');
  });

  it('current still wins for a skipped field the assistant re-pins', () => {
    const box = renderWith(SKIPPED, FIELD.id);
    expect(box.getAttribute('data-fill-state')).toBe('current');
  });
});
