/**
 * Integration tests for FieldOverlay component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldOverlay } from './FieldOverlay';
import type { FormField } from '../types/schema';

describe('FieldOverlay', () => {
  const mockPageHeight = 792; // US Letter
  const mockScale = 1.0;

  const createMockField = (overrides?: Partial<FormField>): FormField => ({
    id: 'test-field',
    name: 'Test Field',
    type: 'text',
    pdf_field_name: 'test_field',
    read_only: false,
    spoken_name: 'Test Field',
    help: {
      instructions: 'Fill this out',
    },
    pdf_position: {
      page: 1,
      x: 100,
      y: 700,
      width: 150,
      height: 30,
    },
    ...overrides,
  });

  describe('Rendering', () => {
    it('should render overlay at correct position', () => {
      const field = createMockField();
      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay');
      expect(overlay).toBeInTheDocument();

      // Check positioning (PDF coords converted to screen coords)
      const style = (overlay as HTMLElement).style;
      expect(style.left).toBe('100px'); // x * scale
      expect(style.top).toBe('700px');  // y * scale (top-left origin, no Y-flip)
      expect(style.width).toBe('150px');
      expect(style.height).toBe('30px');
    });

    it('should not render if field has no pdf_position', () => {
      const field = createMockField({ pdf_position: undefined });
      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      expect(container.querySelector('.field-overlay')).not.toBeInTheDocument();
    });

    it('should scale position correctly at 1.5x zoom', () => {
      const field = createMockField();
      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={1.5}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.left).toBe('150px');   // 100 * 1.5
      expect(overlay.style.top).toBe('1050px');   // 700 * 1.5 (top-left origin, no Y-flip)
      expect(overlay.style.width).toBe('225px');  // 150 * 1.5
      expect(overlay.style.height).toBe('45px');  // 30 * 1.5
    });
  });

  describe('Color Coding', () => {
    it('should have green border for a REVIEWED field (bd g63j)', () => {
      // Green is human sign-off only: a machine-clean field is not enough.
      const field = createMockField({
        spoken_name: 'Complete Field',
        help: { instructions: 'Help text' },
        _review: { status: 'reviewed_correct' },
      });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('rgb(74, 222, 128)'); // green-400
    });

    it('should have YELLOW border for an un-reviewed but clean field (bd g63j)', () => {
      // The maintainer's directive: nobody has looked at this field, so the
      // overlay must not tell them it is done.
      const field = createMockField({
        spoken_name: 'Complete Field',
        help: { instructions: 'Help text' },
      });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('rgb(250, 204, 21)'); // yellow-400
    });

    it('should have yellow border for field needing review', () => {
      const field = createMockField({
        spoken_name: '', // Missing spoken name = needs review
      });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('rgb(250, 204, 21)'); // yellow-400
    });

    it('should have red border for field with errors', () => {
      const field = createMockField({
        id: '', // Missing ID = error
      });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('rgb(248, 113, 113)'); // red-400
    });

    it('should turn a reviewed_correct auto-amber field green (bd u8t6)', () => {
      // Missing spoken name = auto-amber; the sign-off must green the overlay
      // to agree with the FieldList row, not leave it yellow.
      const field = createMockField({
        spoken_name: '',
        _review: { status: 'reviewed_correct' },
      });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('rgb(74, 222, 128)'); // green-400
    });

    it('should keep a real ERROR field red even when reviewed_correct (bd u8t6)', () => {
      const field = createMockField({
        id: '', // missing id = local ERROR
        _review: { status: 'reviewed_correct' },
      });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('rgb(248, 113, 113)'); // red-400
    });

    it('should show a needs_followup field in the yellow band (bd u8t6)', () => {
      const field = createMockField({
        // otherwise auto-complete; the human flag alone drives the color
        _review: { status: 'needs_followup' },
      });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('rgb(250, 204, 21)'); // yellow-400
    });

    it('should have thicker border when selected', () => {
      const field = createMockField();

      const { container, rerender } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      let overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('2px'); // Normal width

      rerender(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={true}
        />
      );

      overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('4px'); // Thicker when selected
    });
  });

  describe('Hover Behavior', () => {
    it('should show tooltip on hover', async () => {
      const field = createMockField({ spoken_name: 'My Field' });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;

      // Before hover - no tooltip
      expect(container.querySelector('.field-label-tooltip')).not.toBeInTheDocument();

      // Hover
      fireEvent.mouseEnter(overlay);

      // After hover - tooltip appears
      const tooltip = container.querySelector('.field-label-tooltip');
      expect(tooltip).toBeInTheDocument();
      expect(tooltip).toHaveTextContent('My Field');
      expect(tooltip).toHaveTextContent('[text]'); // Field type
    });

    it('should hide tooltip on mouse leave', () => {
      const field = createMockField();

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;

      // Hover
      fireEvent.mouseEnter(overlay);
      expect(container.querySelector('.field-label-tooltip')).toBeInTheDocument();

      // Leave
      fireEvent.mouseLeave(overlay);
      expect(container.querySelector('.field-label-tooltip')).not.toBeInTheDocument();
    });

    it('should call onMouseEnter callback', () => {
      const handleMouseEnter = vi.fn();
      const field = createMockField();

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
          onMouseEnter={handleMouseEnter}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      fireEvent.mouseEnter(overlay);

      expect(handleMouseEnter).toHaveBeenCalledTimes(1);
    });

    it('should call onMouseLeave callback', () => {
      const handleMouseLeave = vi.fn();
      const field = createMockField();

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
          onMouseLeave={handleMouseLeave}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      fireEvent.mouseLeave(overlay);

      expect(handleMouseLeave).toHaveBeenCalledTimes(1);
    });
  });

  describe('Click Handling', () => {
    it('should call onClick callback when clicked', () => {
      const handleClick = vi.fn();
      const field = createMockField();

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
          onClick={handleClick}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      fireEvent.click(overlay);

      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('should have pointer cursor', () => {
      const field = createMockField();

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.cursor).toBe('pointer');
    });
  });

  describe('Accessibility', () => {
    it('should have title attribute with field name', () => {
      const field = createMockField({ spoken_name: 'Accessible Field' });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.title).toBe('Accessible Field');
    });

    it('should have data-field-id attribute', () => {
      const field = createMockField({ id: 'field-123' });

      const { container } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.getAttribute('data-field-id')).toBe('field-123');
    });

    it('should have data-testid for testing', () => {
      const field = createMockField({ id: 'field-123' });

      render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      expect(screen.getByTestId('field-overlay-field-123')).toBeInTheDocument();
    });
  });

  describe('Z-Index Layering', () => {
    it('should have higher z-index when selected', () => {
      const field = createMockField();

      const { container, rerender } = render(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={false}
        />
      );

      let overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.zIndex).toBe('10');

      rerender(
        <FieldOverlay
          field={field}
          pageHeight={mockPageHeight}
          scale={mockScale}
          isSelected={true}
        />
      );

      overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.zIndex).toBe('20');
    });
  });
});
