/**
 * THE OVERLAY'S FILL STATE REACHES ASSISTIVE TECH (bd polyglot-pdf-sagh6).
 *
 * The state used to live ONLY in an inline border/background colour and a
 * `data-fill-state` attribute -- neither of which any screen reader reads.
 * Measured before fixing:
 *
 *   editable overlay:  role=button, aria-label "Edit USCIS Number"  (no state)
 *   read-only overlay: role=null,   aria-label=null                (INVISIBLE)
 *
 * So the second case was not merely missing its state -- the box was absent
 * from the accessibility tree entirely.
 *
 * That matters most for 'skipped', which means a required question was
 * deliberately left unanswered and a human must follow up. The FORM view says
 * so in words (a "Skipped" badge plus a role=status note); the PDF view said it
 * in purple. And since bd polyglot-pdf-ykfx0 gave Preview its own skip button,
 * a screen-reader user can now both CREATE and fail to perceive that state
 * without leaving the PDF surface -- the popover note that confirms it vanishes
 * when the popover closes, leaving the overlay as the only lasting evidence.
 *
 * These tests drive the REAL PDFViewer and query by ACCESSIBLE NAME (the thing
 * a screen reader actually announces), not by the attribute or the colour.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import type { FormField } from '../schema-forms/types/schema';
import { accessibleNameFor, STATE_PHRASES, type FillState } from './FieldOverlay';

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

const SKIPPED = { value: null, skipped: true, confirmed: true };

/**
 * `editable` mirrors PreviewPane: the edit handlers arrive together, and
 * without them the surface is read-only (which is the case that had NO
 * accessible name at all).
 */
function renderOverlay(
  entry: unknown,
  opts: { editable?: boolean; currentFieldId?: string | null } = {},
) {
  const editable = opts.editable ?? true;
  render(
    <PDFViewer
      document={{} as any}
      numPages={1}
      scale={1}
      fields={[FIELD]}
      fieldValues={entry === undefined ? {} : { [FIELD.id]: entry }}
      currentFieldId={opts.currentFieldId ?? null}
      {...(editable
        ? {
            editingFieldId: null,
            onOverlayClick: vi.fn(),
            onCloseEditor: vi.fn(),
            onFieldChange: vi.fn(),
            onFieldBlur: vi.fn(),
          }
        : {})}
    />,
  );
  return screen.getByTestId(`pdf-field-overlay-${FIELD.id}`);
}

describe('a skipped field announces itself (bd polyglot-pdf-sagh6)', () => {
  it('is findable BY ACCESSIBLE NAME, not just by colour', () => {
    renderOverlay(SKIPPED);
    // What a screen reader announces. Queried by role+name rather than by the
    // data attribute precisely because the attribute was never the problem.
    expect(
      screen.getByRole('button', { name: /set aside to answer later/i }),
      'a skipped field must say so, not only look purple',
    ).toBeTruthy();
  });

  it('announces itself on a READ-ONLY surface too, where it had no name at all', () => {
    // The worse half of the original defect: a non-clickable overlay had no
    // role and no aria-label, so it was absent from the accessibility tree.
    const box = renderOverlay(SKIPPED, { editable: false });
    expect(box.getAttribute('role'), 'a read-only overlay needs a role to be nameable').toBe('img');
    expect(box.getAttribute('aria-label')).toMatch(/set aside to answer later/i);
  });

  it('keeps the field NAME -- the state is added, not substituted', () => {
    renderOverlay(SKIPPED);
    const label = screen.getByRole('button').getAttribute('aria-label') ?? '';
    expect(label, 'the user still has to know WHICH field').toMatch(/USCIS Number/);
    expect(label).toMatch(/set aside/i);
  });
});

describe('every fill state that should announce, does (bd polyglot-pdf-sagh6)', () => {
  // CRITERION 3: pin the COMPLETE set, so a sixth state added without an
  // announcement fails here rather than in a review round. The map itself is a
  // Record<FillState, string>, so tsc already refuses an incomplete one -- this
  // pins that the phrases actually REACH the rendered name, and that 'empty'
  // stays deliberately silent.
  const CASES: Array<{
    state: FillState;
    entry: unknown;
    currentFieldId?: string | null;
    announces: boolean;
  }> = [
    { state: 'empty', entry: undefined, announces: false },
    { state: 'filled', entry: { value: 'A123456789' }, announces: true },
    { state: 'confirmed', entry: { value: 'A123456789', confirmed: true }, announces: true },
    { state: 'skipped', entry: SKIPPED, announces: true },
    { state: 'current', entry: { value: null }, currentFieldId: FIELD.id, announces: true },
  ];

  it('covers every FillState -- a new one cannot slip in untested', () => {
    // DERIVED from the shipped map, never hand-listed. A hand-written list is
    // exactly how a state goes unannounced: the list keeps passing while the
    // union grows past it (CLAUDE.md scar 8 -- pin the set, not the instance).
    const declared = (Object.keys(STATE_PHRASES) as FillState[]).slice().sort();
    const covered = CASES.map(c => c.state).slice().sort();
    expect(
      covered,
      'a FillState exists with no case above -- add one rather than widening this',
    ).toEqual(declared);
  });

  for (const { state, entry, currentFieldId, announces } of CASES) {
    it(`${state}: ${announces ? 'adds a state phrase' : 'stays silent'}`, () => {
      const box = renderOverlay(entry, { currentFieldId });
      const label = box.getAttribute('aria-label') ?? '';

      // Cross-check that the fixture produced the state we meant to test --
      // otherwise a fixture drifting would silently test the wrong row.
      expect(box.getAttribute('data-fill-state'), `fixture for '${state}' drifted`).toBe(state);

      if (announces) {
        expect(
          label,
          `'${state}' must add a state phrase to the accessible name`,
        ).not.toBe(`Edit ${FIELD.name}`);
        expect(label).toContain(accessibleNameFor(FIELD.name, state));
      } else {
        // An unfilled field has nothing to report, and a phrase on every blank
        // box would bury the states that do.
        expect(label, 'an empty field must not chatter').toBe(`Edit ${FIELD.name}`);
      }
    });
  }
});

describe('the wording does not collide with the form view (bd polyglot-pdf-sagh6)', () => {
  it('avoids "needs follow-up", the form-view note locator', () => {
    // bd polyglot-pdf-c9dfo hit this exact collision once: repeating the
    // form-view note's phrase made getByText(/needs follow-up/i) match two
    // elements and throw, breaking a passing test in another file. The overlay
    // uses the Preview legend's wording instead, so the surface is consistent
    // AND the locator stays unique.
    const phrases = (Object.keys(STATE_PHRASES) as FillState[])
      .map(s => accessibleNameFor('F', s));
    for (const p of phrases) {
      expect(p, `"${p}" must not reuse the form view's locator phrase`)
        .not.toMatch(/needs follow-up/i);
    }
  });

  it('matches the Preview legend, so one state has one name', () => {
    expect(accessibleNameFor('F', 'skipped')).toMatch(/set aside to answer later/i);
  });
});
