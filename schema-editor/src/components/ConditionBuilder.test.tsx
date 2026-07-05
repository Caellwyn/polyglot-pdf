// Component tests for the composite condition builder (bd polyglot-pdf-h76m.9,
// P4.1). Cover the bead's exit criteria:
//   1. A contractor authors ALL[A,B] + NONE[C] entirely by dropdown/checklist
//      and the PreviewPane obeys the result live.
//   2. in/not_in rules are editable via an option multi-select checklist
//      (absorbs bd polyglot-pdf-jplx).
//   3. No UI path emits a value outside the trigger's option set.
// Plus the wire-shape rule (one all_of atom -> legacy single condition) and
// the malformed-condition read-only guard.

import { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { ConditionBuilder, operatorsForTrigger } from './ConditionBuilder';
import PreviewPane from './PreviewPane';
import type { FieldCondition, FormField, FormSchema } from '../types/schema';

function field(p: Partial<FormField> & { id: string }): FormField {
  return {
    name: p.id, type: 'text', pdf_field_name: `${p.id}[0]`,
    read_only: false, required: false, ...p,
  } as FormField;
}

const GROUP_A = field({
  id: 'grp_a', type: 'checkbox_group', spoken_name: 'group a',
  options: [
    { value: 'a1', label: 'Alpha One' },
    { value: 'a2', label: 'Alpha Two' },
  ],
});
const RADIO_B = field({
  id: 'radio_b', type: 'radio', spoken_name: 'radio b',
  options: [
    { value: 'b1', label: 'Beta One' },
    { value: 'b2', label: 'Beta Two' },
  ],
});
const CHECK_C = field({ id: 'check_c', type: 'checkbox', spoken_name: 'check c' });
const TEXT_D = field({ id: 'text_d', type: 'text', spoken_name: 'text d' });
const TARGET = field({ id: 'target', type: 'text', spoken_name: 'the target' });

function makeSchema(): FormSchema {
  const fields = [GROUP_A, RADIO_B, CHECK_C, TEXT_D, TARGET];
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T-1', total_widgets: fields.length,
      total_fields: fields.length, version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  };
}

// Controlled harness: the builder is a controlled component, so authoring
// flows re-render it with each emitted value, like FieldEditor does.
let lastCondition: FieldCondition | undefined;
function Harness({ initial }: { initial?: FieldCondition }) {
  const [condition, setCondition] = useState<FieldCondition | undefined>(initial);
  lastCondition = condition;
  return (
    <ConditionBuilder
      title="Shown when"
      condition={condition}
      selfId="target"
      schema={makeSchema()}
      onChange={(next) => {
        lastCondition = next;
        setCondition(next);
      }}
    />
  );
}

describe('ConditionBuilder: authoring ALL[A,B] + NONE[C] by dropdown/checklist (EC1)', () => {
  it('builds the composite entirely through selects and emits the canonical shape', () => {
    render(<Harness />);

    // Start: empty -> add the first ALL-of row (defaults to the first
    // triggerable field, grp_a, with its first valid operator `includes` and
    // its FIRST OPTION as value -- never an out-of-set value).
    fireEvent.click(screen.getByText(/\+ Add condition/));
    expect(lastCondition).toEqual({ field: 'grp_a', operator: 'includes', value: 'a1' });

    // Row 1: pick option Alpha Two on the group trigger.
    fireEvent.change(screen.getByLabelText('all_of row 1: value'), { target: { value: 'a2' } });
    expect(lastCondition).toEqual({ field: 'grp_a', operator: 'includes', value: 'a2' });

    // Add row 2 in ALL-of; retarget it to radio_b (operator auto-resets to a
    // valid one for the new trigger; value snaps into ITS option set).
    fireEvent.click(screen.getByLabelText('Add row: ALL of these are true'));
    fireEvent.change(screen.getByLabelText('all_of row 2: trigger field'), {
      target: { value: 'radio_b' },
    });
    fireEvent.change(screen.getByLabelText('all_of row 2: operator'), {
      target: { value: 'equals' },
    });
    fireEvent.change(screen.getByLabelText('all_of row 2: value'), { target: { value: 'b1' } });

    // Add the NONE-of row on the standalone checkbox (no-value operator).
    fireEvent.click(screen.getByLabelText('Add row: NONE of these are true'));
    fireEvent.change(screen.getByLabelText('none_of row 1: trigger field'), {
      target: { value: 'check_c' },
    });
    fireEvent.change(screen.getByLabelText('none_of row 1: operator'), {
      target: { value: 'is_checked' },
    });

    expect(lastCondition).toEqual({
      all_of: [
        { field: 'grp_a', operator: 'includes', value: 'a2' },
        { field: 'radio_b', operator: 'equals', value: 'b1' },
      ],
      none_of: [{ field: 'check_c', operator: 'is_checked' }],
    });

    // Plain-language summary line reflects the whole condition.
    const summary = screen.getByTestId('condition-summary-Shown when');
    expect(summary.textContent).toContain('group a has selected');
    expect(summary.textContent).toContain('NOT (check c is checked)');
  });

  it('the PreviewPane obeys the authored composite live', () => {
    const schema = makeSchema();
    schema.fields = schema.fields.map(f =>
      f.id === 'target'
        ? {
            ...f,
            label: 'Target Field',
            show_if: {
              all_of: [
                { field: 'grp_a', operator: 'includes', value: 'a2' },
                { field: 'radio_b', operator: 'equals', value: 'b1' },
              ],
              none_of: [{ field: 'check_c', operator: 'is_checked' }],
            },
          }
        : f,
    );
    render(<PreviewPane schema={schema} />);

    // Hidden until ALL-of is satisfied.
    expect(screen.queryByText('Target Field')).toBeNull();

    fireEvent.click(screen.getByLabelText('Alpha Two'));
    expect(screen.queryByText('Target Field')).toBeNull();
    fireEvent.click(screen.getByLabelText('Beta One'));
    expect(screen.queryByText('Target Field')).not.toBeNull();

    // NONE-of trips -> hides again.
    fireEvent.click(screen.getByLabelText('check c'));
    expect(screen.queryByText('Target Field')).toBeNull();
  });
});

