/**
 * Option-value mint-on-settle (bd polyglot-pdf-0x10.5).
 *
 * Editing an option's label used to re-mint the internal value slug on EVERY
 * keystroke -- the slug churned through each intermediate label ("c" became
 * "nonresident_alien_filing_a_u_s_federal_tax_return" mid-typing) and the
 * chip visibly mutated under the author's cursor. The value now settles once,
 * on blur, with the dependent-condition retarget (bd 432u) running atomically
 * at that same settle point.
 *
 * These tests thread each patch back into a stateful harness (like the real
 * App does) so the blur handler sees the post-typing label, then assert on
 * the harness's latest schema.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField, FormSection } from '../types/schema';

function baseSchema(): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T', total_widgets: 2, total_fields: 2,
      version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 0, fields: ['race', 'dep'] }],
    fields: [
      {
        id: 'race', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
        section_id: 's1', read_only: false,
        options: [
          { value: 'white', label: 'White', pdf_field_name: 'w[0]' },
          { value: 'black', label: 'Black', pdf_field_name: 'b[0]' },
        ],
      },
      {
        id: 'dep', name: 'Dep', spoken_name: 'dep', type: 'text',
        section_id: 's1', read_only: false, pdf_field_name: 'd[0]',
        show_if: { field: 'race', operator: 'includes', value: 'white' },
      },
    ],
  } as unknown as FormSchema;
}

// Stateful harness: patches thread back into local state exactly like App's
// handleUpdateField/handleUpdateFields, and `latest` always holds the current
// schema for assertions.
function makeHarness(initial: FormSchema) {
  const latest = { schema: initial };
  const Harness: React.FC = () => {
    const [schema, setSchema] = React.useState(initial);
    latest.schema = schema;
    const field = schema.fields.find(f => f.id === 'race') ?? null;
    return (
      <FieldEditor
        field={field}
        schema={schema}
        onUpdateField={(updated: FormField) =>
          setSchema(prev => ({
            ...prev,
            fields: prev.fields.map(f => (f.id === updated.id ? updated : f)),
          }))
        }
        onUpdateFields={(fields: FormField[], sections?: FormSection[]) =>
          setSchema(prev => ({
            ...prev,
            fields,
            sections: sections ?? prev.sections,
          }))
        }
        authorTier
      />
    );
  };
  return { Harness, latest };
}

function raceOptions(schema: FormSchema) {
  return schema.fields.find(f => f.id === 'race')!.options!;
}

describe('option value mints on blur, not per keystroke (bd 0x10.5)', () => {
  it('keystrokes update the label only; the value is untouched until blur', () => {
    const { Harness, latest } = makeHarness(baseSchema());
    render(<Harness />);
    const input = screen.getByDisplayValue('White');

    fireEvent.change(input, { target: { value: 'Cauc' } });
    fireEvent.change(input, { target: { value: 'Caucasian person' } });

    expect(raceOptions(latest.schema)[0].label).toBe('Caucasian person');
    expect(raceOptions(latest.schema)[0].value).toBe('white');
  });

  it('blur settles the edit: value re-mints once from the final label', () => {
    const { Harness, latest } = makeHarness(baseSchema());
    render(<Harness />);
    const input = screen.getByDisplayValue('White');

    fireEvent.change(input, { target: { value: 'Caucasian person' } });
    fireEvent.blur(input);

    expect(raceOptions(latest.schema)[0].value).toBe('caucasian_person');
    expect(raceOptions(latest.schema)[0].label).toBe('Caucasian person');
    // The sibling option is untouched.
    expect(raceOptions(latest.schema)[1]).toMatchObject({ value: 'black', label: 'Black' });
  });

  it('the dependent show_if retargets to the new slug atomically at settle time (bd 432u contract)', () => {
    const { Harness, latest } = makeHarness(baseSchema());
    render(<Harness />);
    const input = screen.getByDisplayValue('White');

    fireEvent.change(input, { target: { value: 'Caucasian person' } });
    // Pre-blur: the dependent still points at the OLD slug, which still exists.
    expect((latest.schema.fields.find(f => f.id === 'dep') as any).show_if.value).toBe('white');

    fireEvent.blur(input);
    expect((latest.schema.fields.find(f => f.id === 'dep') as any).show_if.value).toBe('caucasian_person');
  });

  it('blur with an unchanged label is a no-op; an emptied label keeps the old value', () => {
    const { Harness, latest } = makeHarness(baseSchema());
    render(<Harness />);
    const input = screen.getByDisplayValue('White');

    // Unchanged label: no value churn.
    fireEvent.blur(input);
    expect(raceOptions(latest.schema)[0].value).toBe('white');

    // Emptied label: nothing to mint from -- the old value (and the
    // dependent's reference to it) must survive.
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);
    expect(raceOptions(latest.schema)[0].value).toBe('white');
    expect((latest.schema.fields.find(f => f.id === 'dep') as any).show_if.value).toBe('white');
  });
});
