/**
 * App-level field-id rename (bd polyglot-pdf-0x10.1, exit criterion 1): one
 * rename commit retargets the field, its dependents' conditions, the section
 * membership and copy_to lists TOGETHER; a single Undo restores everything;
 * the selection follows the renamed field.
 *
 * Heavy children are mocked (the undo-test pattern): FieldEditor exposes a
 * button that drives onRenameField, FieldList renders the bits of the schema
 * the assertions read.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema, FormField } from './types/schema';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/FieldList', () => ({
  FieldList: ({ schema, onSelectField }: {
    schema: FormSchema | null; onSelectField: (id: string) => void;
  }) => (
    <div>
      <span data-testid="list-ids">{schema?.fields.map(f => f.id).join(',')}</span>
      <span data-testid="list-dep-showif">
        {JSON.stringify((schema?.fields.find(f => f.id === 'dep') as any)?.show_if ?? null)}
      </span>
      <span data-testid="list-section-fields">
        {schema?.sections[0]?.fields.join(',')}
      </span>
      <button onClick={() => onSelectField('old_name')}>select-old</button>
    </div>
  ),
}));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div /> }));
vi.mock('./components/FieldEditor', () => ({
  FieldEditor: ({ field, onRenameField }: {
    field: FormField | null;
    onRenameField?: (oldId: string, newId: string) => string | null;
  }) => (
    <div>
      <span data-testid="editor-field-id">{field?.id ?? '(none)'}</span>
      <button onClick={() => field && onRenameField?.(field.id, 'new_name')}>
        rename-field
      </button>
      <button onClick={() => field && onRenameField?.(field.id, 'dep')}>
        rename-to-duplicate
      </button>
    </div>
  ),
}));
vi.mock('./components/FormSelector', () => ({
  FormSelector: ({ onSelectForm }: { onSelectForm: (f: unknown) => void }) => (
    <button onClick={() => onSelectForm({ name: 'A', pdfPath: '/a.pdf', schemaPath: '/a.json' })}>pick-A</button>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'A', form_number: 'A-1', version: '1' },
  sections: [
    { id: 's1', label: 'S1', order: 0, fields: ['old_name', 'dep', 'copier'] },
  ],
  fields: [
    { id: 'old_name', name: 'O', type: 'text', spoken_name: 'old' },
    {
      id: 'dep', name: 'D', type: 'text', spoken_name: 'dep',
      show_if: { field: 'old_name', operator: 'is_not_empty' },
    },
    { id: 'copier', name: 'C', type: 'text', spoken_name: 'c', copy_to: ['old_name'] },
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
import * as loader from './utils/schemaLoader';

beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true); });
afterEach(() => vi.clearAllMocks());

async function loadAndSelect() {
  fireEvent.click(screen.getByText('pick-A'));
  await waitFor(() => expect(loader.loadSchema).toHaveBeenCalled());
  fireEvent.click(screen.getByText('select-old'));
  await waitFor(() =>
    expect(screen.getByTestId('editor-field-id').textContent).toBe('old_name'));
}

describe('App field-id rename (bd 0x10.1)', () => {
  it('one commit renames the field + retargets dependents; selection follows; one Undo restores all', async () => {
    render(<App />);
    await loadAndSelect();

    fireEvent.click(screen.getByText('rename-field'));

    // Everything moved together...
    await waitFor(() => {
      expect(screen.getByTestId('list-ids').textContent).toBe('new_name,dep,copier');
    });
    expect(screen.getByTestId('list-dep-showif').textContent).toContain('"new_name"');
    expect(screen.getByTestId('list-section-fields').textContent)
      .toBe('new_name,dep,copier');
    // ...and the selection followed the rename.
    expect(screen.getByTestId('editor-field-id').textContent).toBe('new_name');

    // ONE undo restores the whole rename (it was a single commit).
    fireEvent.click(screen.getByTitle(/Undo/));
    await waitFor(() => {
      expect(screen.getByTestId('list-ids').textContent).toBe('old_name,dep,copier');
    });
    expect(screen.getByTestId('list-dep-showif').textContent).toContain('"old_name"');
    expect(screen.getByTestId('list-section-fields').textContent)
      .toBe('old_name,dep,copier');
    // ...and selection is recovered to the RESTORED id, not dropped to the
    // metadata panel (bd polyglot-pdf-6hhc nit 2): the rename moved selection
    // to 'new_name', undo restored 'old_name' at the same position, so the
    // position-preserving re-point re-selects it.
    expect(screen.getByTestId('editor-field-id').textContent).toBe('old_name');
  });

  it('a blocked rename (duplicate id) mutates nothing', async () => {
    render(<App />);
    await loadAndSelect();

    fireEvent.click(screen.getByText('rename-to-duplicate'));

    // Give React a beat; the schema must be untouched.
    await waitFor(() => {
      expect(screen.getByTestId('list-ids').textContent).toBe('old_name,dep,copier');
    });
    expect(screen.getByTestId('editor-field-id').textContent).toBe('old_name');
  });
});
