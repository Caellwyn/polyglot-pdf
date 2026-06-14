/**
 * App-level save-flow tests (bd polyglot-pdf-s1e2): the ONE-STEP re-save is the
 * core criterion-1 mechanism (first save picks a destination; the second save
 * reuses the held handle with NO second prompt). The util round-trip is covered
 * in fileSystemAccess.test.ts; this verifies App actually holds + reuses the
 * handle and clears it on form-switch.
 *
 * The heavy children (PDFViewer/FieldList/FieldEditor/ValidationPanel) are mocked
 * so the test exercises only App's save orchestration, not PDF.js.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { FormSchema } from './types/schema';

// --- mock the heavy children + the network schema load --------------------- //
vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
vi.mock('./components/FieldList', () => ({ FieldList: () => <div data-testid="list" /> }));
vi.mock('./components/FieldEditor', () => ({ FieldEditor: () => <div data-testid="editor" /> }));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div data-testid="vp" /> }));
vi.mock('./components/FormSelector', () => ({
  FormSelector: ({ onSelectForm }: { onSelectForm: (f: unknown) => void }) => (
    <div>
      <button onClick={() => onSelectForm({
        name: 'A', pdfPath: '/a.pdf', schemaPath: '/schemas/a/a.json',
      })}>pick-A</button>
      <button onClick={() => onSelectForm({
        name: 'B', pdfPath: '/b.pdf', schemaPath: '/schemas/b/b.json',
      })}>pick-B</button>
    </div>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'A', form_number: 'A-1', version: '1' },
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
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

function makeWritable() {
  return { write: vi.fn(async () => {}), close: vi.fn(async () => {}) };
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).showSaveFilePicker;
  vi.clearAllMocks();
});

describe('App one-step save (File System Access)', () => {
  beforeEach(() => {
    // confirm() is hit on form-switch with unsaved changes; default allow.
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('prompts once, then re-saves to the same handle without re-prompting', async () => {
    const writable = makeWritable();
    const handle = { name: 'a_edited.json', createWritable: vi.fn(async () => writable),
                     getFile: vi.fn() };
    const picker = vi.fn(async () => handle);
    (window as unknown as Record<string, unknown>).showSaveFilePicker = picker;

    render(<App />);
    fireEvent.click(screen.getByText('pick-A'));
    await waitFor(() => expect(loader.loadSchema).toHaveBeenCalled());

    // First save: picks a destination.
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(picker).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(writable.write).toHaveBeenCalledTimes(1));

    // Second save: reuses the handle -- NO second picker prompt.
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(writable.write).toHaveBeenCalledTimes(2));
    expect(picker).toHaveBeenCalledTimes(1); // still once
  });

  it('clears the handle on form switch (does not save form B over form A)', async () => {
    const writable = makeWritable();
    const handle = { name: 'a_edited.json', createWritable: vi.fn(async () => writable),
                     getFile: vi.fn() };
    const picker = vi.fn(async () => handle);
    (window as unknown as Record<string, unknown>).showSaveFilePicker = picker;

    render(<App />);
    fireEvent.click(screen.getByText('pick-A'));
    await waitFor(() => expect(loader.loadSchema).toHaveBeenCalledTimes(1));
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(picker).toHaveBeenCalledTimes(1));

    // Switch to form B -> the prior handle must be dropped so the next save
    // prompts again (for B's destination), not overwrite A's file.
    fireEvent.click(screen.getByText('pick-B'));
    await waitFor(() => expect(loader.loadSchema).toHaveBeenCalledTimes(2));
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(picker).toHaveBeenCalledTimes(2)); // prompted again
  });

  it('falls back to download when the API is unsupported', async () => {
    // no window.showSaveFilePicker installed -> fsAccess is false
    render(<App />);
    fireEvent.click(screen.getByText('pick-A'));
    await waitFor(() => expect(loader.loadSchema).toHaveBeenCalled());
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(loader.saveSchema).toHaveBeenCalledTimes(1));
  });
});
