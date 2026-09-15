/**
 * FieldOverlay -- a field's rect on the rendered PDF page, colored by FILL
 * state and painting the user's value inside it (bd polyglot-pdf-ogrt).
 *
 * Diverged from the schema editor's FieldOverlay: the editor colors by
 * metadata completeness; this one colors by fill state
 * (empty / filled / confirmed / current).
 *
 * - option-rect painting (bd lp5v): a selected radio/checkbox/checkbox_group
 *   option with its own pdf_position gets an X mark at that option's printed
 *   box (rendered as sibling divs in the same page-coordinate space; the
 *   field-level state box stays, keeping data-field-id for snap-to). Options
 *   without rects fall back to the label-at-field-rect painting.
 * - show_if dimming (bd lp5v): a conditionally-hidden field renders dimmed
 *   (never removed -- it exists on paper) and is not clickable; `current`
 *   wins over dimmed (never dim the field the voice model is on).
 * - click-to-edit (bd 7esr): with `onClick` present and the field not
 *   dimmed, the overlay (and its option marks, as extra pointer targets)
 *   opens the whole-field FieldEditPopover; the field box is the single
 *   accessible button (Enter/Space).
 */

import React from 'react';
import type { FormField } from '../schema-forms/types/schema';
import { pdfToScreenCoords, hasValidCoordinates } from './pdfCoordinates';
import {
  paintedValueFor,
  selectedOptionRects,
  fittedFontSize,
  type PaintedValue,
  optionLabel,
} from './valuePainting';

/**
 * How a field paints on the PDF overlay.
 *
 * 'skipped' exists because a deliberately-skipped required field used to paint
 * as 'empty' -- indistinguishable from one the user never touched (bd
 * polyglot-pdf-c9dfo). markFieldSkipped stores {value: null, skipped: true},
 * and fillStateFor's empty check fired on the null before anything could look
 * at the flag. The form view has always shown a "Skipped / needs follow-up"
 * badge for that state; the PDF surface silently did not, and
 * schemaFormState.ts's own docstring says it must ("NOT a silent blank").
 */
export type FillState = 'empty' | 'filled' | 'confirmed' | 'current' | 'skipped';

export interface FieldOverlayProps {
  field: FormField;
  /** UNWRAPPED raw value (see schema-forms/utils/fieldValue). */
  rawValue: unknown;
  fillState: FillState;
  scale: number;
  /** show_if says the field is hidden: render dimmed, not removed. */
  dimmed?: boolean;
  /**
   * Click-to-edit (bd polyglot-pdf-7esr): when present and the field is not
   * dimmed, the overlay (and its option marks -- bigger hit targets for the
   * SAME whole-field editor, never a direct toggle) becomes clickable and
   * keyboard-activatable. Dimmed fields are never clickable.
   */
  onClick?: (fieldId: string) => void;
}

const BORDERS: Record<FillState, string> = {
  empty: '1px solid rgba(148, 163, 184, 0.55)',
  filled: '2px solid rgb(59, 130, 246)',
  confirmed: '2px solid rgb(34, 197, 94)',
  current: '3px solid rgb(245, 158, 11)',
  // DOTTED purple, deliberately not the form view's amber badge colour: amber
  // is already 'current' here, and a skipped field must not read as the one the
  // assistant is asking about. Dashed is taken too (a dimmed show_if-hidden
  // field), so skipped carries BOTH an unused hue and an unused stroke -- the
  // point is that it cannot be mistaken for a blank.
  skipped: '2px dotted rgb(147, 51, 234)',
};

const BACKGROUNDS: Record<FillState, string> = {
  empty: 'transparent',
  filled: 'rgba(59, 130, 246, 0.06)',
  confirmed: 'rgba(34, 197, 94, 0.06)',
  current: 'rgba(245, 158, 11, 0.14)',
  // A tint, unlike 'empty''s transparent: on a printed form the border alone
  // can be lost against a ruled box, and the whole defect was a skip reading as
  // untouched.
  skipped: 'rgba(147, 51, 234, 0.08)',
};

