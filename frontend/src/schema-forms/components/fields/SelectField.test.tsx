/**
 * Unit tests for SelectField component
 * Tests Bug 1: Manual Entry Shows [object Object]
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { SelectField } from './SelectField';
import type { FormField, FieldValue } from '../../types/schema';

describe('SelectField - Bug 1: [object Object] Fix', () => {
  afterEach(() => {
    cleanup();
  });

  const mockField: FormField = {
    id: 'state-field',
    name: 'State',
    spoken_name: 'state',
    type: 'select',
    section_id: 'section-1',
    options: [
      { value: 'CA', label: 'California' },
      { value: 'NY', label: 'New York' },
      { value: 'TX', label: 'Texas' },
    ],
  };

  describe('Value Unwrapping', () => {
    it('should display primitive string value correctly', () => {
      const onChange = vi.fn();
      render(
        <SelectField field={mockField} value="CA" onChange={onChange} />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('CA');
    });

    it('should unwrap FieldValue object and display value property', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: 'NY',
        confirmed: true,
        lastModified: Date.now(),
      };

      render(
        <SelectField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('NY');
      expect(select.value).not.toBe('[object Object]');
    });

    it('should handle null value', () => {
      const onChange = vi.fn();
      render(
        <SelectField field={mockField} value={null} onChange={onChange} />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('');
    });

    it('should handle undefined value', () => {
      const onChange = vi.fn();
      render(
        <SelectField field={mockField} value={undefined} onChange={onChange} />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('');
    });

    it('should handle FieldValue with null value property', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: null,
        confirmed: false,
      };

      render(
        <SelectField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('');
    });
  });

  describe('User Selection', () => {
    it('should call onChange with new value when user selects option', () => {
      const onChange = vi.fn();
      render(
        <SelectField field={mockField} value="" onChange={onChange} />
      );

      const select = screen.getByRole('combobox');
      fireEvent.change(select, { target: { value: 'TX' } });

      expect(onChange).toHaveBeenCalledWith('TX');
    });

    it('should allow changing selection when value is FieldValue object', () => {
      const onChange = vi.fn();
      const fieldValue: FieldValue = {
        value: 'CA',
        confirmed: true,
      };

      render(
        <SelectField field={mockField} value={fieldValue as any} onChange={onChange} />
      );

      const select = screen.getByRole('combobox');
      fireEvent.change(select, { target: { value: 'NY' } });

      expect(onChange).toHaveBeenCalledWith('NY');
    });
  });

  describe('Options Rendering', () => {
    it('should render all options correctly', () => {
      const onChange = vi.fn();
      render(
        <SelectField field={mockField} value="" onChange={onChange} />
      );

      expect(screen.getByText('California')).toBeTruthy();
      expect(screen.getByText('New York')).toBeTruthy();
      expect(screen.getByText('Texas')).toBeTruthy();
      expect(screen.getByText('-- Please select --')).toBeTruthy();
    });

    it('should have correct option selected when value matches', () => {
      const onChange = vi.fn();
      render(
        <SelectField field={mockField} value="NY" onChange={onChange} />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      const selectedOption = select.options[select.selectedIndex];
      expect(selectedOption.text).toBe('New York');
    });
  });
});
