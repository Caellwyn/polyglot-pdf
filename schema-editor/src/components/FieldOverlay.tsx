/**
 * FieldOverlay Component
 *
 * Renders a colored border overlay on top of a PDF field.
 * 
 * Features:
 * - Clickable: Click to select the field (syncs with field list)
 * - Visual feedback: Selected fields have thicker borders, blue glow, and stronger background
 * - Hover tooltips: Shows field name and type on hover
 * 
 * Color indicates field status (the SAME effective status the FieldList row
 * shows, so a review sign-off agrees across surfaces -- bd polyglot-pdf-u8t6):
 * - Green: complete, OR reviewed-correct (human sign-off over an auto-amber)
 * - Yellow: needs review (automatic) OR needs-follow-up (human flag)
 * - Red: has errors (always wins -- a sign-off never greens a broken field)
 */

import React from 'react';
import type { FormField } from '../types/schema';
import { pdfToScreenCoords, hasValidCoordinates } from '../utils/pdfCoordinates';
import { effectiveStatus } from '../utils/reviewStatus';
import { checkFieldComplete } from '../utils/validation';

type StatusBand = 'complete' | 'attention' | 'error';

/**
 * The single colour source for both display modes. Box mode reads
 * strong/soft/fill for the border and background; ID mode reads text for the
 * label. Keep them here together so the two modes cannot disagree.
 */
const STATUS_COLORS: Record<StatusBand, {
  strong: string; soft: string; fill: string; text: string;
}> = {
  complete: {
    strong: 'rgb(34, 197, 94)',    // green-500
    soft: 'rgb(74, 222, 128)',     // green-400
    fill: '34, 197, 94',
    text: 'rgb(21, 128, 61)',      // green-700
  },
  attention: {
    strong: 'rgb(234, 179, 8)',    // yellow-500
    soft: 'rgb(250, 204, 21)',     // yellow-400
    fill: '234, 179, 8',
    text: 'rgb(161, 98, 7)',       // yellow-700
  },
  error: {
    strong: 'rgb(239, 68, 68)',    // red-500
    soft: 'rgb(248, 113, 113)',    // red-400
    fill: '239, 68, 68',
    text: 'rgb(185, 28, 28)',      // red-700
  },
};

/** Label height as a fraction of the widget box, leaving a little leading. */
const LABEL_HEIGHT_RATIO = 0.72;
/** Below this the glyphs are noise: draw the coloured box instead. */
const MIN_LABEL_FONT_PX = 6;

