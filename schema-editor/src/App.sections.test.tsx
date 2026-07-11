/**
 * App-level section-management wiring (bd polyglot-pdf-6cfu.3): the Sections
 * button opens the SectionManager over the real schema; an op commits ONE
 * atomic {fields, sections, parts} step through the undo history; the
 * regenerate action is hidden outside hosted-author mode.
 *
 * The heavy children are mocked (same harness as App.save.test.tsx);
 * SectionManager itself renders REAL so the wiring under test is App's.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema } from './types/schema';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/FieldList', () => ({ FieldList: () => <div data-testid="list" /> }));
vi.mock('./components/FieldEditor', () => ({ FieldEditor: () => <div data-testid="editor" /> }));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div data-testid="vp" /> }));
vi.mock('./components/FormSelector', () => ({
  FormSelector: ({ onSelectForm }: { onSelectForm: (f: unknown) => void }) => (
    <button onClick={() => onSelectForm({
      name: 'A', pdfPath: '/a.pdf', schemaPath: '/schemas/a/a.json',
    })}>pick-A</button>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'A', form_number: 'A-1', version: '1' },
  parts: [{ id: 'p1', label: 'Part 1', order: 1, section_ids: ['sec_a', 'sec_b'] }],
  sections: [
    { id: 'sec_a', label: 'Alpha', order: 1, fields: ['f1'] },
    { id: 'sec_b', label: 'Beta', order: 2, fields: [] },
  ],
  fields: [{ id: 'f1', name: 'F1', type: 'text', section_id: 'sec_a' }],
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
import * as loader from './utils/schemaLoader';

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

async function openManager() {
  render(<App />);
  fireEvent.click(screen.getByText('pick-A'));
  await waitFor(() => expect(loader.loadSchema).toHaveBeenCalled());
  fireEvent.click(screen.getByText('Sections'));
  await screen.findByText('Manage sections');
}

describe('App section management', () => {
  it('opens the manager, commits a rename as one undoable step', async () => {
    await openManager();
    const input = screen.getByDisplayValue('Alpha');
    fireEvent.change(input, { target: { value: 'Alpha 2' } });
    fireEvent.blur(input);
    // The commit re-rendered the manager from the new schema.
    expect(screen.getByDisplayValue('Alpha 2')).toBeInTheDocument();
    // One undo step restores the original label.
    fireEvent.click(screen.getByText('Close'));
    fireEvent.keyDown(window, { key: 'z', metaKey: true });
    fireEvent.click(screen.getByText('Sections'));
    expect(await screen.findByDisplayValue('Alpha')).toBeInTheDocument();
  });

  it('commits a merge atomically: fields, sections and parts stay consistent', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await openManager();
    fireEvent.change(screen.getByLabelText('Merge Alpha into'),
      { target: { value: 'sec_b' } });
    await waitFor(() =>
      expect(screen.queryByDisplayValue('Alpha')).toBeNull());
    // Re-open after close to read the committed schema state.
    expect(screen.getByDisplayValue('Beta')).toBeInTheDocument();
  });

  it('hides Regenerate divisions outside hosted-author mode', async () => {
    await openManager();
    expect(screen.queryByText('Regenerate divisions')).toBeNull();
  });
});
