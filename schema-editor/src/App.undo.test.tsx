/**
 * App-level undo/redo tests (bd polyglot-pdf-v3y8): an edit is reversible via the
 * Undo button / Cmd+Z and re-appliable via Redo, the dirty flag tracks the
 * baseline, and switching forms clears the undo history.
 *
 * Heavy children are mocked; FieldEditor exposes a button that fires
 * onUpdateField so the test can drive a real edit through App's handleUpdateField.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema, FormField } from './types/schema';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/FieldList', () => ({
  // Renders the schema's field-count so we can assert undo/redo propagates to
  // a SECOND panel (not just FieldEditor) -- criterion 1's "all three panels".
  FieldList: ({ schema, onSelectField }: {
    schema: FormSchema | null; onSelectField: (id: string) => void;
  }) => (
    <div>
      {/* render f1's spoken_name FROM the schema so we can assert undo/redo
          propagates to this panel too (criterion 1's "all three panels"). */}
      <span data-testid="list-f1-spoken">
        {schema?.fields.find(f => f.id === 'f1')?.spoken_name ?? '(none)'}
      </span>
      <button onClick={() => onSelectField('f1')}>select-f1</button>
    </div>
  ),
}));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div /> }));
vi.mock('./components/FieldEditor', () => ({
  FieldEditor: ({ field, onUpdateField }: {
    field: FormField | null; onUpdateField: (f: FormField) => void;
  }) => (
    <div>
      <span data-testid="field-spoken">{field?.spoken_name ?? '(none)'}</span>
      <button onClick={() => field && onUpdateField({ ...field, spoken_name: 'EDITED' })}>
        edit-field
      </button>
    </div>
  ),
}));
vi.mock('./components/FormSelector', () => ({
  FormSelector: ({ onSelectForm }: { onSelectForm: (f: unknown) => void }) => (
    <div>
      <button onClick={() => onSelectForm({ name: 'A', pdfPath: '/a.pdf', schemaPath: '/a.json' })}>pick-A</button>
      <button onClick={() => onSelectForm({ name: 'B', pdfPath: '/b.pdf', schemaPath: '/b.json' })}>pick-B</button>
    </div>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'A', form_number: 'A-1', version: '1' },
  fields: [{ id: 'f1', name: 'F1', type: 'text', spoken_name: 'Original' }],
} as unknown as FormSchema;

vi.mock('./utils/schemaLoader', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/schemaLoader')>();
  return { ...actual, loadSchema: vi.fn(async () => JSON.parse(JSON.stringify(SCHEMA))), saveSchema: vi.fn() };
});

import { App } from './App';
import * as loader from './utils/schemaLoader';

async function loadFormAndSelectField() {
  fireEvent.click(screen.getByText('pick-A'));
  await waitFor(() => expect(loader.loadSchema).toHaveBeenCalled());
  fireEvent.click(screen.getByText('select-f1'));
  // FieldEditor shows the selected field's spoken_name once it's loaded+selected.
  await waitFor(() =>
    expect(screen.getByTestId('field-spoken').textContent).toBe('Original'));
}

beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true); });
afterEach(() => vi.clearAllMocks());

describe('App undo/redo', () => {
  it('undo reverses an edit; redo re-applies it', async () => {
    render(<App />);
    await loadFormAndSelectField();

    // Edit f1's spoken_name -> EDITED. BOTH panels (FieldEditor + FieldList)
    // read from the same `schema`, so both reflect the edit.
    fireEvent.click(screen.getByText('edit-field'));
    expect(screen.getByTestId('field-spoken').textContent).toBe('EDITED');
    expect(screen.getByTestId('list-f1-spoken').textContent).toBe('EDITED');
    await waitFor(() => expect(screen.getByText(/Unsaved changes/)).toBeTruthy());

    // Undo -> back to Original in BOTH panels, dirty cleared (at the baseline).
    fireEvent.click(screen.getByText('Undo'));
    await waitFor(() => expect(screen.getByTestId('field-spoken').textContent).toBe('Original'));
    expect(screen.getByTestId('list-f1-spoken').textContent).toBe('Original');
    expect(screen.queryByText(/Unsaved changes/)).toBeNull();

    // Redo -> EDITED again, dirty set.
    fireEvent.click(screen.getByText('Redo'));
    await waitFor(() => expect(screen.getByTestId('field-spoken').textContent).toBe('EDITED'));
    expect(screen.getByText(/Unsaved changes/)).toBeTruthy();
  });

  it('Cmd+Z / Cmd+Shift+Z drive undo and redo', async () => {
    render(<App />);
    await loadFormAndSelectField();
    fireEvent.click(screen.getByText('edit-field'));
    expect(screen.getByTestId('field-spoken').textContent).toBe('EDITED');

    fireEvent.keyDown(window, { key: 'z', metaKey: true });
    await waitFor(() => expect(screen.getByTestId('field-spoken').textContent).toBe('Original'));

    fireEvent.keyDown(window, { key: 'z', metaKey: true, shiftKey: true });
    await waitFor(() => expect(screen.getByTestId('field-spoken').textContent).toBe('EDITED'));
  });

  it('Undo/Redo buttons disable at the ends of the stack', async () => {
    render(<App />);
    await loadFormAndSelectField();
    // Fresh load: nothing to undo or redo.
    expect((screen.getByText('Undo') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText('Redo') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText('edit-field'));
    await waitFor(() => expect((screen.getByText('Undo') as HTMLButtonElement).disabled).toBe(false));
    expect((screen.getByText('Redo') as HTMLButtonElement).disabled).toBe(true);
  });

  it('switching forms clears the undo history', async () => {
    render(<App />);
    await loadFormAndSelectField();
    fireEvent.click(screen.getByText('edit-field'));
    await waitFor(() => expect((screen.getByText('Undo') as HTMLButtonElement).disabled).toBe(false));

    // Switch to form B -> history reset, Undo disabled again. Poll the
    // observable (button disabled) -- the history clears only after the async
    // load resolves, which is a tick after loadSchema is *called*.
    fireEvent.click(screen.getByText('pick-B'));
    await waitFor(() =>
      expect((screen.getByText('Undo') as HTMLButtonElement).disabled).toBe(true));
  });
});