export interface FieldOverlayProps {
  field: FormField;
  pageHeight: number;
  scale: number;
  isSelected: boolean;
  /**
   * ID mode: draw the field's ID over the widget instead of a coloured box.
   * Optional so every existing call site and test stays valid unchanged.
   */
  showFieldId?: boolean;
  onClick?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

/**
 * Field overlay that draws a colored border over a PDF field
 */
export const FieldOverlay: React.FC<FieldOverlayProps> = ({
  field,
  pageHeight,
  scale,
  isSelected,
  showFieldId = false,
  onClick,
  onMouseEnter,
  onMouseLeave,
}) => {
  const [isHovered, setIsHovered] = React.useState(false);

  // Don't render if no valid position data
  if (!hasValidCoordinates(field.pdf_position)) {
    return null;
  }

  // Convert PDF coordinates to screen coordinates
  const screenPos = pdfToScreenCoords(field.pdf_position!, pageHeight, scale);

  // Determine border color from the EFFECTIVE status (review sign-off layered
  // over the automatic derivation), so the overlay agrees with the FieldList
  // row instead of contradicting it (bd polyglot-pdf-u8t6). The overlay has no
  // backend lint findings threaded in, so hasLintError stays false here -- a
  // lint ERROR already reds the row via FieldList; the overlay keeps mirroring
  // local completeness + the review layer, which is what changed. 'followup'
  // and the automatic 'review' both sit in the yellow (needs-attention) band.
  const status = effectiveStatus(field);

  // ONE colour decision, read by BOTH modes: the box border in box mode and the
  // ID text in ID mode. A second table is how the two modes drift apart, and
  // then a reviewer sees a green box labelled in amber.
  //   strong = selected (-500), soft = unselected (-400),
  //   fill   = the rgb triple the translucent background is built from,
  //   text   = the ID-label tone (-700): thin glyphs over black-on-white form
  //            print need more contrast than a 2px border does.
  const band: StatusBand =
    status === 'complete' ? 'complete'
      : (status === 'review' || status === 'followup') ? 'attention'
        : 'error';
  const palette = STATUS_COLORS[band];

  const borderColor = isSelected ? palette.strong : palette.soft;
  const bgColor = `rgba(${palette.fill}, ${isSelected ? 0.15 : 0.05})`;

  // VERTICAL fit: a fixed fraction of the widget height. screenPos is ALREADY
  // multiplied by scale, so the label tracks zoom with no scale term here.
  const labelFontSize = screenPos.height * LABEL_HEIGHT_RATIO;
  // Below this the glyphs are noise, so draw no label and leave the coloured box
  // as the fallback -- it still carries review status, and hover/click still
  // identify the field. Keyed on SIZE, not field type: a 36pt select is exactly
  // as unreadable as a checkbox. Because screenPos is scaled, a SUPPRESSED label
  // reappears as the user zooms in (every label on the real kits is shown by
  // 150%), which is what makes suppression acceptable rather than lossy.
  //
  // Zoom does NOT rescue horizontal TRUNCATION, though -- box width and font
  // size both scale linearly, so the overflow ratio is zoom-invariant and a
  // label cut at 100% is cut identically at 300%. Measured on the real kits:
  // 16% of labelled f1040 fields truncate, 11% on w7, and 64% on i-90 (whose
  // ids average 21 chars). Hover is the recovery path for those, not zoom.
  const showLabel = showFieldId && labelFontSize >= MIN_LABEL_FONT_PX;

  // A suppressed label falls back to the FULL box: that box is then the only
  // thing marking the field, so thinning it would make small checkboxes vanish.
  const borderWidth = showLabel ? (isSelected ? 2 : 1) : (isSelected ? 4 : 2);
  const effectiveBorderColor = showLabel && !isSelected
    ? `rgba(${palette.fill}, 0.35)`   // hairline: shows extent, does not fight the text
    : borderColor;
  const boxShadow = isSelected ? '0 0 0 2px rgba(59, 130, 246, 0.5)' : 'none';  // Blue glow when selected

  // Never tint under a label -- it greys the printed form text being checked.
  const finalBgColor = showLabel
    ? 'transparent'
    : ((isHovered || isSelected) ? bgColor : 'transparent');

  const handleMouseEnter = () => {
    setIsHovered(true);
    onMouseEnter?.();
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
    onMouseLeave?.();
  };

  return (
    <div
      className="field-overlay"
      style={{
        position: 'absolute',
        left: `${screenPos.x}px`,
        top: `${screenPos.y}px`,
        width: `${screenPos.width}px`,
        height: `${screenPos.height}px`,
        border: `${borderWidth}px solid ${effectiveBorderColor}`,
        backgroundColor: finalBgColor,
        boxShadow: boxShadow,
        pointerEvents: 'auto',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        boxSizing: 'border-box',
        zIndex: isSelected ? 20 : 10,
      }}
      onClick={onClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      title={field.spoken_name || field.id}
      data-field-id={field.id}
      data-testid={`field-overlay-${field.id}`}
    >
      {/* ID mode: the field's own id, drawn over its widget. */}
      {showLabel && (
        <div
          className="field-id-label"
          data-testid={`field-id-label-${field.id}`}
          style={{
            position: 'absolute',
            inset: 0,
            // HORIZONTAL overflow -> truncate. Pure CSS, no measurement. NOT a
            // flex container: textOverflow does not apply to one, so vertical
            // centring uses lineHeight instead.
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis',
            fontSize: `${labelFontSize}px`,
            lineHeight: `${screenPos.height}px`,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontWeight: 600,
            color: palette.text,
            // A white HALO, not a plate: the reviewer must still see the printed
            // form text underneath -- that is the evidence being checked.
            WebkitTextStrokeWidth: '2px',
            WebkitTextStrokeColor: 'rgba(255, 255, 255, 0.9)',
            paintOrder: 'stroke fill',
            // LOAD-BEARING: without this the label becomes the hover target and
            // the overlay's non-bubbling mouseenter/mouseleave never fire, so
            // the spoken-name tooltip breaks.
            pointerEvents: 'none',
            userSelect: 'none',
          }}
        >
          {field.id}
        </div>
      )}

      {/* Field label tooltip (visible on hover) */}
      {isHovered && (
        <div
          className="field-label-tooltip"
          style={{
            position: 'absolute',
            bottom: '100%',
            left: '0',
            marginBottom: '4px',
            backgroundColor: 'rgba(0, 0, 0, 0.9)',
            color: 'white',
            padding: '4px 8px',
            borderRadius: '4px',
            fontSize: '12px',
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            zIndex: 30,
            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
          }}
        >
          {field.spoken_name || field.id}
          <span style={{ marginLeft: '8px', opacity: 0.7 }}>
            [{field.type}]
          </span>
        </div>
      )}
    </div>
  );
};

/**
 * Helper to get status badge text for field
 */
export function getFieldStatusBadge(field: FormField): string {
  const status = checkFieldComplete(field);
  if (status.isComplete) return '✓';
  if (status.needsReview) return '!';
  return '✗';
}

/**
 * Helper to get status color class for field
 */
export function getFieldStatusColor(field: FormField): string {
  const status = checkFieldComplete(field);
  if (status.isComplete) return 'green';
  if (status.needsReview) return 'yellow';
  return 'red';
}
