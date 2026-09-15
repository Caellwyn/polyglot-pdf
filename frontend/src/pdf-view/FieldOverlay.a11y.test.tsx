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
    /** The value the fixture paints, when it has one -- it rides in the name. */
    spoken?: string;
    announces: boolean;
  }> = [
    { state: 'empty', entry: undefined, announces: false },
    { state: 'filled', entry: { value: 'A123456789' }, spoken: 'A123456789', announces: true },
    { state: 'confirmed', entry: { value: 'A123456789', confirmed: true }, spoken: 'A123456789', announces: true },
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

  for (const { state, entry, currentFieldId, spoken, announces } of CASES) {
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
        // Built from the SAME inputs the component saw, including the value --
        // a filled field announces "Field: value (state)", so an expectation
        // omitting the value would check a string the code never emits.
        expect(label).toContain(accessibleNameFor(FIELD.name, state, spoken));
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

describe('the ANSWER survives the img leaf rule (bd polyglot-pdf-sagh6)', () => {
  // Found by fresh-eyes, and it was a real regression in my first version.
  //
  // Under ARIA an `img` is a LEAF: its accessible name REPLACES its subtree. So
  // the moment the read-only overlay gained role="img" (to be nameable at all),
  // the value painted inside it stopped being reachable. Measured then: a
  // confirmed field had textContent "A123456789" while announcing only
  // "USCIS Number: confirmed" -- announcing a field's STATUS while hiding the
  // user's actual ANSWER, which is a worse gap than the one being fixed.
  //
  // So the value rides in the NAME, from the same helpers that decide what to
  // paint.
  const TEXT_FIELD: FormField = {
    id: 'uscis_number', name: 'USCIS Number', spoken_name: 'n', section_id: 's1',
    type: 'text', validation: { required: true },
    pdf_position: { page: 1, x: 10, y: 10, width: 100, height: 14 },
  } as any;

  const CHECKBOX: FormField = {
    id: 'has_apt', name: 'Has apartment', spoken_name: 'n', section_id: 's1',
    type: 'checkbox',
    pdf_position: { page: 1, x: 10, y: 40, width: 100, height: 14 },
  } as any;

  /** Options carrying their OWN rects: marks paint there, the box paints nothing. */
  const GROUP: FormField = {
    id: 'race', name: 'Race', spoken_name: 'n', section_id: 's1',
    type: 'checkbox_group',
    options: [
      { value: 'white', label: 'White', pdf_position: { page: 1, x: 10, y: 70, width: 20, height: 14 } },
      { value: 'asian', label: 'Asian', pdf_position: { page: 1, x: 40, y: 70, width: 20, height: 14 } },
    ],
    pdf_position: { page: 1, x: 10, y: 70, width: 100, height: 14 },
  } as any;

  function nameOf(fields: FormField[], values: Record<string, unknown>, id: string): string {
    render(
      <PDFViewer document={{} as any} numPages={1} scale={1} fields={fields}
        fieldValues={values} currentFieldId={null} />,
    );
    return screen.getByTestId(`pdf-field-overlay-${id}`).getAttribute('aria-label') ?? '';
  }

  it('a read-only filled field announces its VALUE, not just its state', () => {
    const name = nameOf([TEXT_FIELD], { uscis_number: { value: 'A123456789', confirmed: true } }, 'uscis_number');
    expect(
      name,
      'the answer is painted inside an img-rolled box, so it only reaches AT ' +
        'through the accessible name',
    ).toContain('A123456789');
    expect(name).toContain('USCIS Number');
    expect(name).toContain('confirmed');
  });

  it('a ticked checkbox says so -- an X glyph is not readable', () => {
    const name = nameOf([CHECKBOX], { has_apt: { value: true, confirmed: true } }, 'has_apt');
    expect(name).toMatch(/checked/i);
  });

  it("a group whose options paint at their OWN rects still names the selection", () => {
    // The box paints NOTHING in this case (the marks carry the display), so
    // without naming the selection the field would announce no answer at all.
    const name = nameOf([GROUP], { race: { value: ['white'], confirmed: true } }, 'race');
    expect(name, 'a selected option must be named, and by its LABEL not its slug')
      .toContain('White');
    expect(name, 'the slug must not leak into speech').not.toMatch(/\bwhite\b(?![A-Za-z])/);
  });

  it('an unanswered field names no value', () => {
    const name = nameOf([TEXT_FIELD], {}, 'uscis_number');
    expect(name).toBe('USCIS Number');
  });
});

describe('the value is announced ONCE, on both paths (bd polyglot-pdf-sagh6)', () => {
  // The mirror of the img-leaf finding, and fresh-eyes caught both.
  //
  // read-only is role="img" -- an ARIA LEAF, so its subtree is pruned
  // automatically. That pruning is what made the painted value unreachable
  // until the name started carrying it.
  //
  // editable is role="button", which is NOT a leaf: its child text stays
  // exposed. So once the name carried the value, a screen reader could hear it
  // twice -- once from the name, once from the content. aria-hidden on the
  // painted subtree gives the button the same pruning the img gets, so one
  // mechanism serves both paths.
  //
  // Round 1's value tests all rendered the READ-ONLY branch (no edit handlers),
  // so nothing covered this until now.
  const FILLED: FormField = {
    id: 'uscis_number', name: 'USCIS Number', spoken_name: 'n', section_id: 's1',
    type: 'text', validation: { required: true },
    pdf_position: { page: 1, x: 10, y: 10, width: 100, height: 14 },
  } as any;

  function renderEditableFilled() {
    render(
      <PDFViewer
        document={{} as any}
        numPages={1}
        scale={1}
        fields={[FILLED]}
        fieldValues={{ uscis_number: { value: 'A123456789', confirmed: true } }}
        currentFieldId={null}
        editingFieldId={null}
        onOverlayClick={vi.fn()}
        onCloseEditor={vi.fn()}
        onFieldChange={vi.fn()}
        onFieldBlur={vi.fn()}
      />,
    );
    return screen.getByTestId(`pdf-field-overlay-${FILLED.id}`);
  }

  it('the editable overlay IS a button -- so its subtree is not auto-pruned', () => {
    // Establishes the premise the next test depends on. If this ever stops
    // being a button, the aria-hidden reasoning needs revisiting rather than
    // silently still passing.
    expect(renderEditableFilled().getAttribute('role')).toBe('button');
  });

  it('hides the painted value from AT, since the NAME already carries it', () => {
    const box = renderEditableFilled();

    expect(box.getAttribute('aria-label'), 'the name must carry the value')
      .toContain('A123456789');

    // The same text is still on screen -- and must be, for sighted users --
    // but excluded from the accessibility tree so it is not read twice.
    expect(box.textContent, 'the glyphs stay visible').toContain('A123456789');

    // aria-hidden sits on the EXISTING painted span, NOT on a wrapper. A
    // wrapper would become the flex item and steal the free space that
    // .pdf-field-overlay__check's `margin: 0 auto` needs to centre the X --
    // a silent visual regression in an untouched stylesheet, which the Opus
    // cross-surface review caught. Asserting the span ITSELF is what stops a
    // future "tidy-up" reintroducing the wrapper.
    const painted = box.querySelector('.pdf-field-overlay__text');
    expect(painted, 'the painted span must still exist').toBeTruthy();
    expect(
      painted?.getAttribute('aria-hidden'),
      'aria-hidden belongs ON the painted span, not on a wrapper around it',
    ).toBe('true');
    expect(painted?.textContent).toContain('A123456789');
    expect(
      box.firstElementChild,
      'the painted span must be a DIRECT child -- its auto-margin centring ' +
        'depends on being the flex item',
    ).toBe(painted);
  });

  it('hides it on the READ-ONLY path too, so one rule covers both', () => {
    render(
      <PDFViewer document={{} as any} numPages={1} scale={1} fields={[FILLED]}
        fieldValues={{ uscis_number: { value: 'A123456789', confirmed: true } }}
        currentFieldId={null} />,
    );
    const box = screen.getByTestId(`pdf-field-overlay-${FILLED.id}`);
    const painted = box.querySelector('.pdf-field-overlay__text');
    expect(painted?.getAttribute('aria-hidden')).toBe('true');
    expect(box.firstElementChild, 'still a direct flex child').toBe(painted);
  });
});
