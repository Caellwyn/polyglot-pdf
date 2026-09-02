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
  FormCatalogue: ({ onOpenKit, confirmDiscardOnHide, clearOpenKit }: {
    onOpenKit: (e: CatalogueEntry) => void;
    confirmDiscardOnHide?: () => boolean;
    clearOpenKit?: (reason?: 'hidden-by-other') => void;
  }) => (
    <div>
      <button onClick={() => onOpenKit(kit())}>open-kit</button>
      <button onClick={() => { lastAnswer = confirmDiscardOnHide?.() ?? null; }}>
        ask-hide
      </button>
      {/* Stands in for the real catalogues' unwind effect, which fires from a
          background refresh when another author hid the open kit. It calls the
          same function with the same argument they pass. */}
      <button onClick={() => clearOpenKit?.('hidden-by-other')}>
        other-hid-it
      </button>
      {/* The SAME function with NO reason -- every other close in the app
          (folder change, delete, this session's own hide). Must stay silent. */}
      <button onClick={() => clearOpenKit?.()}>close-normally</button>
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

/**
 * The CONCURRENT case (bd polyglot-pdf-0s2wf). When ANOTHER author hides the
 * form this session has open, the next background refresh closes it here --
 * and no dialog can be asked, because that unwind runs outside any user
 * gesture. bd n5fwd shipped that close SILENTLY: the editor emptied itself
 * with no explanation, and any unsaved edits went with it.
 *
 * These drive App's real clearOpenKit, not a stub. Both catalogue suites pass
 * a vi.fn() for it, so a test living there would pin nothing.
 */
describe('App tells the user when someone else closed their form', () => {
  const openAndEdit = async (dirty: boolean) => {
    render(<App />);
    fireEvent.click(screen.getByText('open-kit'));
    fireEvent.click(await screen.findByText('select-field'));
    await waitFor(() => expect(screen.getByText('make-an-edit')).toBeTruthy());
    if (dirty) fireEvent.click(screen.getByText('make-an-edit'));
  };

  beforeEach(() => { lastAnswer = null; });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('says the unsaved changes were LOST when there were some', async () => {
    await openAndEdit(true);
    fireEvent.click(screen.getByText('other-hid-it'));

    const banner = await screen.findByText(/Someone else hid this form/);
    expect(banner.textContent).toContain('unsaved changes were lost');
    // Retrievability: the form itself is fine, and the banner must say how to
    // get it back -- that is the whole promise the Hide button makes.
    expect(banner.textContent).toContain('Show hidden');
  });

  it('does NOT claim a loss when the work was already saved', async () => {
    // Overclaiming is its own bug: a user told their work is gone will go
    // looking for it. This is the branch a fixed "your changes were lost"
    // string would fail.
    await openAndEdit(false);
    fireEvent.click(screen.getByText('other-hid-it'));

    const banner = await screen.findByText(/Someone else hid this form/);
    expect(banner.textContent).toContain('Nothing was lost');
    expect(banner.textContent).not.toContain('unsaved changes were lost');
  });

  it('stays SILENT for an ordinary close, which the user did themselves',
    async () => {
      // The reason is what distinguishes the two. A clearOpenKit that always
      // banners would fire on every folder change and every self-hide -- the
      // banner would then be noise, and noise gets ignored.
      await openAndEdit(true);
      fireEvent.click(screen.getByText('close-normally'));

      await waitFor(() =>
        expect(screen.queryByText('make-an-edit')).toBeNull());   // it DID close
      expect(screen.queryByText(/Someone else hid this form/)).toBeNull();
    });

  it('can be dismissed, and does not come back on its own', async () => {
    // It is a banner, not a modal: the editor stays usable underneath and the
    // user closes it when they have read it.
    await openAndEdit(true);
    fireEvent.click(screen.getByText('other-hid-it'));
    await screen.findByText(/Someone else hid this form/);

    fireEvent.click(screen.getByLabelText('Dismiss'));
    await waitFor(() =>
      expect(screen.queryByText(/Someone else hid this form/)).toBeNull());
  });
});
