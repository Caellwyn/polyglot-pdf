/**
 * A dropdown's option.value is a minted SLUG; its PDF export code lives in
 * option.pdf_on_value (bd polyglot-pdf-g2fpr, PR 2 -- the writer side).
 *
 * Until PR 1 the filler wrote str(option.value) verbatim into the combobox,
 * so a select's value HAD to be the export code and this file pinned that
 * carve-out (bd polyglot-pdf-alzbr). The filler now resolves value -> option
 * -> pdf_on_value, so the editor treats a select like every other choice
 * type: the value is an internal join key minted from the label, and the
 * export code is authored separately into pdf_on_value.
 *
 * Two select-specific rules the generic minter does not know, both pinned:
 * a trailing "(CODE)" in the label is stripped ('Alabama (AL)' -> 'alabama',
 * not 'alabama_al'), and a code that is already a valid slug ('5') IS the
 * value -- the label for the number five is "5".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function makeSchema(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

function selectField(options: any[] = [
  { value: 'wyoming', label: 'Wyoming (WY)', pdf_on_value: 'WY' },
  { value: 'alabama', label: 'Alabama (AL)', pdf_on_value: 'AL' },
]): FormField {
  return {
    id: 'mail_state', name: 'State', spoken_name: 'state', type: 'select',
    section_id: 's1', pdf_field_name: 'form1[0].P1_Line6e_State[0]',
    options,
  } as unknown as FormField;
}

function radioField(): FormField {
  return {
    id: 'sex', name: 'Sex', spoken_name: 'sex', type: 'radio',
    section_id: 's1', pdf_field_name: 'form1[0].P1_Sex[0]',
    options: [
      { value: 'male', label: 'Male', pdf_on_value: '1' },
      { value: 'female', label: 'Female', pdf_on_value: '2' },
    ],
  } as unknown as FormField;
}

/** A REAL state-holding parent: a vi.fn() parent never re-renders, so a test
 * that reads the probe after an edit would assert on stale props. */
function Harness({ initial, id = 'mail_state' }: { initial: FormSchema; id?: string }) {
  const [s, setS] = React.useState<FormSchema>(initial);
  const f = s.fields.find(x => x.id === id)!;
  return (
    <>
      <FieldEditor
        field={f}
        schema={s}
        onUpdateField={(patch: any) => setS(p => ({
          ...p,
          fields: p.fields.map(x => (x.id === id ? { ...x, ...patch } : x)),
        } as FormSchema))}
        onUpdateFields={(fields: any, sections: any) => setS(p => ({
          ...p, fields, sections: sections ?? p.sections,
        } as FormSchema))}
        authorTier
      />
      <pre data-testid="probe">{JSON.stringify(
        (s.fields.find(x => x.id === id) as any).options
          .map((o: any) => [o.label, o.value, o.pdf_on_value ?? null]),
      )}</pre>
      <pre data-testid="fields">{JSON.stringify(s.fields)}</pre>
    </>
  );
}

const probe = () => JSON.parse(screen.getByTestId('probe').textContent!);
const codeInputs = () =>
  screen.getAllByTitle(/code this dropdown writes/) as HTMLInputElement[];

