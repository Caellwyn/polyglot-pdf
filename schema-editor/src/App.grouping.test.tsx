/**
 * App-level group/ungroup wiring test (bd polyglot-pdf-s4dp.1). The pure
 * merge/split semantics are covered in utils/fieldGrouping.test.ts; this proves
 * App threads the multi-selection through FieldList (real), runs the merge, and
 * un-merges back through FieldEditor (real). Only the heavy PDF child and the
 * network schema load are mocked.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema } from './types/schema';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div data-testid="vp" /> }));
vi.mock('./components/FormSelector', () => ({
  FormSelector: ({ onSelectForm }: { onSelectForm: (f: unknown) => void }) => (
    <button onClick={() => onSelectForm({
      name: 'W7', pdfPath: '/w7.pdf', schemaPath: '/schemas/w7/w7.json',
    })}>pick-W7</button>
  ),
}));

// Two separate "check one box" checkbox fields, plus an unrelated text field.
const SCHEMA: FormSchema = {
  source: 'pdf',
  form_metadata: { title: 'W7', form_number: 'W-7', total_widgets: 3, total_fields: 3, version: '1', language: 'en' },
  parts: [],
  sections: [
    { id: 'reason', label: 'Reason', order: 0, fields: ['reason_a', 'reason_b', 'note'] },
    { id: 'other', label: 'Other', order: 1, fields: ['other_a'] },
  ],
  fields: [
    { id: 'reason_a', name: 'Reason A', type: 'checkbox', section_id: 'reason', pdf_field_name: 'reason_a[0]', read_only: false, required: false, spoken_name: 'reason a' },
    { id: 'reason_b', name: 'Reason B', type: 'checkbox', section_id: 'reason', pdf_field_name: 'reason_b[0]', read_only: false, required: false, spoken_name: 'reason b' },
    { id: 'note', name: 'Note', type: 'text', section_id: 'reason', pdf_field_name: 'note[0]', read_only: false, required: false, spoken_name: 'note' },
    { id: 'other_a', name: 'Other A', type: 'checkbox', section_id: 'other', pdf_field_name: 'other_a[0]', read_only: false, required: false, spoken_name: 'other a' },
  ],
} as unknown as FormSchema;

vi.mock('./utils/schemaLoader', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/schemaLoader')>();
  return {
    ...actual,
    loadSchema: vi.fn(async () => JSON.parse(JSON.stringify(SCHEMA))),
    saveSchema: vi.fn(),
  };
});

import { App } from './App';

afterEach(() => {
  vi.clearAllMocks();
});

async function openForm() {
  render(<App />);
  fireEvent.click(screen.getByText('pick-W7'));
  await waitFor(() => expect(screen.getByTestId('pdf')).toBeInTheDocument());
}

describe('App group/ungroup wiring (bd polyglot-pdf-s4dp.1)', () => {
  beforeEach(() => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('shows a merge checkbox only for groupable (radio/checkbox) fields', async () => {
    await openForm();
    // reason_a / reason_b are checkboxes -> have a merge checkbox; note is text.
    expect(screen.getByLabelText('Select reason_a for merge')).toBeInTheDocument();
    expect(screen.getByLabelText('Select reason_b for merge')).toBeInTheDocument();
    expect(screen.queryByLabelText('Select note for merge')).not.toBeInTheDocument();
  });

  it('merges two ticked fields into one consolidated radio, then un-merges back', async () => {
    await openForm();

    // Tick both reason fields; the merge bar appears once 2 are selected.
    fireEvent.click(screen.getByLabelText('Select reason_a for merge'));
    fireEvent.click(screen.getByLabelText('Select reason_b for merge'));

    const mergeBtn = await screen.findByRole('button', { name: 'Merge' });
    fireEvent.click(mergeBtn);

    // After merge: the editor opens on the merged primary (reason_a), now a radio
    // with an Options section that has an Ungroup control.
    const ungroupBtn = await screen.findByRole('button', { name: 'Ungroup' });
    expect(ungroupBtn).toBeInTheDocument();

    // reason_b's standalone row is gone (it became an option of reason_a).
    expect(screen.queryByLabelText('Select reason_b for merge')).not.toBeInTheDocument();

    // Un-merge restores the separate fields: reason_b's merge checkbox returns.
    fireEvent.click(ungroupBtn);
    await waitFor(() =>
      expect(screen.getByLabelText('Select reason_b for merge')).toBeInTheDocument()
    );
    expect(screen.getByLabelText('Select reason_a for merge')).toBeInTheDocument();
  });

  it('disables Merge with only one field ticked', async () => {
    await openForm();
    fireEvent.click(screen.getByLabelText('Select reason_a for merge'));
    const mergeBtn = await screen.findByRole('button', { name: 'Merge' });
    expect(mergeBtn).toBeDisabled();
  });

  it('disables Merge with an explanation when the selection spans sections (Codex PR #256)', async () => {
    await openForm();
    fireEvent.click(screen.getByLabelText('Select reason_a for merge'));
    fireEvent.click(screen.getByLabelText('Select other_a for merge'));
    const mergeBtn = await screen.findByRole('button', { name: 'Merge' });
    expect(mergeBtn).toBeDisabled();
    expect(screen.getByText(/span multiple sections/i)).toBeInTheDocument();
  });
});

describe('App form-metadata reachability (bd polyglot-pdf-s4dp.2, Codex PR #263)', () => {
  beforeEach(() => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('shows the metadata panel by default (no field selected), then again via "Form metadata" after a field is picked', async () => {
    await openForm();
    // No field selected -> metadata panel is shown.
    expect(screen.getByText('Form metadata')).toBeInTheDocument(); // panel heading

    // Select a field (click its row in the FieldList) -> Field Properties shows.
    // The row renders the id as text inside the selectable button.
    const idCell = screen.getAllByText('reason_a').find(el => el.closest('button'));
    fireEvent.click(idCell!.closest('button')!);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Field Properties' })).toBeInTheDocument()
    );

    // The "Form metadata" deselect button is the way back; click it.
    fireEvent.click(screen.getByRole('button', { name: 'Form metadata' }));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Form Metadata' })).toBeInTheDocument()
    );
    // The editable version input is reachable again.
    expect(screen.getByLabelText('Version / Revision')).toBeInTheDocument();
  });
});
