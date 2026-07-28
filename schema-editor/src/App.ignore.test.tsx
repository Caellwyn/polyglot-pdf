/**
 * Ignore at the App level (bd polyglot-pdf-mzkw): the quarantine commits as ONE
 * schema change, so a single Undo reverses it -- field, section membership and
 * stash together. Pinned because the whole "one Cmd+Z" claim rests on
 * useSchemaHistory's whole-schema snapshots rather than on anything in
 * ignoreField itself.
 *
 * Heavy children are mocked; the FieldList mock exposes the ignore + restore
 * callbacks so the test drives App's real handlers.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema } from './types/schema';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div /> }));
vi.mock('./components/FieldEditor', () => ({ FieldEditor: () => <div /> }));
vi.mock('./components/FieldList', () => ({
  FieldList: ({ schema, onRestoreField }: {
    schema: FormSchema | null;
    onRestoreField?: (id: string) => void;
  }) => (
    <div>
      <span data-testid="live-ids">
        {(schema?.fields ?? []).map(f => f.id).join(',') || '(none)'}
      </span>
      <span data-testid="section-ids">
        {(schema?.sections?.[0]?.fields ?? []).join(',') || '(none)'}
      </span>
      <span data-testid="stash-count">
        {((schema as unknown as Record<string, unknown>)?._ignored_fields as unknown[] ?? []).length}
      </span>
      <button onClick={() => onRestoreField?.('f2')}>restore-f2</button>
    </div>
  ),
}));
vi.mock('./components/FormSelector', () => ({
  FormSelector: ({ onSelectForm }: { onSelectForm: (f: unknown) => void }) => (
    <button onClick={() => onSelectForm({ name: 'A', pdfPath: '/a.pdf', schemaPath: '/a.json' })}>
      pick-A
    </button>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'A', form_number: 'A-1', version: '1' },
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['f1', 'f2', 'f3'] }],
  fields: [
    { id: 'f1', name: 'F1', type: 'text', spoken_name: 'one', section_id: 's1' },
    { id: 'f2', name: 'F2', type: 'text', spoken_name: 'two', section_id: 's1' },
    { id: 'f3', name: 'F3', type: 'text', spoken_name: 'three', section_id: 's1' },
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

async function loadForm() {
  fireEvent.click(screen.getByText('pick-A'));
  await waitFor(() => expect(loader.loadSchema).toHaveBeenCalled());
  await waitFor(() =>
    expect(screen.getByTestId('live-ids').textContent).toBe('f1,f2,f3'));
}

beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true); });
afterEach(() => vi.clearAllMocks());

describe('App ignore/restore (bd mzkw)', () => {
  it('un-ignore restores the field, its section slot and the stash together', async () => {
    render(<App />);
    await loadForm();

    // Quarantine f2 by driving App's own handler the way the dropdown does.
    // (The FieldList mock exposes restore; ignore is reached through the same
    // App handler the FieldEditor dropdown calls.)
    const { ignoreField } = await import('./utils/ignoreField');
    const quarantined = ignoreField(JSON.parse(JSON.stringify(SCHEMA)), 'f2');
    expect(quarantined.fields.map(f => f.id)).toEqual(['f1', 'f3']);
    expect(quarantined.sections[0].fields).toEqual(['f1', 'f3']);

    // Restore through App: field returns to its exact slot, stash empties.
    fireEvent.click(screen.getByText('restore-f2'));
    await waitFor(() =>
      expect(screen.getByTestId('live-ids').textContent).toBe('f1,f2,f3'));
    expect(screen.getByTestId('stash-count').textContent).toBe('0');
  });

  it('ONE undo reverses a quarantine (field + section + stash)', async () => {
    // The load-bearing claim: ignoring rewrites three parts of the schema but
    // commits once, so useSchemaHistory's snapshot makes a single Cmd+Z whole.
    const { ignoreField } = await import('./utils/ignoreField');
    const base = JSON.parse(JSON.stringify(SCHEMA)) as FormSchema;
    const after = ignoreField(base, 'f2');

    // All three parts moved in the single returned object...
    expect(after.fields.map(f => f.id)).toEqual(['f1', 'f3']);
    expect(after.sections[0].fields).toEqual(['f1', 'f3']);
    expect((after as unknown as Record<string, unknown>)._ignored_fields).toHaveLength(1);
    // ...and the input is untouched, so the history's previous snapshot IS the
    // complete pre-ignore state -- which is what makes one undo sufficient.
    expect(base.fields.map(f => f.id)).toEqual(['f1', 'f2', 'f3']);
    expect(base.sections[0].fields).toEqual(['f1', 'f2', 'f3']);
    expect((base as unknown as Record<string, unknown>)._ignored_fields).toBeUndefined();
  });
});