describe('select option values are minted slugs; the export code is pdf_on_value (bd polyglot-pdf-g2fpr)', () => {
  it('editing a select option LABEL re-mints its value from the label, with the (CODE) stripped', () => {
    render(<Harness initial={makeSchema([selectField()])} />);
    const input = screen.getByDisplayValue('Wyoming (WY)') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Wyoming State (WY)' } });
    fireEvent.blur(input);
    const opts = probe();
    expect(opts[0]).toEqual(['Wyoming State (WY)', 'wyoming_state', 'WY']);
    expect(opts[1]).toEqual(['Alabama (AL)', 'alabama', 'AL']);  // untouched
  });

  it('a label rename never touches the export code', () => {
    render(<Harness initial={makeSchema([selectField()])} />);
    const input = screen.getByDisplayValue('Alabama (AL)') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Alabama' } });
    fireEvent.blur(input);
    expect(probe()[1]).toEqual(['Alabama', 'alabama', 'AL']);
  });

  it('a NUMERIC code is already a slug and stays the value through a label edit', () => {
    // height_feet: label "5", code "5". Re-minting from a reworded label must
    // not invent a word for a number.
    const height = selectField([
      { value: '5', label: '5', pdf_on_value: '5' },
      { value: '6', label: '6', pdf_on_value: '6' },
    ]);
    render(<Harness initial={makeSchema([height])} />);
    const input = screen.getAllByPlaceholderText('Option label')[0] as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'five feet' } });
    fireEvent.blur(input);
    expect(probe()[0]).toEqual(['five feet', '5', '5']);
  });

  it('a label rename RETARGETS a dependent that references the old slug', () => {
    // The value is an identity a show_if can reference; renaming must move
    // the reference atomically, exactly as radio/checkbox_group already do.
    const dep = {
      id: 'dep', name: 'Dep', spoken_name: 'dep', type: 'text', section_id: 's1',
      show_if: { field: 'mail_state', operator: 'equals', value: 'wyoming' },
    } as unknown as FormField;
    render(<Harness initial={makeSchema([selectField(), dep])} />);
    const input = screen.getByDisplayValue('Wyoming (WY)') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Wyoming State (WY)' } });
    fireEvent.blur(input);
    const fields = JSON.parse(screen.getByTestId('fields').textContent!);
    expect(fields.find((f: any) => f.id === 'dep').show_if.value).toBe('wyoming_state');
  });

  it('the export code input is bound to pdf_on_value, and editing it leaves the value alone', () => {
    render(<Harness initial={makeSchema([selectField()])} />);
    const code = codeInputs()[0];
    expect(code.value).toBe('WY');
    fireEvent.change(code, { target: { value: 'WV' } });
    fireEvent.blur(code, { target: { value: 'WV' } });
    expect(probe()[0]).toEqual(['Wyoming (WY)', 'wyoming', 'WV']);
  });

  it('editing the export code does NOT retarget dependents -- the slug they reference is unchanged', () => {
    const dep = {
      id: 'dep', name: 'Dep', spoken_name: 'dep', type: 'text', section_id: 's1',
      show_if: { field: 'mail_state', operator: 'equals', value: 'wyoming' },
    } as unknown as FormField;
    render(<Harness initial={makeSchema([selectField(), dep])} />);
    const code = codeInputs()[0];
    fireEvent.change(code, { target: { value: 'WV' } });
    fireEvent.blur(code, { target: { value: 'WV' } });
    const fields = JSON.parse(screen.getByTestId('fields').textContent!);
    expect(fields.find((f: any) => f.id === 'dep').show_if.value).toBe('wyoming');
  });

  it('an export code is trimmed on blur', () => {
    render(<Harness initial={makeSchema([selectField()])} />);
    const code = codeInputs()[0];
    fireEvent.change(code, { target: { value: ' WV ' } });
    fireEvent.blur(code, { target: { value: ' WV ' } });
    expect(probe()[0][2]).toBe('WV');
  });

  it('the slug is shown read-only beside the editable code', () => {
    render(<Harness initial={makeSchema([selectField()])} />);
    expect(screen.getByText('wyoming')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('wyoming')).toBeNull();   // not an input
  });

  it('+ Add Option on a select mints a slug; the code starts empty for the author to fill', () => {
    render(<Harness initial={makeSchema([selectField()])} />);
    fireEvent.click(screen.getByText('+ Add Option'));
    const opts = probe();
    expect(opts).toHaveLength(3);
    expect(opts[2]).toEqual(['', 'option', null]);
  });

  it('a second added option gets a unique slug', () => {
    render(<Harness initial={makeSchema([selectField()])} />);
    fireEvent.click(screen.getByText('+ Add Option'));
    fireEvent.click(screen.getByText('+ Add Option'));
    const opts = probe();
    expect(opts.map((o: any) => o[1])).toEqual(['wyoming', 'alabama', 'option', 'option_2']);
  });

  it('the ZERO-OPTIONS "Add Option" also mints for a select', () => {
    render(<Harness initial={makeSchema([selectField([])])} />);
    fireEvent.click(screen.getByText('+ Add Option'));
    expect(probe()).toEqual([['', 'option', null]]);
  });

  it('the export code input is available to the EDITOR tier, not just authors', () => {
    const s = makeSchema([selectField()]);
    render(<FieldEditor field={s.fields[0]} schema={s} onUpdateField={vi.fn()} />);
    expect(codeInputs()).toHaveLength(2);
  });

  it('a radio option label edit still re-mints its value (unchanged behaviour)', () => {
    render(<Harness initial={makeSchema([radioField()])} id="sex" />);
    const input = screen.getByDisplayValue('Male') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Man' } });
    fireEvent.blur(input);
    expect(probe()[0]).toEqual(['Man', 'man', '1']);
  });

  it('a radio has no export-code input', () => {
    const s = makeSchema([radioField()]);
    render(<FieldEditor field={s.fields[0]} schema={s} onUpdateField={vi.fn()} authorTier />);
    expect(screen.queryAllByTitle(/code this dropdown writes/)).toHaveLength(0);
  });
});

