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

export interface FieldOverlayProps {
  field: FormField;
  pageHeight: number;
  scale: number;
  isSelected: boolean;
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
  let borderColor: string;
  let bgColor: string;

  if (status === 'complete') {
    borderColor = isSelected ? 'rgb(34, 197, 94)' : 'rgb(74, 222, 128)';  // green-500 : green-400
    bgColor = isSelected ? 'rgba(34, 197, 94, 0.15)' : 'rgba(34, 197, 94, 0.05)';  // Stronger highlight when selected
  } else if (status === 'review' || status === 'followup') {
    borderColor = isSelected ? 'rgb(234, 179, 8)' : 'rgb(250, 204, 21)';  // yellow-500 : yellow-400
    bgColor = isSelected ? 'rgba(234, 179, 8, 0.15)' : 'rgba(234, 179, 8, 0.05)';  // Stronger highlight when selected
  } else {
    borderColor = isSelected ? 'rgb(239, 68, 68)' : 'rgb(248, 113, 113)';  // red-500 : red-400
    bgColor = isSelected ? 'rgba(239, 68, 68, 0.15)' : 'rgba(239, 68, 68, 0.05)';  // Stronger highlight when selected
  }

  // Selected fields get thicker border and shadow
  const borderWidth = isSelected ? 4 : 2;
  const boxShadow = isSelected ? '0 0 0 2px rgba(59, 130, 246, 0.5)' : 'none';  // Blue glow when selected

  // Hovered fields get lighter background
  const finalBgColor = (isHovered || isSelected) ? bgColor : 'transparent';

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
        border: `${borderWidth}px solid ${borderColor}`,
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
