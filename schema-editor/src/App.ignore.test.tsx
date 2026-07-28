/**
 * Ignore/restore/undo through App's REAL handlers (bd polyglot-pdf-mzkw).
 *
 * The point of this file is the WIRING, not the pure ops (ignoreField.test.ts
 * owns those): that App.handleIgnoreField quarantines through commitSchema,
 * that handleRestoreField brings the field back, and that ONE Ctrl+Z reverses
 * a quarantine -- field, section membership and stash together -- because the
 * whole move lands in a single history snapshot.
 *
 * An earlier version of this file was VACUOUS: it computed a quarantined
 * schema locally and never fed it to App, so no-op'ing the handlers still
 * passed. Every test here now drives App's own callbacks and asserts on
 * App-rendered state, and each was checked to FAIL when its handler is gutted.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormField, FormSchema } from './types/schema';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
// Exposes onSelectField so the test can fire a lint finding that names a
// PARKED field -- the click-to-focus dead end App guards against.
vi.mock('./components/ValidationPanel', () => ({
  ValidationPanel: ({ onSelectField }: { onSelectField?: (id: string) => void }) => (
    <button onClick={() => onSelectField?.('f2')}>finding-f2</button>
  ),
}));
// FieldEditor exposes App's ignore callback the way the real review dropdown
// does, so the test drives handleIgnoreField itself.
vi.mock('./components/FieldEditor', () => ({
  FieldEditor: ({ field, onIgnoreField, ignoreBlocked }: {
    field: FormField | null;
    onIgnoreField?: (id: string) => string | null;
    ignoreBlocked?: string | null;
  }) => (
    <div>
      <span data-testid="editor-field">{field?.id ?? '(none)'}</span>
      <span data-testid="ignore-blocked">{ignoreBlocked ?? '(allowed)'}</span>
      <span data-testid="ignore-result">{''}</span>
      <button onClick={() => {
        const reason = onIgnoreField?.(field?.id ?? '');
        const slot = screen.getByTestId('ignore-result');
        slot.textContent = reason ?? 'ok';
      }}>
        ignore-selected
      </button>
    </div>
  ),
}));
vi.mock('./components/FieldList', () => ({
  FieldList: ({ schema, onSelectField, onRestoreField }: {
    schema: FormSchema | null;
    onSelectField: (id: string) => void;
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
        {(((schema as unknown as Record<string, unknown>)?._ignored_fields as unknown[]) ?? []).length}
      </span>
      <button onClick={() => onSelectField('f2')}>select-f2</button>
      <button onClick={() => onSelectField('f3')}>select-f3</button>
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
    // f3 is REQUIRED, so it exercises the gate through App's own wiring.
    { id: 'f3', name: 'F3', type: 'text', spoken_name: 'three', section_id: 's1',
      validation: { required: true } },
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

const liveIds = () => screen.getByTestId('live-ids').textContent;
const sectionIds = () => screen.getByTestId('section-ids').textContent;
const stashCount = () => screen.getByTestId('stash-count').textContent;

beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true); });
afterEach(() => vi.clearAllMocks());

describe('App ignore/restore/undo wiring (bd mzkw)', () => {
  it('quarantines through App: field, section slot and stash all move', async () => {
    render(<App />);
    await loadForm();
    fireEvent.click(screen.getByText('select-f2'));
    await waitFor(() =>
      expect(screen.getByTestId('editor-field').textContent).toBe('f2'));

    fireEvent.click(screen.getByText('ignore-selected'));

    await waitFor(() => expect(liveIds()).toBe('f1,f3'));
    expect(sectionIds()).toBe('f1,f3');
    expect(stashCount()).toBe('1');
    // Selection is dropped -- the field has left fields[], so there is no pane.
    expect(screen.getByTestId('editor-field').textContent).toBe('(none)');
  });

  it('ONE Ctrl+Z reverses the whole quarantine', async () => {
    render(<App />);
    await loadForm();
    fireEvent.click(screen.getByText('select-f2'));
    fireEvent.click(screen.getByText('ignore-selected'));
    await waitFor(() => expect(liveIds()).toBe('f1,f3'));

    // A single undo, because the move committed as ONE schema snapshot.
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });

    await waitFor(() => expect(liveIds()).toBe('f1,f2,f3'));
    expect(sectionIds()).toBe('f1,f2,f3');
    expect(stashCount()).toBe('0');
  });

  it('un-ignore through App restores the exact section slot', async () => {
    render(<App />);
    await loadForm();
    fireEvent.click(screen.getByText('select-f2'));
    fireEvent.click(screen.getByText('ignore-selected'));
    await waitFor(() => expect(stashCount()).toBe('1'));

    fireEvent.click(screen.getByText('restore-f2'));

    await waitFor(() => expect(stashCount()).toBe('0'));
    expect(liveIds()).toBe('f1,f3,f2');       // appended to fields[]...
    expect(sectionIds()).toBe('f1,f2,f3');    // ...but back in its section slot
  });

  it('explains, rather than dead-ends, when a finding names a parked field', async () => {
    // Lint findings persisted before a field was ignored still name it. The
    // editor pane has nothing to render for a parked id, so clicking would
    // otherwise fall silently back to the metadata panel (fresh-eyes).
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    render(<App />);
    await loadForm();
    fireEvent.click(screen.getByText('select-f2'));
    fireEvent.click(screen.getByText('ignore-selected'));
    await waitFor(() => expect(liveIds()).toBe('f1,f3'));

    fireEvent.click(screen.getByText('finding-f2'));

    expect(alertSpy).toHaveBeenCalledOnce();
    expect(alertSpy.mock.calls[0][0]).toContain('ignored');
    // ...and it did NOT select the parked id (which would render nothing).
    expect(screen.getByTestId('editor-field').textContent).toBe('(none)');
  });

  it('still focuses a LIVE field from a finding', async () => {
    // The guard must not break the ordinary click-to-focus path.
    render(<App />);
    await loadForm();
    fireEvent.click(screen.getByText('finding-f2'));
    await waitFor(() =>
      expect(screen.getByTestId('editor-field').textContent).toBe('f2'));
  });

  it('App refuses to quarantine a required field, with the reason', async () => {
    render(<App />);
    await loadForm();
    fireEvent.click(screen.getByText('select-f3')); // f3 is required
    await waitFor(() =>
      expect(screen.getByTestId('editor-field').textContent).toBe('f3'));

    // The gate is surfaced BEFORE the author acts...
    expect(screen.getByTestId('ignore-blocked').textContent)
      .toContain('marked required');

    // ...and the handler refuses even if called anyway.
    fireEvent.click(screen.getByText('ignore-selected'));
    await waitFor(() =>
      expect(screen.getByTestId('ignore-result').textContent)
        .toContain('marked required'));
    expect(liveIds()).toBe('f1,f2,f3');
    expect(stashCount()).toBe('0');
  });
});
