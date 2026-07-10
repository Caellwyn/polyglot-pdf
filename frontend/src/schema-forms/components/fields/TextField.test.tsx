/**
 * Unit tests for TextField component
 * Tests Bug 1: Manual Entry Shows [object Object]
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { TextField } from './TextField';
import type { FormField, FieldValue } from '../../types/schema';

describe('TextField - Bug 1: [object Object] Fix', () => {
  afterEach(() => {
    cleanup();
  });

  const mockField: FormField = {
    id: 'test-field',
    name: 'Test Field',
    spoken_name: 'test field',
    type: 'text',
    section_id: 'section-1',
  };

  describe('Value Unwrapping', () => {
    it('should display primitive string value correctly', () => {
      const onChange = vi.fn();
      render(
        <TextField field={mockField} value="John Doe" onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.value).toBe('John Doe');
    });

    it('should unwrap FieldValue object and display value property', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: 'Jane Smith',
        confirmed: true,
        lastModified: Date.now(),
      };

      render(
        <TextField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.value).toBe('Jane Smith');
      expect(input.value).not.toBe('[object Object]');
    });

    it('should handle null value', () => {
      const onChange = vi.fn();
      render(
        <TextField field={mockField} value={null} onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.value).toBe('');
    });

    it('should handle undefined value', () => {
      const onChange = vi.fn();
      render(
        <TextField field={mockField} value={undefined} onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.value).toBe('');
    });

    it('should handle empty string value', () => {
      const onChange = vi.fn();
      render(
        <TextField field={mockField} value="" onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.value).toBe('');
    });

    it('should handle FieldValue with null value property', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: null,
        confirmed: false,
      };

      render(
        <TextField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.value).toBe('');
    });
  });

  describe('User Input', () => {
    it('should call onChange with new value when user types', () => {
      const onChange = vi.fn();
      render(
        <TextField field={mockField} value="" onChange={onChange} />
      );

      const input = screen.getByRole('textbox');
      fireEvent.change(input, { target: { value: 'New Text' } });

      expect(onChange).toHaveBeenCalledWith('New Text');
    });

    it('should allow editing when value is FieldValue object', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: 'Initial',
        confirmed: true,
      };

      render(
        <TextField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const input = screen.getByRole('textbox');
      fireEvent.change(input, { target: { value: 'Updated' } });

      expect(onChange).toHaveBeenCalledWith('Updated');
    });
  });

  describe('Field Types', () => {
    it('should render email type correctly', () => {
      const onChange = vi.fn();
      const emailField: FormField = { ...mockField, type: 'email' };

      render(
        <TextField field={emailField} value="test@example.com" onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.type).toBe('email');
      expect(input.value).toBe('test@example.com');
    });

    it('should render tel type correctly', () => {
      const onChange = vi.fn();
      const telField: FormField = { ...mockField, type: 'tel' };

      render(
        <TextField field={telField} value="555-1234" onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.type).toBe('tel');
      expect(input.value).toBe('555-1234');
    });
  });

  describe('required prop (bd eaof: dynamic require_if state)', () => {
    it('shows the asterisk when required=true even if validation.required is falsy', () => {
      const onChange = vi.fn();
      render(
        <TextField field={mockField} value="" onChange={onChange} required={true} />
      );

      expect(document.querySelector('.form-field__required')).toBeTruthy();
    });

    it('suppresses the asterisk when required=false even if validation.required is true', () => {
      const onChange = vi.fn();
      const requiredField: FormField = { ...mockField, validation: { required: true } };

      render(
        <TextField field={requiredField} value="" onChange={onChange} required={false} />
      );

      expect(document.querySelector('.form-field__required')).toBeNull();
    });

    it('falls back to static validation.required when the prop is omitted', () => {
      const onChange = vi.fn();
      const requiredField: FormField = { ...mockField, validation: { required: true } };

      render(
        <TextField field={requiredField} value="" onChange={onChange} />
      );

      expect(document.querySelector('.form-field__required')).toBeTruthy();
    });

    it('shows no asterisk when the prop is omitted and validation.required is falsy', () => {
      const onChange = vi.fn();

      render(
        <TextField field={mockField} value="" onChange={onChange} />
      );

      expect(document.querySelector('.form-field__required')).toBeNull();
    });
  });

  describe('Edge Cases', () => {
    it('should handle numeric string value', () => {
      const onChange = vi.fn();
      render(
        <TextField field={mockField} value="12345" onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      expect(input.value).toBe('12345');
    });

    it('should handle FieldValue with boolean value (edge case)', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: true,
        confirmed: true,
      };

      render(
        <TextField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const input = screen.getByRole('textbox') as HTMLInputElement;
      // Boolean should be converted to string
      expect(input.value).toBe('true');
    });
  });
});
