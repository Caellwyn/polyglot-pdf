// Tests for the standalone preview conditional-visibility evaluator (bd
// polyglot-pdf-s4dp.4). These pin parity with the voice runtime's shouldShowField
// (frontend/src/schema-forms/utils/validation.ts) for the operators the preview
// exercises -- a field hides/shows correctly as its controlling field changes.

import { describe, it, expect } from 'vitest';
import { shouldShowField, evaluateCondition } from './conditionalVisibility';
import type { FormField } from '../types/schema';

function field(partial: Partial<FormField> & { id: string }): FormField {
  return {
    name: partial.id, type: 'text', pdf_field_name: `${partial.id}[0]`,
    read_only: false, required: false, ...partial,
  };
}

const radio = field({ id: 'trigger', type: 'radio', options: [
  { value: 'a', label: 'A' }, { value: 'b', label: 'B' },
] });
const checkboxGroup = field({ id: 'cbg', type: 'checkbox', options: [
  { value: 'x', label: 'X' }, { value: 'y', label: 'Y' },
] });
const fields = [radio, checkboxGroup];

describe('shouldShowField (no show_if)', () => {
  it('shows a field with no show_if and not hidden', () => {
    expect(shouldShowField(field({ id: 'f' }), {}, fields)).toBe(true);
  });
  it('hides a field with no show_if but hidden=true', () => {
    expect(shouldShowField(field({ id: 'f', hidden: true }), {}, fields)).toBe(false);
  });
});

describe('equals / not_equals (scalar radio trigger)', () => {
  const dep = field({ id: 'dep', show_if: { field: 'trigger', operator: 'equals', value: 'a' } });
  it('shows when the radio equals the value', () => {
    expect(shouldShowField(dep, { trigger: 'a' }, fields)).toBe(true);
  });
  it('hides when the radio holds a different value', () => {
    expect(shouldShowField(dep, { trigger: 'b' }, fields)).toBe(false);
  });
  it('hides when the radio is unset', () => {
    expect(shouldShowField(dep, {}, fields)).toBe(false);
  });
  it('not_equals is the inverse', () => {
    const d = field({ id: 'd', show_if: { field: 'trigger', operator: 'not_equals', value: 'a' } });
    expect(shouldShowField(d, { trigger: 'a' }, fields)).toBe(false);
    expect(shouldShowField(d, { trigger: 'b' }, fields)).toBe(true);
  });
});

describe('checkbox-group trigger compares by MEMBERSHIP', () => {
  const dep = field({ id: 'dep', show_if: { field: 'cbg', operator: 'equals', value: 'x' } });
  it('equals: true when x is among the selected array', () => {
    expect(shouldShowField(dep, { cbg: ['x', 'y'] }, fields)).toBe(true);
    expect(shouldShowField(dep, { cbg: ['y'] }, fields)).toBe(false);
    expect(shouldShowField(dep, { cbg: [] }, fields)).toBe(false);
  });
  it('not_equals: true when x is NOT among the selected array', () => {
    const d = field({ id: 'd', show_if: { field: 'cbg', operator: 'not_equals', value: 'x' } });
    expect(shouldShowField(d, { cbg: ['y'] }, fields)).toBe(true);
    expect(shouldShowField(d, { cbg: ['x'] }, fields)).toBe(false);
  });
  it('splits a comma-joined string ONLY for a checkbox-group trigger', () => {
    expect(evaluateCondition({ field: 'cbg', operator: 'equals', value: 'y' }, { cbg: 'x,y' }, fields)).toBe(true);
    // a scalar text trigger with a comma is NOT split (e.g. "Springfield, IL")
    const textTrigger = field({ id: 't', type: 'text' });
    expect(evaluateCondition({ field: 't', operator: 'equals', value: 'IL' }, { t: 'Springfield, IL' }, [textTrigger])).toBe(false);
  });
});

describe('is_checked / is_empty / is_not_empty', () => {
  it('is_checked: single boolean checkbox', () => {
    const single = field({ id: 's', type: 'checkbox' });
    const dep = field({ id: 'd', show_if: { field: 's', operator: 'is_checked' } });
    expect(shouldShowField(dep, { s: true }, [single])).toBe(true);
    expect(shouldShowField(dep, { s: false }, [single])).toBe(false);
    expect(shouldShowField(dep, {}, [single])).toBe(false);
  });
  it('is_checked: checkbox group is "any selected"', () => {
    const dep = field({ id: 'd', show_if: { field: 'cbg', operator: 'is_checked' } });
    expect(shouldShowField(dep, { cbg: ['x'] }, fields)).toBe(true);
    expect(shouldShowField(dep, { cbg: [] }, fields)).toBe(false);
  });
  it('is_empty / is_not_empty on a text value', () => {
    const t = field({ id: 't', type: 'text' });
    const empty = field({ id: 'e', show_if: { field: 't', operator: 'is_empty' } });
    const notEmpty = field({ id: 'n', show_if: { field: 't', operator: 'is_not_empty' } });
    expect(shouldShowField(empty, { t: '' }, [t])).toBe(true);
    expect(shouldShowField(empty, { t: 'hi' }, [t])).toBe(false);
    expect(shouldShowField(notEmpty, { t: 'hi' }, [t])).toBe(true);
    expect(shouldShowField(notEmpty, {}, [t])).toBe(false);
  });
  it('is_empty / is_not_empty on a checkbox-group array', () => {
    const empty = field({ id: 'e', show_if: { field: 'cbg', operator: 'is_empty' } });
    const notEmpty = field({ id: 'n', show_if: { field: 'cbg', operator: 'is_not_empty' } });
    expect(shouldShowField(empty, { cbg: [] }, fields)).toBe(true);
    expect(shouldShowField(empty, { cbg: ['x'] }, fields)).toBe(false);
    expect(shouldShowField(notEmpty, { cbg: ['x'] }, fields)).toBe(true);
  });
});

describe('contains / greater_than / less_than / in / not_in', () => {
  const t = field({ id: 't', type: 'text' });
  const n = field({ id: 'n', type: 'number' });
  it('contains: substring on text, membership on array', () => {
    expect(evaluateCondition({ field: 't', operator: 'contains', value: 'oo' }, { t: 'food' }, [t])).toBe(true);
    expect(evaluateCondition({ field: 'cbg', operator: 'contains', value: 'x' }, { cbg: ['x'] }, fields)).toBe(true);
  });
  it('greater_than / less_than coerce to number', () => {
    expect(evaluateCondition({ field: 'n', operator: 'greater_than', value: 5 }, { n: '10' }, [n])).toBe(true);
    expect(evaluateCondition({ field: 'n', operator: 'less_than', value: 5 }, { n: '10' }, [n])).toBe(false);
  });
  it('in / not_in require an array value', () => {
    expect(evaluateCondition({ field: 't', operator: 'in', value: ['a', 'b'] }, { t: 'b' }, [t])).toBe(true);
    expect(evaluateCondition({ field: 't', operator: 'in', value: ['a', 'b'] }, { t: 'c' }, [t])).toBe(false);
    expect(evaluateCondition({ field: 't', operator: 'not_in', value: ['a', 'b'] }, { t: 'c' }, [t])).toBe(true);
    // a non-array value -> in is false, not_in is false (matches runtime)
    expect(evaluateCondition({ field: 't', operator: 'in', value: 'a' }, { t: 'a' }, [t])).toBe(false);
    expect(evaluateCondition({ field: 't', operator: 'not_in', value: 'a' }, { t: 'a' }, [t])).toBe(false);
  });
});
