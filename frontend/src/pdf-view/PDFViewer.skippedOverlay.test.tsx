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
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
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

  // EVERY CUE must distinguish, not merely the pair as a whole. Asserting
  // `not.toEqual` on the {border, background} object was too weak: styling
  // skipped with the SAME border as 'empty' still passed, because the
  // background happened to differ, and styling it identically to 'current'
  // passed for the same reason. Both mutations survived. A viewer reads ONE
  // cue at a glance, so each has to carry the distinction on its own.
  function expectDistinctPaint(
    a: { border: string; background: string },
    b: { border: string; background: string },
    what: string,
  ) {
    expect(a.border, `skipped must not share a BORDER with ${what}`).not.toBe(b.border);
    expect(a.background, `skipped must not share a BACKGROUND with ${what}`)
      .not.toBe(b.background);
  }

  it('paints DIFFERENTLY from an untouched field -- the actual defect', () => {
    const skipped = paintOf(renderWith(SKIPPED));
    cleanup();
    const untouched = paintOf(renderWith(undefined));

    // The assertion the bug fails. Both were previously 'empty', so both got a
    // 1px grey border and a transparent background.
    expectDistinctPaint(skipped, untouched, 'an untouched field');

    // And specifically: it carries a tint. 'empty' is transparent, and on a
    // printed form a border alone can be lost against a ruled box.
    expect(skipped.background).not.toBe('transparent');
    expect(skipped.background).not.toBe('');
  });

  it('is not confusable with the field the assistant is currently on', () => {
    const skipped = paintOf(renderWith(SKIPPED));
    cleanup();
    const current = paintOf(renderWith({ value: null }, FIELD.id));

    // The form view uses amber for its Skipped badge, but amber is already
    // 'current' on this surface -- so reusing it would make a skipped field
    // read as the one being asked about right now.
    expectDistinctPaint(skipped, current, 'the current field');
  });

  it('is not confusable with a filled or confirmed field either', () => {
    const skipped = paintOf(renderWith(SKIPPED));
    cleanup();
    const filled = paintOf(renderWith({ value: 'A123' }));
    cleanup();
    const confirmed = paintOf(renderWith({ value: 'A123', confirmed: true }));

    expectDistinctPaint(skipped, filled, 'a filled field');
    expectDistinctPaint(skipped, confirmed, 'a confirmed field');
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

describe("the legend names the state without stealing the note's phrase", () => {
  // The legend has to explain the purple box, or the colour is unexplained.
  // But my first wording said "needs follow-up" -- the skipped NOTE's own
  // phrase -- so getByText(/needs follow-up/i) matched two elements and threw,
  // breaking a passing test in another file. A real failure, not a flake.
  //
  // Pinned from BOTH sides so neither half drifts back: the legend must still
  // name the colour, and must not re-use the note's locator phrase. Read from
  // source because the property is about the shipped string, and rendering
  // PreviewPane here would need the whole pdf document + overlay chain.
  const bannerSource = readFileSync(
    resolve(__dirname, 'PreviewPane.tsx'),
    'utf-8',
  );

  it('names the skipped colour', () => {
    expect(
      bannerSource,
      'a purple box with nothing explaining it is worse than no colour',
    ).toMatch(/purple\s*=/);
  });

  it('does not re-use the skipped note phrase "needs follow-up"', () => {
    // Scoped to the BANNER text, not the whole file: the file legitimately
    // mentions the phrase in comments, and a whole-file grep would fail on
    // those -- the evidence region has to match the claim.
    const start = bannerSource.indexOf('Preview mode: your answers');
    const end = bannerSource.indexOf('Filled PDF" below');

    // ASSERT THE ANCHORS WERE FOUND, before slicing with them.
    //
    // `slice(start, -1)` does NOT yield an empty string -- it widens to
    // (end of file - 1). So if only the END anchor drifted, the old
    // `length > 40` floor passed while the "banner" was nearly the whole file,
    // and the phrase check then held only because that phrase happens not to
    // recur later in the source. A floor that cannot fail is not a floor;
    // fresh-eyes mutation-verified exactly that by renaming the trailing text.
    expect(start, 'banner START anchor not found -- retarget this test').not.toBe(-1);
    expect(end, 'banner END anchor not found -- retarget this test').not.toBe(-1);
    expect(end, 'anchors out of order -- retarget this test').toBeGreaterThan(start);

    const banner = bannerSource.slice(start, end);

    // Bounded on BOTH sides: the banner is one known short sentence, so a
    // region this big can only mean the slice escaped its intended text.
    expect(banner.length, 'banner text too short -- retarget this test').toBeGreaterThan(40);
    expect(
      banner.length,
      'the sliced region is far larger than the banner sentence, so this test ' +
        'is no longer reading the banner',
    ).toBeLessThan(400);

    expect(
      banner,
      'the legend must not repeat "needs follow-up": that phrase is how tests ' +
        'and screen readers locate the skipped NOTE, and two matches throw',
    ).not.toMatch(/needs follow-up/i);
  });
});

describe('a dimmed skipped field keeps its cue (bd polyglot-pdf-c9dfo)', () => {
  // `dimmed` tracks show_if ALONE, so skipped-and-hidden is reachable in both
  // orders: skip a field then have a later answer hide it, or hide it and then
  // skip it. Dimming replaces border AND background wholesale, so before
  // 'skipped' joined 'current' in the exemption this painted grey-dashed +
  // transparent -- the untouched-blank look this bead exists to eliminate,
  // reappearing under one extra condition.
  //
  // Found by the fresh-eyes reviewer, not by me: my distinctness matrix
  // compared skipped against every real FillState and never against the
  // `dimmed` OVERRIDE, which is not a FillState at all.
  const HIDDEN_FIELD: FormField = {
    id: 'apt_number',
    name: 'Apt number',
    spoken_name: 'apartment number',
    section_id: 's1',
    type: 'text',
    validation: { required: true },
    // Never satisfied in these fixtures -> shouldShowField false -> dimmed.
    show_if: { field: 'has_apt', operator: 'is_checked' },
    pdf_position: { page: 1, x: 100, y: 200, width: 120, height: 14 },
  } as any;

  function renderHidden(entry: unknown) {
    render(
      <PDFViewer
        document={{} as any}
        numPages={1}
        scale={1}
        fields={[HIDDEN_FIELD]}
        fieldValues={entry === undefined ? {} : { [HIDDEN_FIELD.id]: entry }}
        currentFieldId={null}
      />,
    );
    return screen.getByTestId(`pdf-field-overlay-${HIDDEN_FIELD.id}`);
  }

  it('stays DIMMED and inert -- it is still conditionally hidden', () => {
    // Only the COLOUR survives. My first attempt added 'skipped' to the
    // isDimmed exemption, which also made the field clickable and dropped its
    // 0.35 opacity -- breaking bd polyglot-pdf-lp5v's rule that a
    // show_if-hidden field is "dimmed, never removed, and never clickable".
    // This pins the narrower behaviour so that cannot be widened by accident.
    const box = renderHidden(SKIPPED);
    expect(
      box.getAttribute('data-dimmed'),
      'a hidden field must stay inert whatever its fill state',
    ).toBe('true');
    expect(box.className).toMatch(/pdf-field-overlay--dimmed/);
  });

  it('does NOT paint as a dimmed blank -- the defect, one condition deeper', () => {
    const skipped = paintOf(renderHidden(SKIPPED));
    cleanup();
    const hiddenBlank = paintOf(renderHidden(undefined));

    expect(
      skipped.border,
      'a hidden-but-skipped field must not share the dimmed blank border -- ' +
        'the overlay is the only lasting record that it needs follow-up',
    ).not.toBe(hiddenBlank.border);
    expect(skipped.background).not.toBe(hiddenBlank.background);
  });

  it('an ordinary hidden blank field is still dimmed as before', () => {
    // The negative half: the exemption must not have un-dimmed everything.
    const box = renderHidden(undefined);
    expect(box.getAttribute('data-dimmed')).toBe('true');
    expect(box.style.border).toMatch(/dashed/);
    expect(box.style.backgroundColor).toBe('transparent');
  });
});