const DIMMED_BORDER = '1px dashed rgba(148, 163, 184, 0.6)';

/**
 * What each fill state ADDS to the overlay's accessible name.
 *
 * The state used to live only in an inline colour and a data- attribute,
 * neither of which assistive tech reads -- so a screen-reader user got "Edit
 * <field>" at best, and on a read-only surface nothing at all (bd
 * polyglot-pdf-sagh6). Colour was carrying the whole meaning, including
 * "skipped", which means a required question was deliberately left unanswered
 * and a human must follow up.
 *
 * `Record<FillState, string>` on purpose, exactly like BORDERS/BACKGROUNDS: a
 * sixth state cannot be added without deciding what it announces, because tsc
 * refuses the incomplete map.
 *
 * 'empty' is deliberately SILENT. An unfilled field has nothing to report, and
 * a phrase on every blank box would bury the states that do.
 *
 * The wording avoids "needs follow-up" even though that is the form view's
 * phrase for the same state: it is how tests and screen readers locate the
 * form-view NOTE, and repeating it made getByText match two elements and throw
 * during bd polyglot-pdf-c9dfo. "set aside to answer later" matches the Preview
 * legend instead, so the surface says one thing consistently.
 */
export const STATE_PHRASES: Record<FillState, string> = {
  empty: '',
  filled: 'answered, not yet confirmed',
  confirmed: 'confirmed',
  current: 'being asked now',
  skipped: 'set aside to answer later',
};

/**
 * The overlay's accessible name: the field, its VALUE, and its state.
 *
 * The value has to be in the NAME, not merely painted inside the box. Under
 * ARIA an `img` is a LEAF -- its accessible name replaces its subtree -- so the
 * moment the read-only overlay gained role="img" (to be nameable at all), the
 * painted value text inside it stopped being reachable. Measured: a confirmed
 * field rendered `textContent "A123456789"` while announcing only
 * "USCIS Number: confirmed". Announcing a field's STATUS while hiding the
 * user's actual ANSWER trades one accessibility gap for a worse one; found by
 * fresh-eyes, and it was a real regression in my first version.
 *
 * `spokenValue` is the SAME text the box paints (from paintedValueFor), so a
 * screen reader hears what a sighted user sees -- including an option's human
 * label rather than its slug, which that helper already resolves.
 */
export function accessibleNameFor(
  fieldName: string,
  fillState: FillState,
  spokenValue?: string,
): string {
  // "Field: value (state)" rather than colon-joining all three. A three-way
  // colon chain reads badly aloud -- "Has apartment: checked: confirmed" --
  // and the state is a parenthetical about the value, not a third peer.
  const phrase = STATE_PHRASES[fillState];
  const head = spokenValue ? `${fieldName}: ${spokenValue}` : fieldName;
  return phrase ? `${head} (${phrase})` : head;
}