describe('ConditionBuilder: in/not_in via option multi-select checklist (EC2, bd jplx)', () => {
  it('authors an in rule on a radio trigger through checkboxes only', () => {
    render(
      <Harness initial={{ field: 'radio_b', operator: 'equals', value: 'b1' }} />,
    );

    fireEvent.change(screen.getByLabelText('all_of row 1: operator'), {
      target: { value: 'in' },
    });
    // Operator switch coerces the scalar into a list; the checklist appears.
    const group = screen.getByRole('group', { name: 'all_of row 1: options' });
    fireEvent.click(within(group).getByLabelText('all_of row 1: option Beta One'));
    fireEvent.click(within(group).getByLabelText('all_of row 1: option Beta Two'));
    expect(lastCondition).toEqual({
      field: 'radio_b', operator: 'in', value: ['b1', 'b2'],
    });

    // Unticking removes from the list.
    fireEvent.click(within(group).getByLabelText('all_of row 1: option Beta One'));
    expect(lastCondition).toEqual({ field: 'radio_b', operator: 'in', value: ['b2'] });
  });

  it('an existing in rule loads editable (no read-only lockout)', () => {
    render(
      <Harness initial={{ field: 'radio_b', operator: 'in', value: ['b1'] }} />,
    );
    const beta1 = screen.getByLabelText('all_of row 1: option Beta One') as HTMLInputElement;
    expect(beta1.checked).toBe(true);
    expect(beta1.disabled).toBe(false);
  });
});

describe('ConditionBuilder: no UI path emits out-of-set values (EC3)', () => {
  it('choice triggers render ONLY option pickers -- no free-text input', () => {
    render(
      <Harness initial={{ field: 'grp_a', operator: 'includes', value: 'a1' }} />,
    );
    // The value control is a select whose options are exactly the trigger's.
    const valueSelect = screen.getByLabelText('all_of row 1: value') as HTMLSelectElement;
    expect(valueSelect.tagName).toBe('SELECT');
    expect(Array.from(valueSelect.options).map(o => o.value)).toEqual(['a1', 'a2']);
    expect(screen.queryByPlaceholderText('Expected value')).toBeNull();
  });

  it('retargeting a row onto a choice trigger snaps the value into its option set', () => {
    render(
      <Harness initial={{ field: 'text_d', operator: 'equals', value: 'free text' }} />,
    );
    fireEvent.change(screen.getByLabelText('all_of row 1: trigger field'), {
      target: { value: 'radio_b' },
    });
    // 'free text' is not a radio_b option -> snapped to the first option.
    expect(lastCondition).toEqual({ field: 'radio_b', operator: 'equals', value: 'b1' });
  });

  it('switching operator keeps only in-set members of a list value', () => {
    render(
      <Harness initial={{ field: 'radio_b', operator: 'in', value: ['b2', 'ghost'] }} />,
    );
    fireEvent.change(screen.getByLabelText('all_of row 1: operator'), {
      target: { value: 'not_in' },
    });
    expect(lastCondition).toEqual({ field: 'radio_b', operator: 'not_in', value: ['b2'] });
  });
});

