/**
 * App's unsaved-edits guard for hiding a form (bd polyglot-pdf-n5fwd).
 *
 * WHY THIS FILE EXISTS. Hiding the OPEN kit closes the editor, which throws
 * away unsaved schema edits and the whole undo stack. Both catalogues consult
 * `confirmDiscardOnHide` before doing that -- and both catalogue test suites
 * inject a `vi.fn()` stub for it, so the REAL function, the one whose entire
 * purpose is preventing silent data loss, was pinned by nothing. Reverting its
 * body to `() => true` reinstated the original bug with the full suite green.
 *
 * That is the shape scar #9 warns about: the guard is tested everywhere except
 * where it is defined. These tests drive App's own implementation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import type { FormSchema } from './types/schema';
import type { CatalogueEntry } from './utils/formKitDirectory';

vi.mock('./components/PDFViewer', () => ({ PDFViewer: () => <div data-testid="pdf" /> }));
// FieldEditor only mounts once a field is SELECTED, so the list has to offer
// the selection first -- an edit cannot be reached otherwise.
vi.mock('./components/FieldList', () => ({
  FieldList: ({ onSelectField }: { onSelectField?: (id: string) => void }) => (
    <button onClick={() => onSelectField?.('f1')}>select-field</button>
  ),
}));
vi.mock('./components/ValidationPanel', () => ({ ValidationPanel: () => <div /> }));

// The catalogue is replaced by two buttons: one opens the kit, the other calls
// the guard App handed down and records what it answered. That answer IS the
// contract -- false means "do not hide", and the catalogues honour it.
let lastAnswer: boolean | null = null;
vi.mock('./components/FormCatalogue', () => ({
  FormCatalogue: ({ onOpenKit, confirmDiscardOnHide }: {
    onOpenKit: (e: CatalogueEntry) => void;
    confirmDiscardOnHide?: () => boolean;
  }) => (
    <div>
      <button onClick={() => onOpenKit(kit())}>open-kit</button>
      <button onClick={() => { lastAnswer = confirmDiscardOnHide?.() ?? null; }}>
        ask-hide
      </button>
    </div>
  ),
}));

// FieldEditor is where an edit originates; expose a button that makes one.
vi.mock('./components/FieldEditor', () => ({
  FieldEditor: ({ onUpdateField }: {
    onUpdateField?: (id: string, patch: Record<string, unknown>) => void;
  }) => (
    <button onClick={() => onUpdateField?.('f1', { name: 'EDITED' })}>
      make-an-edit
    </button>
  ),
}));

vi.mock('./utils/formKitDirectory', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/formKitDirectory')>();
  return {
    ...actual,
    loadKitSchema: async () => JSON.parse(JSON.stringify(SCHEMA)) as FormSchema,
  };
});

vi.mock('./utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/remoteKitStore')>();
  return { ...actual, isHostedMode: () => false, hasBackend: () => false };
});

const SCHEMA: FormSchema = {
  form_metadata: { title: 'W-7', version: '1' },
  sections: [],
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

function kit(): CatalogueEntry {
  return {
    id: 'w7', label: 'W-7', status: 'draft', hasSchema: true, hasPdf: false,
    schemaFile: 'schema.json', pdfFile: 'form.pdf',
    dirHandle: { getFileHandle: async () => ({}) } as unknown as CatalogueEntry['dirHandle'],
  };
}

import { App } from './App';

describe("App's unsaved-edits guard for hiding (bd polyglot-pdf-n5fwd)", () => {
  beforeEach(() => { lastAnswer = null; });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('allows the hide silently when there is nothing to lose', async () => {
    // The common case must not nag: no unsaved edits, no dialog, answer true.
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<App />);
    fireEvent.click(screen.getByText('open-kit'));
    fireEvent.click(await screen.findByText('select-field'));
    await waitFor(() => expect(screen.getByText('make-an-edit')).toBeTruthy());

    fireEvent.click(screen.getByText('ask-hide'));
    expect(lastAnswer).toBe(true);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('ASKS once there are unsaved edits, and relays a refusal', async () => {
    // The whole point. Reverting App's body to `() => true` makes this fail,
    // which is what nothing previously did.
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<App />);
    fireEvent.click(screen.getByText('open-kit'));
    fireEvent.click(await screen.findByText('select-field'));
    await waitFor(() => expect(screen.getByText('make-an-edit')).toBeTruthy());
    fireEvent.click(screen.getByText('make-an-edit'));   // now dirty

    fireEvent.click(screen.getByText('ask-hide'));
    expect(confirmSpy).toHaveBeenCalled();
    expect(lastAnswer).toBe(false);   // the human said no; the hide is refused
  });

  it('relays an ACCEPTANCE, so the human can still choose to lose the edits',
    async () => {
      // A guard that always refuses is its own bug -- the human must be able to
      // say "yes, hide it anyway".
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      render(<App />);
      fireEvent.click(screen.getByText('open-kit'));
      fireEvent.click(await screen.findByText('select-field'));
    await waitFor(() => expect(screen.getByText('make-an-edit')).toBeTruthy());
      fireEvent.click(screen.getByText('make-an-edit'));

      fireEvent.click(screen.getByText('ask-hide'));
      expect(lastAnswer).toBe(true);
    });
});
