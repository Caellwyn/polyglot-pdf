/**
 * ID mode for FieldOverlay (bd polyglot-pdf-w70y).
 *
 * The overlay normally draws a coloured box per widget. In ID mode it draws the
 * field's ID over the widget instead, so a reviewer can see at a glance that
 * (say) "applicant_signature_date" is sitting on the printed phone-number box --
 * a field<->widget misassignment that no automated gate can detect, because the
 * claimed widget is real and claimed exactly once, just wrong.
 *
 * jsdom has no layout engine, so truncation and the text halo can only be pinned
 * as CSS contracts here, not as observed rendering. Stated so nobody reads these
 * as proof the label visually clips.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { FieldOverlay } from './FieldOverlay';
import type { FormField } from '../types/schema';

const PAGE_HEIGHT = 792; // US Letter

const createMockField = (overrides?: Partial<FormField>): FormField => ({
  id: 'test-field',
  name: 'Test Field',
  type: 'text',
  pdf_field_name: 'test_field',
  read_only: false,
  spoken_name: 'Test Field',
  help: { instructions: 'Fill this out' },
  pdf_position: { page: 1, x: 100, y: 700, width: 150, height: 30 },
  ...overrides,
});

const renderOverlay = (props: {
  field: FormField;
  scale?: number;
  isSelected?: boolean;
  showFieldId?: boolean;
  onClick?: () => void;
}) =>
  render(
    <FieldOverlay
      field={props.field}
      pageHeight={PAGE_HEIGHT}
      scale={props.scale ?? 1.0}
      isSelected={props.isSelected ?? false}
      showFieldId={props.showFieldId}
      onClick={props.onClick}
    />,
  );

describe('FieldOverlay -- ID mode', () => {
  describe('what gets drawn', () => {
    it('draws no label when showFieldId is omitted (default OFF)', () => {
      const { container } = renderOverlay({ field: createMockField() });
      expect(container.querySelector('.field-id-label')).toBeNull();
      // ...and the box is unchanged: full 2px border, as box mode has always had.
      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('2px');
    });

    it('draws the field ID -- not the spoken name -- when ON', () => {
      const field = createMockField({
        id: 'field_taxpayer_ssn',
        spoken_name: 'Social Security Number',
      });
      const { container, queryByText } = renderOverlay({
        field,
        showFieldId: true,
      });
      const label = container.querySelector('.field-id-label') as HTMLElement;
      expect(label.textContent).toBe('field_taxpayer_ssn');
      // The spoken name stays hover-only; it is too long for dense forms.
      expect(queryByText('Social Security Number')).toBeNull();
    });
  });

  describe('sizing follows the widget, and therefore zoom', () => {
    // Parsed rather than string-compared: 30 * 0.72 is 21.599999999999998 in
    // IEEE floats, and pinning that literal would be pinning float noise.
    const fontPx = (field: FormField, scale?: number) => {
      const { container } = renderOverlay({ field, showFieldId: true, scale });
      const label = container.querySelector('.field-id-label') as HTMLElement;
      return parseFloat(label.style.fontSize);
    };

    it('derives the font size from the box height', () => {
      expect(fontPx(createMockField())).toBeCloseTo(21.6, 5);  // 30 * 0.72
    });

    it('scales with zoom WITHOUT a scale term in the formula', () => {
      // screenPos is already multiplied by scale, so the label tracks zoom for
      // free. This fails if anyone reintroduces a `* scale` or clamps the size.
      expect(fontPx(createMockField(), 2.0)).toBeCloseTo(43.2, 5);
    });
  });

  describe('suppression when the box is too small to read', () => {
    it('draws NO label below the legibility floor, keeping the full box', () => {
      // 8pt tall -> 5.76px, under the 6px floor. Checkboxes look like this.
      const field = createMockField({
        pdf_position: { page: 1, x: 100, y: 700, width: 10, height: 8 },
      });
      const { container } = renderOverlay({ field, showFieldId: true });
      expect(container.querySelector('.field-id-label')).toBeNull();
      // The box is the fallback marker, so it must stay FULL width, not the
      // 1px hairline a labelled widget gets -- otherwise it nearly vanishes.
      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.border).toContain('2px');
    });

    it('restores the label once zoom makes it legible', () => {
      // The same 8pt field at 2x is 11.5px -- comfortably over the floor. This
      // is what makes suppression acceptable rather than lossy, and it fails if
      // suppression is ever computed from the UNSCALED pdf_position.
      const field = createMockField({
        pdf_position: { page: 1, x: 100, y: 700, width: 10, height: 8 },
      });
      const { container } = renderOverlay({
        field, showFieldId: true, scale: 2.0,
      });
      expect(container.querySelector('.field-id-label')).not.toBeNull();
    });
  });

  describe('horizontal overflow', () => {
    it('does NOT recover truncation by zooming -- the overflow ratio is fixed', () => {
      // Box width and font size both scale linearly with zoom, so a label cut at
      // 100% is cut IDENTICALLY at 300%. Zoom is the escape hatch for
      // SUPPRESSION only; hover is the recovery path for truncation. Pinned
      // because the opposite was asserted in a comment and believed until it was
      // measured in a browser (16% of f1040 labels truncate, 64% on i-90).
      const field = createMockField({
        id: 'p6_line4_interpreters_daytime_phone_number',
        pdf_position: { page: 1, x: 100, y: 700, width: 40, height: 30 },
      });
      const ratioAt = (scale: number) => {
        const { container } = renderOverlay({ field, showFieldId: true, scale });
        const label = container.querySelector('.field-id-label') as HTMLElement;
        // jsdom reports 0 for both, so compare the DECLARED geometry instead:
        // chars-that-fit is width / (0.6 * fontSize), and both terms carry the
        // same scale factor, so the quotient must be scale-independent.
        const fontPx = parseFloat(label.style.fontSize);
        const boxPx = parseFloat((container.querySelector('.field-overlay') as HTMLElement).style.width);
        return boxPx / (0.6 * fontPx);
      };
      expect(ratioAt(3.0)).toBeCloseTo(ratioAt(1.0), 5);
    });

    it('pins the truncation CSS contract (jsdom cannot observe clipping)', () => {
      const field = createMockField({
        id: 'p6_line4_interpreters_daytime_phone_number',
        pdf_position: { page: 1, x: 100, y: 700, width: 40, height: 30 },
      });
      const { container } = renderOverlay({ field, showFieldId: true });
      const label = container.querySelector('.field-id-label') as HTMLElement;
      expect(label.style.overflow).toBe('hidden');
      expect(label.style.whiteSpace).toBe('nowrap');
      expect(label.style.textOverflow).toBe('ellipsis');
      // NOT a flex container: textOverflow silently no-ops on one, which would
      // leave this assertion passing while real truncation was broken.
      expect(label.style.display).not.toBe('flex');
    });
  });

  describe('status colour is carried on the text', () => {
    const labelColor = (field: FormField) => {
      const { container } = renderOverlay({ field, showFieldId: true });
      // An error field has an empty id, so its data-testid is degenerate --
      // query by class, which is stable across every case here.
      return (container.querySelector('.field-id-label') as HTMLElement).style.color;
    };

    it('is green for a field a human signed off', () => {
      expect(labelColor(createMockField({
        _review: { status: 'reviewed_correct' },
      } as Partial<FormField>))).toBe('rgb(21, 128, 61)');
    });

    it('is amber for an un-reviewed field', () => {
      expect(labelColor(createMockField())).toBe('rgb(161, 98, 7)');
    });

    it('is red for a broken field even when marked reviewed-correct', () => {
      // Red always wins: a sign-off never greens a field with a real error.
      // An empty id is the error shape the existing suite already uses.
      const broken = createMockField({
        id: '',
        _review: { status: 'reviewed_correct' },
      } as Partial<FormField>);
      expect(labelColor(broken)).toBe('rgb(185, 28, 28)');
    });

    it('keeps the box border and the label in the SAME status band', () => {
      // The anti-drift test: both modes must read one colour source, so a
      // reviewer never sees a green box labelled in amber.
      const field = createMockField({
        _review: { status: 'reviewed_correct' },
      } as Partial<FormField>);
      const box = renderOverlay({ field });
      const boxBorder = (box.container.querySelector('.field-overlay') as HTMLElement)
        .style.border;
      expect(boxBorder).toContain('rgb(74, 222, 128)');   // green-400 border
      expect(labelColor(field)).toBe('rgb(21, 128, 61)'); // green-700 text
    });
  });

  describe('existing behaviour survives ID mode', () => {
    it('still shows the spoken-name tooltip on hover', () => {
      // Depends on pointerEvents:none on the label -- without it the label
      // becomes the hover target and the overlay's non-bubbling mouseenter
      // never fires.
      const field = createMockField({ spoken_name: 'Given Name' });
      const { container } = renderOverlay({ field, showFieldId: true });
      const overlay = container.querySelector('.field-overlay') as HTMLElement;

      fireEvent.mouseEnter(overlay);

      const tooltip = container.querySelector('.field-label-tooltip');
      expect(tooltip).not.toBeNull();
      expect(tooltip!.textContent).toContain('Given Name');
    });

    it('keeps the label out of the pointer path', () => {
      const { container } = renderOverlay({
        field: createMockField(), showFieldId: true,
      });
      const label = container.querySelector('.field-id-label') as HTMLElement;
      expect(label.style.pointerEvents).toBe('none');
    });

    it('still selects the field on click', () => {
      const onClick = vi.fn();
      const { container } = renderOverlay({
        field: createMockField(), showFieldId: true, onClick,
      });
      fireEvent.click(container.querySelector('.field-overlay') as HTMLElement);
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('keeps the blue selection glow', () => {
      const { container } = renderOverlay({
        field: createMockField(), showFieldId: true, isSelected: true,
      });
      const overlay = container.querySelector('.field-overlay') as HTMLElement;
      expect(overlay.style.boxShadow).toContain('rgba(59, 130, 246');
    });
  });
});
