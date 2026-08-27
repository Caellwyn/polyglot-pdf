/**
 * A dropdown's option.value is the PDF's own EXPORT CODE, not a minted slug
 * (bd polyglot-pdf-alzbr).
 *
 * A select has no fill branch of its own: the filler writes str(option.value)
 * verbatim into the combobox and never consults pdf_on_value, and PyMuPDF does
 * not validate that write against the widget's /Opt list. So a label-derived
 * slug is accepted silently and then RENDERS CLIPPED -- measured on the I-90
 * mailing-state box (36x18pt): 'WY' prints "WY", 'wyoming' prints "wyomin".
 *
 * The editor therefore must never derive a select's option value from its
 * label, and must let an author type the code directly -- it is the only place
 * that code can come from. radio / checkbox_group keep the mint-from-label
 * behaviour: they carry widget identity in pdf_field_name / pdf_on_value, so
 * their values really are internal join keys.
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

function selectField(options = [
  { value: 'WY', label: 'Wyoming (WY)' },
  { value: 'AL', label: 'Alabama (AL)' },
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

describe('select option values are PDF export codes (bd polyglot-pdf-alzbr)', () => {
  it('editing a select option LABEL does not change its value', () => {
    // Asserted on the RESULTING STATE, not on callback shapes. The correct
    // behaviour here is to commit NOTHING (the value must not change), so any
    // assertion that only inspects committed calls iterates zero times and
    // passes against a broken guard -- which is exactly how an earlier cut of
    // this test shipped vacuous. A real state-holding parent makes the
    // post-edit value directly observable instead.
    function Harness() {
      const [s, setS] = React.useState<FormSchema>(
        makeSchema([selectField()]),
      );
      const f = s.fields.find(x => x.id === 'mail_state')!;
      return (
        <>
          <FieldEditor
            field={f}
            schema={s}
            onUpdateField={(patch: any) => setS(p => ({
              ...p,
              fields: p.fields.map(x => (x.id === 'mail_state' ? { ...x, ...patch } : x)),
            } as FormSchema))}
            onUpdateFields={(fields: any, sections: any) => setS(p => ({
              ...p, fields, sections: sections ?? p.sections,
            } as FormSchema))}
            authorTier
          />
          <pre data-testid="probe">{JSON.stringify(
            (s.fields.find(x => x.id === 'mail_state') as any).options
              .map((o: any) => [o.label, o.value]),
          )}</pre>
        </>
      );
    }

    render(<Harness />);
    const input = screen.getByDisplayValue('Wyoming (WY)') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Wyoming' } });
    fireEvent.blur(input);

    const opts = JSON.parse(screen.getByTestId('probe').textContent!);
    expect(opts[0][0]).toBe('Wyoming');  // the label DID change...
    expect(opts[0][1]).toBe('WY');       // ...and the export code did NOT
    expect(opts[1][1]).toBe('AL');
  });

  it('a radio option label edit STILL re-mints its value (the carve-out is select-only)', () => {
    // The blur handler reads the option's label from the CURRENT field prop,
    // so the parent must re-render with the edited label -- exactly what the
    // real editor does. Driving change+blur against a static prop would leave
    // the handler reading the OLD label and prove nothing.
    const onUpdateField = vi.fn();
    const edited = radioField();
    (edited.options as any)[0].label = 'Gentleman';
    render(
      <FieldEditor field={edited} schema={makeSchema([edited])}
        onUpdateField={onUpdateField} authorTier />,
    );

    const input = screen.getByDisplayValue('Gentleman') as HTMLInputElement;
    fireEvent.blur(input);

    const remint = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(f => f && Array.isArray(f.options))
      .some(f => f.options.some((o: any) => o.value === 'gentleman'));
    expect(remint).toBe(true);
  });

  it('a select option value is EDITABLE, so the export code can be authored', () => {
    const onUpdateField = vi.fn();
    const field = selectField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={onUpdateField} authorTier />,
    );

    // Rendered as an input carrying the code -- not a read-only chip.
    const codeInput = screen.getByDisplayValue('WY') as HTMLInputElement;
    expect(codeInput.tagName).toBe('INPUT');

    fireEvent.change(codeInput, { target: { value: 'WV' } });
    const wrote = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(p => p && Array.isArray(p.options))
      .some(p => p.options[0].value === 'WV');
    expect(wrote).toBe(true);
  });

  it('a radio option value stays a read-only chip, not an input', () => {
    const field = radioField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={vi.fn()} authorTier />,
    );
    // present as text...
    expect(screen.getByText('male')).toBeInTheDocument();
    // ...and NOT as an editable input
    expect(screen.queryByDisplayValue('male')).toBeNull();
  });

  it('+ Add Option on a select adds an EMPTY value for the author to fill', () => {
    const onUpdateField = vi.fn();
    const field = selectField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={onUpdateField} authorTier />,
    );

    fireEvent.click(screen.getByText('+ Add Option'));
    const added = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(p => p && Array.isArray(p.options))
      .pop();
    expect(added).toBeTruthy();
    // A minted slug here would look valid and print WRONG; empty trips the
    // existing option-value-missing lint ERROR, which is the honest signal.
    expect(added.options[added.options.length - 1].value).toBe('');
  });

  it('retargets dependents when driven through a REAL state-holding parent', () => {
    // The load-bearing test for the retarget (bd polyglot-pdf-alzbr).
    //
    // A vi.fn() parent never feeds an updated field prop back, so the row is
    // never re-rendered between keystrokes and the handler's closed-over
    // option.value stays pinned at the ORIGINAL code -- which is NOT what
    // happens in the app. With a real parent, onChange commits every keystroke,
    // so by blur the option's value is already the newly-typed string; reading
    // "old" from it found no change and skipped the retarget entirely. Measured
    // before the fix: code became 'WV' while the dependent still said 'WY'.
    //
    // This harness mirrors App.tsx: real useState, both callbacks wired.
    function Harness() {
      const [schema, setSchema] = React.useState<FormSchema>({
        source: 'pdf',
        form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
        parts: [],
        sections: [{ id: 's1', label: 'S1', order: 1, fields: ['mail_state', 'dep'] }],
        fields: [
          selectField(),
          {
            id: 'dep', name: 'Dep', spoken_name: 'dep', type: 'text',
            section_id: 's1', pdf_field_name: 'form1[0].dep[0]',
            show_if: { field: 'mail_state', operator: 'equals', value: 'WY' },
          } as unknown as FormField,
        ],
      } as unknown as FormSchema);
      const field = schema.fields.find(f => f.id === 'mail_state')!;
      return (
        <>
          <FieldEditor
            field={field}
            schema={schema}
            onUpdateField={(f: any) => setSchema(s => ({
              ...s,
              fields: s.fields.map(x => (x.id === 'mail_state' ? { ...x, ...f } : x)),
            } as FormSchema))}
            onUpdateFields={(fields: any, sections: any) => setSchema(s => ({
              ...s, fields, sections: sections ?? s.sections,
            } as FormSchema))}
            authorTier
          />
          <pre data-testid="probe">{JSON.stringify({
            code: (schema.fields.find(f => f.id === 'mail_state') as any).options[0].value,
            depRef: (schema.fields.find(f => f.id === 'dep') as any).show_if?.value,
          })}</pre>
        </>
      );
    }

    render(<Harness />);
    const input = screen.getByDisplayValue('WY') as HTMLInputElement;
    // Real keystrokes, and a real blur with NO target override -- overriding
    // e.target.value at blur manufactures a mismatch that cannot occur live.
    fireEvent.change(input, { target: { value: 'W' } });
    fireEvent.change(input, { target: { value: 'WV' } });
    fireEvent.blur(input);

    const state = JSON.parse(screen.getByTestId('probe').textContent!);
    expect(state.code).toBe('WV');
    expect(state.depRef).toBe('WV');
  });

  it('editing an export code RETARGETS dependents that reference it', () => {
    // option.value is an identity a dependent's show_if can reference -- Remove
    // even BLOCKS deleting a referenced option over it. Changing the code must
    // therefore move those references too, exactly as the radio label-rename
    // does, or the dependent silently dangles (or flips from hidden to
    // shown-for-everyone).
    const field = selectField();
    const dependent = {
      id: 'dep', name: 'Dep', spoken_name: 'dep', type: 'text', section_id: 's1',
      pdf_field_name: 'form1[0].dep[0]',
      show_if: { field: 'mail_state', operator: 'equals', value: 'WY' },
    } as unknown as FormField;
    const schema = {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 1, fields: ['mail_state', 'dep'] }],
      fields: [field, dependent],
    } as unknown as FormSchema;

    const onUpdateFields = vi.fn();
    render(
      <FieldEditor field={field} schema={schema}
        onUpdateField={vi.fn()} onUpdateFields={onUpdateFields} authorTier />,
    );

    const codeInput = screen.getByDisplayValue('WY') as HTMLInputElement;
    fireEvent.change(codeInput, { target: { value: 'WV' } });
    fireEvent.blur(codeInput, { target: { value: 'WV' } });

    expect(onUpdateFields).toHaveBeenCalled();
    const [fields] = onUpdateFields.mock.calls[onUpdateFields.mock.calls.length - 1];
    const dep = fields.find((f: any) => f.id === 'dep');
    expect(dep.show_if.value).toBe('WV');
  });

  it('blanking a referenced code does NOT retarget the dependent to empty', () => {
    // Deliberate: leaving the reference on the old code keeps it VISIBLE.
    // schema_lint skips its dangling-reference check for "" on purpose (the v1
    // "field is empty" idiom, used for real on the i-90's unit-type radios), so
    // rewriting a dependent to "" turns an orphaned reference into a different,
    // LIVE condition that lint cannot see -- and one that plausibly matches an
    // unanswered dropdown. Measured against the real linter: old code ->
    // ref-option-value ERROR; "" -> nothing at all.
    const field = selectField();
    const dependent = {
      id: 'dep', name: 'Dep', spoken_name: 'dep', type: 'text', section_id: 's1',
      pdf_field_name: 'form1[0].dep[0]',
      show_if: { field: 'mail_state', operator: 'equals', value: 'WY' },
    } as unknown as FormField;
    const schema = {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 1, fields: ['mail_state', 'dep'] }],
      fields: [field, dependent],
    } as unknown as FormSchema;

    // Real state-holding parent: a vi.fn() parent never calls onUpdateFields
    // here, so a loop over its calls would iterate ZERO times and assert
    // nothing -- the test would pass against a blank-out that DID retarget.
    function Harness() {
      const [s, setS] = React.useState<FormSchema>(schema);
      const f = s.fields.find(x => x.id === 'mail_state')!;
      return (
        <>
          <FieldEditor
            field={f}
            schema={s}
            onUpdateField={(patch: any) => setS(p => ({
              ...p,
              fields: p.fields.map(x => (x.id === 'mail_state' ? { ...x, ...patch } : x)),
            } as FormSchema))}
            onUpdateFields={(fields: any, sections: any) => setS(p => ({
              ...p, fields, sections: sections ?? p.sections,
            } as FormSchema))}
            authorTier
          />
          <pre data-testid="probe">{JSON.stringify({
            code: (s.fields.find(x => x.id === 'mail_state') as any).options[0].value,
            depRef: (s.fields.find(x => x.id === 'dep') as any).show_if?.value,
          })}</pre>
        </>
      );
    }

    render(<Harness />);
    const codeInput = screen.getByDisplayValue('WY') as HTMLInputElement;
    fireEvent.focus(codeInput);
    fireEvent.change(codeInput, { target: { value: '' } });
    fireEvent.blur(codeInput);

    const state = JSON.parse(screen.getByTestId('probe').textContent!);
    expect(state.code).toBe('');        // the blank-out did take effect...
    expect(state.depRef).toBe('WY');    // ...and the reference stayed VISIBLE
  });

  it('an export code is trimmed on blur', () => {
    // ' WY' is never a legal export code -- it silently fails the /Opt match
    // and the form prints blank.
    const onUpdateField = vi.fn();
    const field = selectField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={onUpdateField} authorTier />,
    );
    const codeInput = screen.getByDisplayValue('WY') as HTMLInputElement;
    fireEvent.change(codeInput, { target: { value: '  WV  ' } });
    fireEvent.blur(codeInput, { target: { value: '  WV  ' } });

    const committed = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(f => f && Array.isArray(f.options))
      .pop();
    expect(committed.options[0].value).toBe('WV');
  });

  it('the export code input is available to the EDITOR tier, not just authors', () => {
    // "+ Add Option" is enabled for editors on a select, and a new select
    // option now starts EMPTY -- so an editor who cannot reach this input can
    // create an option they have no way to complete.
    // authorTier DEFAULTS TO TRUE, so omitting the prop does not simulate an
    // editor -- it must be passed false explicitly or this asserts nothing.
    const field = selectField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={vi.fn()} authorTier={false} />,
    );
    expect(screen.getByDisplayValue('WY')).toBeInTheDocument();
  });

  it('a radio option value stays author-only (no editor-tier value input)', () => {
    const field = radioField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={vi.fn()} authorTier={false} />,
    );
    expect(screen.queryByDisplayValue('male')).toBeNull();
  });

  it('+ Add Option on a radio still mints a slug', () => {
    const onUpdateField = vi.fn();
    const field = radioField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={onUpdateField} authorTier />,
    );

    fireEvent.click(screen.getByText('+ Add Option'));
    const added = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(p => p && Array.isArray(p.options))
      .pop();
    expect(added).toBeTruthy();
    expect(added.options[added.options.length - 1].value).toBeTruthy();
  });
});
