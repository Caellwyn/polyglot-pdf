/**
 * FieldOverlay option-rect painting + show_if dimming (bd polyglot-pdf-lp5v,
 * epic rubric R1 vitest half + R4).
 */
import { describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import { FieldOverlay } from './FieldOverlay';
import type { FormField } from '../schema-forms/types/schema';

afterEach(() => cleanup());

const rect = (y: number) => ({ page: 3, x: 344, y, width: 10, height: 10 });

const radioWithRects: FormField = {
  id: 'eth',
  name: 'Ethnicity',
  spoken_name: 'ethnicity',
  section_id: 's1',
  type: 'radio',
  pdf_position: rect(100),
  options: [
    { value: 'hispanic', label: 'Hispanic or Latino', pdf_position: rect(100) },
    { value: 'not_hispanic', label: 'Not Hispanic or Latino', pdf_position: rect(120) },
  ],
} as any;

const radioWithoutRects: FormField = {
  ...radioWithRects,
  options: [
    { value: 'hispanic', label: 'Hispanic or Latino' },
    { value: 'not_hispanic', label: 'Not Hispanic or Latino' },
  ],
} as any;

describe('FieldOverlay option-rect painting', () => {
  it('paints a mark at the selected option own rect, not a label at the field rect', () => {
    render(
      <FieldOverlay field={radioWithRects} rawValue="not_hispanic" fillState="filled" scale={2} />
    );
    const mark = screen.getByTestId('pdf-option-mark-eth-not_hispanic');
    // Option rect (x=344, y=120, 10x10) at scale 2.
    expect(mark.style.left).toBe('688px');
    expect(mark.style.top).toBe('240px');
    expect(mark.style.width).toBe('20px');
    expect(mark.textContent).toBe('X');
    // The field-level state box stays (snap-to anchor), but paints NO label.
    const box = screen.getByTestId('pdf-field-overlay-eth');
    expect(box.getAttribute('data-field-id')).toBe('eth');
    expect(box.textContent).toBe('');
    // Only the selected option gets a mark.
    expect(screen.queryByTestId('pdf-option-mark-eth-hispanic')).toBeNull();
  });

  it('falls back to the label at the field-level rect when options carry no rects', () => {
    render(
      <FieldOverlay field={radioWithoutRects} rawValue="not_hispanic" fillState="filled" scale={1} />
    );
    expect(screen.queryByTestId('pdf-option-mark-eth-not_hispanic')).toBeNull();
    expect(screen.getByTestId('pdf-field-overlay-eth').textContent).toBe(
      'Not Hispanic or Latino'
    );
  });

  it('paints one mark per selected checkbox_group option', () => {
    const group: FormField = {
      ...radioWithRects,
      id: 'race',
      type: 'checkbox_group',
      options: [
        { value: 'white', label: 'White', pdf_position: rect(100) },
        { value: 'asian', label: 'Asian', pdf_position: rect(120) },
        { value: 'other', label: 'Other', pdf_position: rect(140) },
      ],
    } as any;
    render(
      <FieldOverlay field={group} rawValue={['white', 'other']} fillState="confirmed" scale={1} />
    );
    expect(screen.getByTestId('pdf-option-mark-race-white')).toBeTruthy();
    expect(screen.getByTestId('pdf-option-mark-race-other')).toBeTruthy();
    expect(screen.queryByTestId('pdf-option-mark-race-asian')).toBeNull();
  });
});

describe('FieldOverlay dimming (show_if hidden)', () => {
  it('renders dimmed: dimmed class + dashed border replace the fill-state styling', () => {
    render(
      <FieldOverlay field={radioWithoutRects} rawValue="" fillState="empty" scale={1} dimmed />
    );
    const box = screen.getByTestId('pdf-field-overlay-eth');
    expect(box.className).toContain('pdf-field-overlay--dimmed');
    expect(box.getAttribute('data-dimmed')).toBe('true');
    expect(box.style.border).toContain('dashed');
  });

  it('current wins over dimmed: the voice-model field is never dimmed', () => {
    render(
      <FieldOverlay field={radioWithoutRects} rawValue="" fillState="current" scale={1} dimmed />
    );
    const box = screen.getByTestId('pdf-field-overlay-eth');
    expect(box.className).not.toContain('pdf-field-overlay--dimmed');
    expect(box.getAttribute('data-dimmed')).toBeNull();
    expect(box.style.border).toContain('solid');
  });

  it('dims the option marks along with the field box', () => {
    render(
      <FieldOverlay field={radioWithRects} rawValue="hispanic" fillState="filled" scale={1} dimmed />
    );
    expect(screen.getByTestId('pdf-option-mark-eth-hispanic').className).toContain(
      'pdf-field-overlay--dimmed'
    );
  });
});