export const FieldOverlay: React.FC<FieldOverlayProps> = ({
  field,
  rawValue,
  fillState,
  scale,
  dimmed = false,
  onClick,
}) => {
  if (!hasValidCoordinates(field.pdf_position)) {
    return null;
  }

  // `current` always wins: the field the voice model is on is never dimmed
  // (the border/background/snap cues must stay visible).
  const isDimmed = dimmed && fillState !== 'current';

  // A dimmed SKIPPED field keeps its own colours while staying dimmed.
  //
  // Dimming otherwise replaces border AND background wholesale with
  // grey-dashed + transparent -- which for a skipped field reproduces exactly
  // the untouched-blank look bd polyglot-pdf-c9dfo exists to eliminate, one
  // condition deeper. Reachable because `dimmed` tracks show_if ALONE: a field
  // can be skipped and then hidden by a later answer, or hidden and then
  // skipped.
  //
  // This is deliberately NARROWER than adding 'skipped' to the isDimmed
  // exemption above. That would also make the field CLICKABLE and drop its
  // 0.35 opacity, breaking bd polyglot-pdf-lp5v's rule that a show_if-hidden
  // field is "dimmed, never removed, and never clickable". A hidden field must
  // stay inert whatever its fill state; only its COLOUR needs to survive, so
  // the follow-up it needs is still legible through the dimming.
  const keepsColourWhileDimmed = isDimmed && fillState === 'skipped';

  // Dimmed = visible-but-inert: the cue for "make this active" is the
  // controlling field, and editing an invisible-in-Simplified field could
  // contradict it.
  const clickable = !!onClick && !isDimmed;
  const activate = clickable ? () => onClick(field.id) : undefined;
  // The accessible name carries the VALUE and the STATE in both modes: the
  // colour never reached assistive tech, and once the read-only overlay gained
  // role="img" to be nameable, ARIA's leaf rule meant the painted value inside
  // it stopped being reachable too (bd polyglot-pdf-sagh6).
  //
  // Computed from the SAME helpers that decide what to paint, so the
  // announcement matches the box:
  //   - the ordinary case paints text (or an X) at the field rect;
  //   - when selected options carry their own printed rects, marks paint THERE
  //     and the field box paints nothing -- so the name has to name the
  //     selected options, or a radio/checkbox group would announce no answer at
  //     all.
  const optionRectsForName = selectedOptionRects(field, rawValue);
  const spokenValue = ((): string | undefined => {
    if (optionRectsForName.length > 0) {
      const labels = optionRectsForName.map(o => optionLabel(field, o.value));
      return labels.join(', ');
    }
    // A SELECT is the one type where paint-text and speech-text must differ.
    // paintedValueFor deliberately paints the option's pdf_on_value -- the PDF
    // EXPORT CODE -- because a speakable label ("Armed Forces Americas (AA)")
    // clips in a 36px state box. That is a PIXEL constraint, and it does not
    // transfer to speech: read aloud, "AA" tells the user nothing, and bd
    // polyglot-pdf-jpjcv is on record that an alphabetic code is not speakable
    // as itself. So speech resolves the LABEL while the box keeps the code.
    // Radio and checkbox_group already speak labels, so select was the only
    // path where reusing paint-text silently degraded the announcement
    // (Opus cross-surface round 2).
    if (field.type === 'select' && typeof rawValue === 'string' && rawValue !== '') {
      return optionLabel(field, rawValue);
    }
    const painted = paintedValueFor(field, rawValue);
    if (painted.kind === 'text') return painted.text;
    if (painted.kind === 'check') return 'checked';
    return undefined;
  })();
  const accessibleName = accessibleNameFor(field.name, fillState, spokenValue);

  const interactiveProps = clickable
    ? {
        role: 'button' as const,
        tabIndex: 0,
        'aria-label': `Edit ${accessibleName}`,
        onClick: activate,
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            activate!();
          }
        },
        style: { pointerEvents: 'auto' as const, cursor: 'pointer' },
      }
    : {
        // A NON-clickable overlay had no role and no name whatsoever, so a
        // read-only or dimmed field was entirely absent from the accessibility
        // tree -- not merely missing its state (measured before fixing).
        //
        // role="img" rather than a bare labelled div: an aria-label on a div
        // with no role is not reliably announced, because such a node is not
        // nameable. "img" is also honest about what this is -- a graphic whose
        // colour stands for a state.
        role: 'img' as const,
        'aria-label': accessibleName,
        style: {},
      };

  const pos = pdfToScreenCoords(field.pdf_position, scale);

  // Option-rect painting: when any SELECTED option carries its own usable
  // rect, marks paint at those rects and the field-level box paints no text
  // (the mark placement IS the value display; a duplicate label at the field
  // rect would just clutter the form).
  const optionRects = optionRectsForName;

  let content: React.ReactNode = null;
  if (optionRects.length === 0) {
    const painted: PaintedValue = paintedValueFor(field, rawValue);
    if (painted.kind === 'check') {
      content = (
        <span
          className="pdf-field-overlay__check"
          // DECORATIVE to assistive tech: the accessible name already says
          // "checked" (see accessibleNameFor). Without this, the editable
          // overlay -- role="button", which is NOT an ARIA leaf -- would have
          // the value in its name AND expose this glyph as child text, so a
          // screen reader could announce it twice (fresh-eyes round 2). The
          // read-only overlay is role="img", an ARIA leaf, so its subtree is
          // pruned anyway; this makes both paths agree.
          //
          // Set on the EXISTING span rather than a wrapper: .pdf-field-overlay
          // is display:flex with no justify-content, and this span's
          // `margin: 0 auto` (pdf-view.css) is what centres the X. A wrapper
          // would become the flex item, leaving the auto margin no free space
          // to distribute -- the X would jump to the left edge. A silent visual
          // regression in an untouched stylesheet, invisible to the suite;
          // caught by the Opus cross-surface review.
          aria-hidden="true"
          style={{ fontSize: `${Math.max(8, Math.min(pos.height * 0.8, 24))}px` }}
        >
          X
        </span>
      );
    } else if (painted.kind === 'text') {
      const isMultiline = field.type === 'textarea';
      content = (
        <span
          className="pdf-field-overlay__text"
          // Decorative for the same reason as the check glyph above; likewise
          // set on the existing span so the flex layout is untouched.
          aria-hidden="true"
          style={{
            fontSize: `${fittedFontSize(painted.text, pos.width - 4, pos.height)}px`,
            whiteSpace: isMultiline ? 'normal' : 'nowrap',
          }}
        >
          {painted.text}
        </span>
      );
    }
  }

  const classes = ['pdf-field-overlay', `pdf-field-overlay--${fillState}`];
  if (isDimmed) classes.push('pdf-field-overlay--dimmed');
  if (clickable) classes.push('pdf-field-overlay--clickable');
  const { style: interactiveStyle, ...interactiveRest } = interactiveProps;
  return (
    <>
      <div
        className={classes.join(' ')}
        style={{
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          width: `${pos.width}px`,
          height: `${pos.height}px`,
          border:
            isDimmed && !keepsColourWhileDimmed ? DIMMED_BORDER : BORDERS[fillState],
          backgroundColor:
            isDimmed && !keepsColourWhileDimmed ? 'transparent' : BACKGROUNDS[fillState],
          ...interactiveStyle,
        }}
        data-field-id={field.id}
        data-fill-state={fillState}
        data-dimmed={isDimmed || undefined}
        data-testid={`pdf-field-overlay-${field.id}`}
        {...interactiveRest}
      >
        {content}
      </div>
      {optionRects.map(({ value, position }) => {
        const optPos = pdfToScreenCoords(position, scale);
        const markClasses = ['pdf-field-overlay__option-mark'];
        if (isDimmed) markClasses.push('pdf-field-overlay--dimmed');
        if (clickable) markClasses.push('pdf-field-overlay--clickable');
        return (
          <div
            key={value}
            className={markClasses.join(' ')}
            style={{
              left: `${optPos.x}px`,
              top: `${optPos.y}px`,
              width: `${optPos.width}px`,
              height: `${optPos.height}px`,
              fontSize: `${Math.max(8, Math.min(optPos.height * 0.8, 24))}px`,
              ...interactiveStyle,
            }}
            // Decorative: the field box's accessible name already names every
            // selected option by its label (accessibleNameFor), so an
            // unlabelled "X" per mark would just repeat it -- and a bare "X"
            // with no context is worse than silence. The field box carries the
            // role and the meaning; these are extra hit targets for the SAME
            // editor. Pre-existing on dev (filed as bd polyglot-pdf-jlwr6);
            // folded in here because it is one attribute on the element this
            // diff's own naming work made redundant, and the mark div is its
            // own flex container with a bare text child, so there is no
            // layout dependency to break.
            aria-hidden="true"
            data-testid={`pdf-option-mark-${field.id}-${value}`}
            {...(clickable
              ? // An option mark is an extra hit target for the SAME
                // whole-field editor -- the field box carries the accessible
                // button role; marks stay presentation with a click handler.
                { onClick: activate }
              : {})}
          >
            X
          </div>
        );
      })}
    </>
  );
};
