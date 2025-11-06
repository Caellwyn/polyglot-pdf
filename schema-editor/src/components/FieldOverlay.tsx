/**
 * FieldOverlay Component
 *
 * Renders a colored border overlay on top of a PDF field.
 * Color indicates field completion status:
 * - Green: Complete
 * - Yellow: Needs review
 * - Red: Has errors
 */

import React from 'react';
import type { FormField } from '../types/schema';
import { pdfToScreenCoords, hasValidCoordinates } from '../utils/pdfCoordinates';
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

  // Determine border color based on field status
  const status = checkFieldComplete(field);
  let borderColor: string;
  let bgColor: string;

  if (status.isComplete) {
    borderColor = isSelected ? 'rgb(34, 197, 94)' : 'rgb(74, 222, 128)';  // green-500 : green-400
    bgColor = 'rgba(34, 197, 94, 0.05)';  // Very light green
  } else if (status.needsReview) {
    borderColor = isSelected ? 'rgb(234, 179, 8)' : 'rgb(250, 204, 21)';  // yellow-500 : yellow-400
    bgColor = 'rgba(234, 179, 8, 0.05)';  // Very light yellow
  } else {
    borderColor = isSelected ? 'rgb(239, 68, 68)' : 'rgb(248, 113, 113)';  // red-500 : red-400
    bgColor = 'rgba(239, 68, 68, 0.05)';  // Very light red
  }

  // Selected fields get thicker border
  const borderWidth = isSelected ? 3 : 2;

  // Hovered fields get lighter background
  const finalBgColor = isHovered ? bgColor : 'transparent';

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