describe('ConditionBuilder: wire-shape + guards', () => {
  it('exactly one ALL-of atom emits the LEGACY single-condition shape', () => {
    render(<Harness />);
    fireEvent.click(screen.getByText(/\+ Add condition/));
    expect(lastCondition).not.toHaveProperty('all_of');
    expect(lastCondition).toHaveProperty('field', 'grp_a');
  });

  it('removing the last row removes the condition key entirely', () => {
    render(
      <Harness initial={{ field: 'text_d', operator: 'is_not_empty' }} />,
    );
    fireEvent.click(screen.getByLabelText('Remove all_of row 1'));
    expect(lastCondition).toBeUndefined();
  });

  it('no-value operators render no value control', () => {
    render(
      <Harness initial={{ field: 'check_c', operator: 'is_checked' }} />,
    );
    expect(screen.queryByLabelText('all_of row 1: value')).toBeNull();
    expect(screen.queryByRole('group')).toBeNull();
  });

  it('the group-trigger operator dropdown offers membership operators, never equals', () => {
    render(
      <Harness initial={{ field: 'grp_a', operator: 'includes', value: 'a1' }} />,
    );
    const opSelect = screen.getByLabelText('all_of row 1: operator') as HTMLSelectElement;
    const ops = Array.from(opSelect.options).map(o => o.value);
    expect(ops).toContain('includes');
    expect(ops).toContain('not_includes');
    expect(ops).not.toContain('equals'); // v2: equals-on-group is retired vocabulary
  });

  it('an off-matrix operator on stored data still displays without being rewritten', () => {
    render(
      <Harness initial={{ field: 'grp_a', operator: 'equals', value: 'a1' }} />,
    );
    const opSelect = screen.getByLabelText('all_of row 1: operator') as HTMLSelectElement;
    expect(opSelect.value).toBe('equals'); // legacy rule shows itself
    expect(lastCondition).toEqual({ field: 'grp_a', operator: 'equals', value: 'a1' });
  });

  it('a malformed condition renders read-only with Remove as the only edit', () => {
    const onChange = vi.fn();
    render(
      <ConditionBuilder
        title="Shown when"
        condition={{ field: 'x', operator: 'equals', value: 'y', all_of: [] } as any}
        selfId="target"
        schema={makeSchema()}
        onChange={onChange}
      />,
    );
    expect(screen.getByText(/unrecognized shape/)).toBeTruthy();
    fireEvent.click(screen.getByText('Remove'));
    expect(onChange).toHaveBeenCalledWith(undefined);
  });
});

describe('operatorsForTrigger mirrors the backend v2 compat matrix', () => {
  it('per trigger type', () => {
    expect(operatorsForTrigger(GROUP_A)).toEqual(
      ['includes', 'not_includes', 'is_empty', 'is_not_empty'],
    );
    expect(operatorsForTrigger(CHECK_C)).toContain('is_checked');
    expect(operatorsForTrigger(CHECK_C)).not.toContain('includes');
    expect(operatorsForTrigger(TEXT_D)).toContain('contains');
    expect(operatorsForTrigger(TEXT_D)).not.toContain('is_checked');
    expect(operatorsForTrigger(field({ id: 'n', type: 'number' }))).toContain('greater_than');
    // Legacy checkbox-with-options counts as a group trigger.
    const legacyGroup = field({
      id: 'lg', type: 'checkbox',
      options: [{ value: 'x', label: 'X' }],
    });
    expect(operatorsForTrigger(legacyGroup)).toEqual(
      ['includes', 'not_includes', 'is_empty', 'is_not_empty'],
    );
  });
});

// Fresh-eyes round 1: a stored value referencing an option that no longer
// exists on the trigger must be SURFACED loudly (never silently rewritten,
// never rendered as an unresolvable select).
describe('ConditionBuilder: stale stored option values are surfaced (EC3 hardening)', () => {
  it('flags a scalar value whose option was removed from the trigger', () => {
    render(
      <Harness initial={{ field: 'radio_b', operator: 'equals', value: 'gone' }} />,
    );
    const valueSelect = screen.getByLabelText('all_of row 1: value') as HTMLSelectElement;
    expect(valueSelect.value).toBe('gone'); // still displayed, not silently snapped
    expect(screen.getByRole('alert').textContent).toContain("'gone'");
    // Picking a real option heals the rule.
    fireEvent.change(valueSelect, { target: { value: 'b2' } });
    expect(lastCondition).toEqual({ field: 'radio_b', operator: 'equals', value: 'b2' });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders stale list members as removable checklist entries', () => {
    render(
      <Harness initial={{ field: 'radio_b', operator: 'in', value: ['b1', 'ghost'] }} />,
    );
    const staleBox = screen.getByLabelText(
      'all_of row 1: option (missing option) ghost',
    ) as HTMLInputElement;
    expect(staleBox.checked).toBe(true);
    fireEvent.click(staleBox); // untick removes the orphan
    expect(lastCondition).toEqual({ field: 'radio_b', operator: 'in', value: ['b1'] });
  });
});

describe('PreviewPane: malformed checkbox_group with zero options', () => {
  it('shows the no-options notice instead of a lone-checkbox render', () => {
    const schema = makeSchema();
    schema.fields = schema.fields.map(f =>
      f.id === 'grp_a' ? { ...f, options: [] } : f,
    );
    render(<PreviewPane schema={schema} />);
    expect(screen.getByText('No options defined for this group.')).toBeTruthy();
  });
});