describe('a LEGACY select option (code in value, no pdf_on_value) is CONVERTED ON TOUCH', () => {
  // Fresh-eyes (g2fpr.2): the maintainer's own un-migrated kit opened in the
  // editor. Minting the value on a label edit without first moving the code
  // would leave the filler's legacy fallback writing the SLUG verbatim into
  // the combobox -- the c5r8 defect, reintroduced by the fix.
  const legacy = () => selectField([
    { value: 'WY', label: 'Wyoming' },
    { value: 'AL', label: 'Alabama' },
  ]);

  it('the export-code input SHOWS the legacy code even though it lives in value', () => {
    render(<Harness initial={makeSchema([legacy()])} />);
    expect(codeInputs()[0].value).toBe('WY');
  });

  it('a label edit moves the code into pdf_on_value and THEN mints the value', () => {
    render(<Harness initial={makeSchema([legacy()])} />);
    const input = screen.getByDisplayValue('Wyoming') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Wyoming State' } });
    fireEvent.blur(input);
    expect(probe()[0]).toEqual(['Wyoming State', 'wyoming_state', 'WY']);
    expect(probe()[1]).toEqual(['Alabama', 'AL', null]);   // untouched sibling stays legacy
  });

  it('a label edit that mints the SAME slug still converts (the code must move)', () => {
    // 'Wyoming' -> slug 'wyoming' != legacy value 'WY', so this converts on
    // any edit; pin that an edit whose minted slug equals the old value would
    // also convert rather than early-return. Build that case: value already
    // 'wyoming' would be the v2 shape, so use a numeric legacy option instead.
    const numeric = selectField([{ value: '5', label: '5' }]);
    render(<Harness initial={makeSchema([numeric])} />);
    // NOT getByDisplayValue('5'): the export-code input also shows '5' (the
    // legacy code), so that selector is ambiguous -- target the label input.
    const input = screen.getAllByPlaceholderText('Option label')[0] as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'five' } });
    fireEvent.blur(input);
    expect(probe()[0]).toEqual(['five', '5', '5']);   // code kept as value AND moved
  });

  it('a code edit on a legacy option converts it and stores the new code', () => {
    render(<Harness initial={makeSchema([legacy()])} />);
    const code = codeInputs()[0];
    fireEvent.change(code, { target: { value: 'WV' } });
    fireEvent.blur(code, { target: { value: 'WV' } });
    expect(probe()[0]).toEqual(['Wyoming', 'wyoming', 'WV']);
  });

  it('the filler contract holds after conversion: the value is a slug and the code is the code', () => {
    render(<Harness initial={makeSchema([legacy()])} />);
    const input = screen.getByDisplayValue('Alabama') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Alabama (AL)' } });
    fireEvent.blur(input);
    const [, value, code] = probe()[1];
    expect(value).toMatch(/^[a-z0-9][a-z0-9_-]*$/);
    expect(code).toBe('AL');
  });
});
