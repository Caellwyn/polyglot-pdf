/**
 * Component tests for the controls_fields editing UI (bd polyglot-pdf-bjwy, A4).
 * Authoring a control round-trips into the canonical List[ConditionalControl]
 * shape (operator + value + action arrays of target field ids); editing and
 * removing work; and the ValidationPanel reference check stays consistent with
 * the list shape.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import { validateSchema } from '../utils/validation';
import type { FormSchema, FormField } from '../types/schema';

function field(partial: Partial<FormField> & { id: string }): FormField {
  return {
    name: partial.id,
    type: 'text',
    pdf_field_name: partial.id,
    read_only: false,
    required: false,
    ...partial,
  } as FormField;
}

function makeSchema(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Test', form_number: 'T-1', total_widgets: fields.length,
      total_fields: fields.length, version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  };
}

const TRIGGER = field({ id: 'has_other_name', type: 'checkbox', section_id: 's1' });
const TARGET_A = field({ id: 'other_family_name', section_id: 's1', spoken_name: 'Family name' });
const TARGET_B = field({ id: 'other_given_name', section_id: 's1' });

describe('FieldEditor controls_fields UI', () => {
  it('authoring a control round-trips into the canonical list shape', () => {
    const schema = makeSchema([TRIGGER, TARGET_A, TARGET_B]);
    const onUpdateField = vi.fn();
    render(<FieldEditor field={TRIGGER} schema={schema} onUpdateField={onUpdateField} />);

    // Add an (empty) control entry.
    fireEvent.click(screen.getByText('+ Add Control'));
    expect(onUpdateField).toHaveBeenLastCalledWith(
      expect.objectContaining({
        controls_fields: [{ operator: 'equals', value: '' }],
      })
    );
  });

  it('selecting a target field under an action adds it to that action array', () => {
    // Pre-seed one empty control so the action pickers render.
    const trigger = { ...TRIGGER, controls_fields: [{ operator: 'equals' as const, value: 'Yes' }] };
    const schema = makeSchema([trigger, TARGET_A, TARGET_B]);
    const onUpdateField = vi.fn();
    render(<FieldEditor field={trigger} schema={schema} onUpdateField={onUpdateField} />);

    // Find the "Unlocks" action group and check the TARGET_A box within it.
    const unlocksLabel = screen.getByText('Unlocks');
    const group = unlocksLabel.parentElement as HTMLElement;
    const targetRow = within(group).getByText('Family name').closest('label') as HTMLElement;
    fireEvent.click(within(targetRow).getByRole('checkbox'));

    expect(onUpdateField).toHaveBeenLastCalledWith(
      expect.objectContaining({
        controls_fields: [
          { operator: 'equals', value: 'Yes', unlocks: ['other_family_name'] },
        ],
      })
    );
  });

  it('changing operator and value edits the existing control in place', () => {
    const trigger = {
      ...TRIGGER,
      controls_fields: [{ operator: 'equals' as const, value: 'Yes', shows: ['other_given_name'] }],
    };
    const schema = makeSchema([trigger, TARGET_A, TARGET_B]);
    const onUpdateField = vi.fn();
    render(<FieldEditor field={trigger} schema={schema} onUpdateField={onUpdateField} />);

    fireEvent.change(screen.getByDisplayValue('Yes'), { target: { value: 'No' } });
    expect(onUpdateField).toHaveBeenLastCalledWith(
      expect.objectContaining({
        controls_fields: [{ operator: 'equals', value: 'No', shows: ['other_given_name'] }],
      })
    );
  });

  it('removing a control deletes the key when it was the only entry', () => {
    const trigger = {
      ...TRIGGER,
      controls_fields: [{ operator: 'equals' as const, value: 'Yes', shows: ['other_given_name'] }],
    };
    const schema = makeSchema([trigger, TARGET_A, TARGET_B]);
    const onUpdateField = vi.fn();
    render(<FieldEditor field={trigger} schema={schema} onUpdateField={onUpdateField} />);

    fireEvent.click(screen.getByText('Remove'));
    expect(onUpdateField).toHaveBeenLastCalledWith(
      expect.objectContaining({ controls_fields: undefined })
    );
  });

  it('unchecking the last target drops the action key', () => {
    const trigger = {
      ...TRIGGER,
      controls_fields: [{ operator: 'equals' as const, value: 'Yes', unlocks: ['other_family_name'] }],
    };
    const schema = makeSchema([trigger, TARGET_A, TARGET_B]);
    const onUpdateField = vi.fn();
    render(<FieldEditor field={trigger} schema={schema} onUpdateField={onUpdateField} />);

    const unlocksLabel = screen.getByText('Unlocks');
    const group = unlocksLabel.parentElement as HTMLElement;
    const targetRow = within(group).getByText('Family name').closest('label') as HTMLElement;
    fireEvent.click(within(targetRow).getByRole('checkbox')); // uncheck

    expect(onUpdateField).toHaveBeenLastCalledWith(
      expect.objectContaining({
        controls_fields: [{ operator: 'equals', value: 'Yes', unlocks: undefined }],
      })
    );
  });

  it('a pruned action key serializes out of the exported JSON (undefined, not null)', () => {
    // Backend ConditionalControl actions are Optional[List[str]] = None, so a
    // dropped action must be ABSENT in JSON, not present-as-null. JSON.stringify
    // elides undefined; this locks that the write path uses undefined.
    const trigger = {
      ...TRIGGER,
      controls_fields: [{ operator: 'equals' as const, value: 'Yes', unlocks: ['other_family_name'] }],
    };
    const schema = makeSchema([trigger, TARGET_A, TARGET_B]);
    let captured: FormField | null = null;
    const onUpdateField = vi.fn((f: FormField) => { captured = f; });
    render(<FieldEditor field={trigger} schema={schema} onUpdateField={onUpdateField} />);

    const unlocksLabel = screen.getByText('Unlocks');
    const group = unlocksLabel.parentElement as HTMLElement;
    const targetRow = within(group).getByText('Family name').closest('label') as HTMLElement;
    fireEvent.click(within(targetRow).getByRole('checkbox')); // uncheck the last target

    const json = JSON.stringify(captured!.controls_fields);
    expect(json).toBe('[{"operator":"equals","value":"Yes"}]');
    expect(json).not.toContain('unlocks');
    expect(json).not.toContain('null');
  });
});

describe('validation reference check for list-shaped controls_fields', () => {
  it('flags a control that targets a non-existent field', () => {
    const trigger = field({
      id: 'has_other_name',
      controls_fields: [{ operator: 'equals', value: 'Yes', unlocks: ['ghost_field'] }],
    });
    const schema = makeSchema([trigger, TARGET_A]);
    const errors = validateSchema(schema);
    const refError = errors.find(e =>
      e.message.includes('controls_fields references non-existent field: ghost_field')
    );
    expect(refError).toBeTruthy();
  });

  it('does not flag a control whose targets all exist (across multiple action arrays)', () => {
    const trigger = field({
      id: 'has_other_name',
      controls_fields: [
        {
          operator: 'equals',
          value: 'Yes',
          shows: ['other_given_name'],
          unlocks: ['other_family_name'],
          makes_required: ['other_family_name'],
        },
      ],
    });
    // validateSchema builds its known-id set incrementally as it iterates
    // schema.fields, so a trigger must follow its targets to be checked against
    // the full set (a pre-existing order-dependency shared with show_if; filed
    // separately). Real i-90 data lists controlled fields before the trigger.
    const schema = makeSchema([TARGET_A, TARGET_B, trigger]);
    const errors = validateSchema(schema);
    const refError = errors.find(e =>
      e.message.includes('controls_fields references non-existent field')
    );
    expect(refError).toBeFalsy();
  });
});
