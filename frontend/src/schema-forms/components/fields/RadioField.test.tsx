/**
 * Unit tests for RadioField component
 * Tests Bug 1: Manual Entry Shows [object Object]
 * Tests Bug 2: Radio Buttons Reset Form (state preservation)
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RadioField } from './RadioField';
import type { FormField, FieldValue } from '../../types/schema';

describe('RadioField - Bug 1 & 2 Fixes', () => {
  const mockField: FormField = {
    id: 'gender-field',
    name: 'Gender',
    spoken_name: 'gender',
    type: 'radio',
    section_id: 'section-1',
    options: [
      { value: 'male', label: 'Male' },
      { value: 'female', label: 'Female' },
      { value: 'other', label: 'Other' },
    ],
  };

  describe('Bug 1: Value Unwrapping', () => {
    it('should display primitive string value correctly', () => {
      const onChange = vi.fn();
      render(
        <RadioField field={mockField} value="male" onChange={onChange} />
      );

      const maleRadio = screen.getByLabelText('Male') as HTMLInputElement;
      expect(maleRadio.checked).toBe(true);
    });

    it('should unwrap FieldValue object and check correct radio', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: 'female',
        confirmed: true,
        lastModified: Date.now(),
      };

      const { container } = render(
        <RadioField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const radios = container.querySelectorAll('input[type="radio"]');
      const femaleRadio = Array.from(radios).find(r => (r as HTMLInputElement).value === 'female') as HTMLInputElement;
      const maleRadio = Array.from(radios).find(r => (r as HTMLInputElement).value === 'male') as HTMLInputElement;

      expect(femaleRadio.checked).toBe(true);
      expect(maleRadio.checked).toBe(false);
    });

    it('should handle null value (no radio checked)', () => {
      const onChange = vi.fn();
      render(
        <RadioField field={mockField} value={null} onChange={onChange} />
      );

      const maleRadio = screen.getByLabelText('Male') as HTMLInputElement;
      const femaleRadio = screen.getByLabelText('Female') as HTMLInputElement;
      const otherRadio = screen.getByLabelText('Other') as HTMLInputElement;

      expect(maleRadio.checked).toBe(false);
      expect(femaleRadio.checked).toBe(false);
      expect(otherRadio.checked).toBe(false);
    });

    it('should handle undefined value (no radio checked)', () => {
      const onChange = vi.fn();
      render(
        <RadioField field={mockField} value={undefined} onChange={onChange} />
      );

      const maleRadio = screen.getByLabelText('Male') as HTMLInputElement;
      expect(maleRadio.checked).toBe(false);
    });

    it('should handle FieldValue with null value property', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: null,
        confirmed: false,
      };

      render(
        <RadioField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const maleRadio = screen.getByLabelText('Male') as HTMLInputElement;
      expect(maleRadio.checked).toBe(false);
    });
  });

  describe('Bug 2: onChange Behavior (State Preservation)', () => {
    it('should call onChange with only the new value (not entire state)', () => {
      const onChange = vi.fn();
      render(
        <RadioField field={mockField} value="" onChange={onChange} />
      );

      const femaleRadio = screen.getByLabelText('Female');
      fireEvent.click(femaleRadio);

      // Should only pass the field value, not replace entire form state
      expect(onChange).toHaveBeenCalledWith('female');
      expect(onChange).toHaveBeenCalledTimes(1);

      // Verify onChange receives a primitive string, not an object
      const callArg = onChange.mock.calls[0][0];
      expect(typeof callArg).toBe('string');
    });

    it('should allow changing selection when value is FieldValue object', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: 'male',
        confirmed: true,
      };

      render(
        <RadioField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const otherRadio = screen.getByLabelText('Other');
      fireEvent.click(otherRadio);

      expect(onChange).toHaveBeenCalledWith('other');
      expect(typeof onChange.mock.calls[0][0]).toBe('string');
    });

    it('should trigger onBlur when radio changes', () => {
      const onChange = vi.fn();
      const onBlur = vi.fn();

      render(
        <RadioField
          field={mockField}
          value=""
          onChange={onChange}
          onBlur={onBlur}
        />
      );

      const maleRadio = screen.getByLabelText('Male');
      fireEvent.click(maleRadio);

      expect(onChange).toHaveBeenCalledWith('male');
      expect(onBlur).toHaveBeenCalled();
    });
  });

  describe('Radio Group Rendering', () => {
    it('should render all radio options', () => {
      const onChange = vi.fn();
      render(
        <RadioField field={mockField} value="" onChange={onChange} />
      );

      expect(screen.getByLabelText('Male')).toBeInTheDocument();
      expect(screen.getByLabelText('Female')).toBeInTheDocument();
      expect(screen.getByLabelText('Other')).toBeInTheDocument();
    });

    it('should only check one radio at a time', () => {
      const onChange = vi.fn();
      render(
        <RadioField field={mockField} value="female" onChange={onChange} />
      );

      const maleRadio = screen.getByLabelText('Male') as HTMLInputElement;
      const femaleRadio = screen.getByLabelText('Female') as HTMLInputElement;
      const otherRadio = screen.getByLabelText('Other') as HTMLInputElement;

      expect(femaleRadio.checked).toBe(true);
      expect(maleRadio.checked).toBe(false);
      expect(otherRadio.checked).toBe(false);
    });
  });
});
