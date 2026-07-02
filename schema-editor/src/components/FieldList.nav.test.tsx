/**
 * FieldList review-flow navigation (bd polyglot-pdf-92qe.5).
 *
 * Exit criterion under test: next-needs-review cycles through non-complete
 * fields including wrap-around and filtered lists, via both click and
 * keyboard; arrows move selection; Escape deselects; none of it fires while
 * typing in an editable control.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldList } from './FieldList';
import type { FormSchema, FormField } from '../types/schema';

// checkFieldComplete: complete needs id+type+pdf_field_name, a non-empty
// spoken_name, and help.instructions without [TODO].
function completeField(id: string, sectionId: string): FormField {
  return {
    id,
    name: id,
    type: 'text',
    pdf_field_name: `pdf.${id}`,
    spoken_name: `spoken ${id}`,
    section_id: sectionId,
    help: { instructions: 'All set.' },
  } as unknown as FormField;
}

function reviewField(id: string, sectionId: string): FormField {
  return {
    id,
    name: id,
    type: 'text',
    pdf_field_name: `pdf.${id}`,
    spoken_name: '', // needs review
    section_id: sectionId,
    help: { instructions: 'All set.' },
  } as unknown as FormField;
}

// Reading order: f-one (complete), f-two (review), g-one (complete),
// g-two (review).
const SCHEMA = {
  form_metadata: { title: 'Nav Form', version: '1' },
  sections: [
    { id: 's1', title: 'Section One', fields: ['f-one', 'f-two'] },
    { id: 's2', title: 'Section Two', fields: ['g-one', 'g-two'] },
  ],
  fields: [
    completeField('f-one', 's1'),
    reviewField('f-two', 's1'),
    completeField('g-one', 's2'),
    reviewField('g-two', 's2'),
  ],
} as unknown as FormSchema;

function renderList(selectedFieldId: string | null = null) {
  const onSelectField = vi.fn();
  const onDeselect = vi.fn();
  render(
    <FieldList
      schema={SCHEMA}
      selectedFieldId={selectedFieldId}
      onSelectField={onSelectField}
      onDeselect={onDeselect}
    />
  );
  return { onSelectField, onDeselect };
}

describe('next-needs-review navigation (bd 92qe.5)', () => {
  it('the button jumps to the first field needing attention', () => {
    const { onSelectField } = renderList(null);
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('f-two');
  });

  it('jumps FORWARD from the current selection, skipping complete fields', () => {
    const { onSelectField } = renderList('f-two');
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('g-two'); // g-one is complete
  });

  it('wraps around from the last field back to the first needing review', () => {
    const { onSelectField } = renderList('g-two');
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('f-two');
  });

  it('honors the active search filter (jumps only within visible fields)', () => {
    const { onSelectField } = renderList(null);
    fireEvent.change(screen.getByLabelText('Search fields'), {
      target: { value: 'g-' },
    });
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('g-two'); // f-two is filtered out
  });

  it('resolves an option-row selection to its base field before jumping', () => {
    const { onSelectField } = renderList('f-two:option:1');
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('g-two');
  });

  it('with every visible field complete: the button disables and N no-ops', () => {
    const allDone = {
      ...SCHEMA,
      fields: [
        completeField('f-one', 's1'),
        completeField('f-two', 's1'),
        completeField('g-one', 's2'),
        completeField('g-two', 's2'),
      ],
    } as unknown as FormSchema;
    const onSelectField = vi.fn();
    render(
      <FieldList schema={allDone} selectedFieldId={null} onSelectField={onSelectField} />
    );
    expect(screen.getByText('Next to review')).toBeDisabled();
    fireEvent.keyDown(window, { key: 'n' });
    expect(onSelectField).not.toHaveBeenCalled();
  });

  it('re-selects the current field when it is the ONLY one needing review', () => {
    const onlyOne = {
      ...SCHEMA,
      fields: [
        completeField('f-one', 's1'),
        reviewField('f-two', 's1'),
        completeField('g-one', 's2'),
        completeField('g-two', 's2'),
      ],
    } as unknown as FormSchema;
    const onSelectField = vi.fn();
    render(
      <FieldList schema={onlyOne} selectedFieldId="f-two" onSelectField={onSelectField} />
    );
    fireEvent.click(screen.getByText('Next to review'));
    expect(onSelectField).toHaveBeenCalledWith('f-two'); // full wrap lands home
  });

  it('pressing N triggers the same jump', () => {
    const { onSelectField } = renderList(null);
    fireEvent.keyDown(window, { key: 'n' });
    expect(onSelectField).toHaveBeenCalledWith('f-two');
  });

  it('ArrowDown moves selection to the next visible field (first when none)', () => {
    const { onSelectField } = renderList(null);
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(onSelectField).toHaveBeenCalledWith('f-one');
  });

  it('ArrowDown/ArrowUp step through the visible order without wrapping', () => {
    const { onSelectField } = renderList('f-two');
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(onSelectField).toHaveBeenLastCalledWith('g-one');
    fireEvent.keyDown(window, { key: 'ArrowUp' });
    expect(onSelectField).toHaveBeenLastCalledWith('f-one');
  });

  it('ArrowUp at the first field stays put (no wrap)', () => {
    const { onSelectField } = renderList('f-one');
    fireEvent.keyDown(window, { key: 'ArrowUp' });
    expect(onSelectField).not.toHaveBeenCalled();
  });

  it('Escape calls onDeselect', () => {
    const { onDeselect } = renderList('f-one');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onDeselect).toHaveBeenCalled();
  });

  it('never fires while typing in the search box (editable-target guard)', () => {
    const { onSelectField, onDeselect } = renderList(null);
    const input = screen.getByLabelText('Search fields');
    input.focus();
    fireEvent.keyDown(input, { key: 'n' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onSelectField).not.toHaveBeenCalled();
    expect(onDeselect).not.toHaveBeenCalled();
  });

  it('modifier chords pass through untouched (Ctrl+N is the browser\'s)', () => {
    const { onSelectField } = renderList(null);
    fireEvent.keyDown(window, { key: 'n', ctrlKey: true });
    expect(onSelectField).not.toHaveBeenCalled();
  });
});
