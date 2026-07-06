/**
 * App hosted-delivery-mode tests (bd polyglot-pdf-92qe.2).
 *
 * Exit criteria under test:
 * - hosted mode lists kits from the API (drafts included), opens one (schema +
 *   PDF via the routes), saves via PUT, marks complete via POST;
 * - the access-code flow prompts when no code is stored, re-prompts on 401, and
 *   hosted mode never touches the File System Access APIs;
 * - default (non-hosted) behavior is unchanged when the flag is unset (the
 *   existing App suites cover it; a sanity check here proves the gate is off).
 *
 * Heavy children are mocked; the remote store's fetch layer is mocked at the
 * module level so App's orchestration (gate -> catalogue -> open -> save) is
 * what runs.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import type { FormSchema } from './types/schema';

// The mock renders pdfPath so tests can assert WHICH blob URL the viewer got
// (the blob-URL lifecycle regression below keys on it).
vi.mock('./components/PDFViewer', () => ({
  PDFViewer: ({ pdfPath }: { pdfPath: string }) => (
    <div data-testid="pdf">{pdfPath}</div>
  ),
}));
vi.mock('./components/FieldList', () => ({ FieldList: () => <div data-testid="list" /> }));
// The panel mock exposes a "repair" button that fires onRepairAll (when the host
// provides it) so App's handleRepairAll wiring is testable through the full tree
// (bd zgln; fresh-eyes: an isolation test of the panel does not cover App's
// wiring to it). data-has-repair reflects whether the host passed the callback.
vi.mock('./components/ValidationPanel', () => ({
  ValidationPanel: ({ onRepairAll }: { onRepairAll?: () => Promise<void> }) => (
    <div data-testid="vp" data-has-repair={onRepairAll ? 'yes' : 'no'}>
      {onRepairAll && (
        <button data-testid="repair-all" onClick={() => void onRepairAll()}>
          repair
        </button>
      )}
    </div>
  ),
}));
// FieldEditor is mocked with an edit button so a test can dirty the schema.
vi.mock('./components/FieldEditor', () => ({
  FieldEditor: ({ onUpdateField, field }: {
    onUpdateField: (f: unknown) => void; field: { id: string } | null;
  }) => (
    <button
      data-testid="edit-field"
      onClick={() => onUpdateField({ id: 'f1', name: 'F1', type: 'text', spoken_name: 'edited' })}
    >
      edit {field?.id ?? 'metadata'}
    </button>
  ),
}));

const SCHEMA: FormSchema = {
  form_metadata: { title: 'Remote Form', version: '1' },
  sections: [],
  fields: [{ id: 'f1', name: 'F1', type: 'text' }],
} as unknown as FormSchema;

const KIT = {
  id: 'draft-kit', label: 'Draft Form', status: 'draft' as const, hasSchema: true,
  hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf',
};

const KIT_B = {
  id: 'second-kit', label: 'Second Form', status: 'draft' as const, hasSchema: true,
  hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf',
};

vi.mock('./utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./utils/remoteKitStore')>();
  return {
    ...actual,
    isHostedMode: vi.fn(() => true),
    probeSession: vi.fn(),
    listRemoteKits: vi.fn(),
    loadRemoteSchema: vi.fn(),
    loadRemotePdfBlobUrl: vi.fn(),
    saveRemoteSchema: vi.fn(),
    setRemoteStatus: vi.fn(),
    repairKit: vi.fn(),
  };
});

import { App } from './App';
import {
  AuthError, clearAccessCode, isHostedMode, listRemoteKits,
  loadRemotePdfBlobUrl, loadRemoteSchema, probeSession, repairKit, saveRemoteSchema,
} from './utils/remoteKitStore';

beforeEach(() => {
  window.localStorage.clear();
  clearAccessCode(); // also drops the module-level in-memory fallback copy
  vi.mocked(isHostedMode).mockReturnValue(true);
  vi.mocked(probeSession).mockResolvedValue({ role: 'editor' });
  vi.mocked(listRemoteKits).mockResolvedValue([KIT]);
  vi.mocked(loadRemoteSchema).mockResolvedValue(
    JSON.parse(JSON.stringify(SCHEMA)) as FormSchema,
  );
  vi.mocked(loadRemotePdfBlobUrl).mockResolvedValue('blob:fake-pdf');
  vi.mocked(saveRemoteSchema).mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  clearAccessCode();
});

/** Enter the access code through the gate and land on the catalogue. */
async function passGate() {
  render(<App />);
  const input = await screen.findByLabelText('Access code');
  fireEvent.change(input, { target: { value: 'sekret' } });
  fireEvent.click(screen.getByText('Open the workspace'));
  await waitFor(() => expect(screen.getByTestId('remote-catalogue')).toBeInTheDocument());
}

describe('App hosted mode (bd 92qe.2)', () => {
  it('prompts for an access code, validates it, and shows the remote catalogue', async () => {
    await passGate();
    expect(probeSession).toHaveBeenCalled();
    // The kit list came from the API, and the local-folder UI never rendered.
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    expect(screen.queryByText('Open form-kits folder')).not.toBeInTheDocument();
  });

  it('a stored code is probed silently on load (no prompt for returning users)', async () => {
    window.localStorage.setItem('schema-editor.accessCode', 'remembered');
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('remote-catalogue')).toBeInTheDocument());
    expect(screen.queryByLabelText('Access code')).not.toBeInTheDocument();
  });

  it('re-prompts when the code is refused (401), with the stored code cleared', async () => {
    window.localStorage.setItem('schema-editor.accessCode', 'stale');
    vi.mocked(probeSession).mockRejectedValue(new AuthError());
    render(<App />);
    // The silent probe fails -> the gate form renders and the code is gone.
    const input = await screen.findByLabelText('Access code');
    expect(input).toBeInTheDocument();
    expect(window.localStorage.getItem('schema-editor.accessCode')).toBeNull();
  });

  it('a NON-auth probe failure (e.g. 503) keeps the stored code and shows why', async () => {
    // Only a REFUSED code may be wiped: a transient server-side issue (surface
    // unconfigured, network blip) must not log every returning contractor out
    // (fresh-eyes gap 2). The error is shown even though the probe was silent.
    window.localStorage.setItem('schema-editor.accessCode', 'still-good');
    vi.mocked(probeSession).mockRejectedValue(
      new Error('The editor surface is not configured on this server'),
    );
    render(<App />);
    await screen.findByLabelText('Access code');
    expect(window.localStorage.getItem('schema-editor.accessCode')).toBe('still-good');
    expect(screen.getByText(/not configured/)).toBeInTheDocument();
  });

  it('opens a kit from the remote catalogue: schema + PDF via the routes', async () => {
    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('pdf')).toBeInTheDocument());
    expect(loadRemoteSchema).toHaveBeenCalledWith('draft-kit');
    expect(loadRemotePdfBlobUrl).toHaveBeenCalledWith('draft-kit');
  });

  it('Cmd+S saves the edited schema back through the remote store', async () => {
    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());

    // Dirty the schema, then save.
    fireEvent.click(screen.getByTestId('edit-field'));
    fireEvent.keyDown(window, { key: 's', metaKey: true });

    await waitFor(() => expect(saveRemoteSchema).toHaveBeenCalledTimes(1));
    const [kitId, saved] = vi.mocked(saveRemoteSchema).mock.calls[0];
    expect(kitId).toBe('draft-kit');
    expect((saved as FormSchema).fields[0]).toMatchObject({ spoken_name: 'edited' });
    // The header reflects the persisted state.
    await waitFor(() =>
      expect(screen.getByText(/Saved to the shared workspace/)).toBeInTheDocument());
  });

  it('author Repair-all repairs the kit then reloads the repaired schema (bd zgln)', async () => {
    vi.mocked(probeSession).mockResolvedValue({ role: 'author' });
    vi.mocked(repairKit).mockResolvedValue({
      applied: 2, dropped: 0, aliasHits: 1, repairs: [], errorCount: 0, warningCount: 0,
    });
    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('vp')).toBeInTheDocument());
    // The host passed onRepairAll (author tier on an open kit).
    expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('yes');

    vi.mocked(loadRemoteSchema).mockClear();
    fireEvent.click(screen.getByTestId('repair-all'));
    await waitFor(() => expect(repairKit).toHaveBeenCalledWith('draft-kit'));
    // The repaired schema is reloaded from the store after the repair.
    await waitFor(() => expect(loadRemoteSchema).toHaveBeenCalledWith('draft-kit'));
  });

  it('editor tier gets NO Repair-all callback (author-only)', async () => {
    vi.mocked(probeSession).mockResolvedValue({ role: 'editor' });
    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('vp')).toBeInTheDocument());
    expect(screen.getByTestId('vp').getAttribute('data-has-repair')).toBe('no');
    expect(screen.queryByTestId('repair-all')).toBeNull();
  });

  it('a repair AuthError re-gates without destroying the open kit', async () => {
    vi.mocked(probeSession).mockResolvedValue({ role: 'author' });
    vi.mocked(repairKit).mockRejectedValue(new AuthError());
    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('repair-all')).toBeInTheDocument());
    // A dead code mid-repair drops back to the access gate (probeSession still
    // resolves author here, so the gate would re-open; assert the re-prompt).
    vi.mocked(probeSession).mockRejectedValue(new AuthError());
    fireEvent.click(screen.getByTestId('repair-all'));
    await screen.findByLabelText('Access code');
  });

  it('a repair in flight does NOT clobber a kit opened mid-repair (bd r5vp)', async () => {
    // Stale-open guard: repair kit A (slow), open kit B before it resolves;
    // the repair reload must NOT overwrite B's displayed schema with A's.
    vi.mocked(probeSession).mockResolvedValue({ role: 'author' });
    vi.mocked(listRemoteKits).mockResolvedValue([KIT, KIT_B]);
    vi.mocked(loadRemotePdfBlobUrl).mockResolvedValue('blob:pdf');
    // Per-kit schemas so we can tell which one is displayed by field id.
    vi.mocked(loadRemoteSchema).mockImplementation(async (kitId: string) => ({
      ...JSON.parse(JSON.stringify(SCHEMA)),
      fields: [{ id: kitId === 'second-kit' ? 'B_field' : 'A_field',
                 name: 'X', type: 'text', spoken_name: 'x' }],
    } as unknown as FormSchema));
    // repairKit for kit A hangs until we release it.
    let releaseRepair: () => void = () => {};
    vi.mocked(repairKit).mockReturnValue(
      new Promise((resolve) => { releaseRepair = () => resolve({
        applied: 1, dropped: 0, aliasHits: 0, repairs: [], errorCount: 0, warningCount: 0,
      }); }),
    );

    await passGate();
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));           // open kit A
    await waitFor(() => expect(screen.getByTestId('repair-all')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('repair-all'));          // repair A (hangs)
    await waitFor(() => expect(repairKit).toHaveBeenCalledWith('draft-kit'));

    // Open kit B while A's repair is still in flight.
    fireEvent.click(screen.getByText('Second Form'));
    await waitFor(() => expect(loadRemoteSchema).toHaveBeenCalledWith('second-kit'));

    // Now let A's repair finish -- its reload must be abandoned (stale token).
    vi.mocked(loadRemoteSchema).mockClear();
    releaseRepair();
    await waitFor(() => expect(repairKit).toHaveBeenCalledTimes(1));
    // The repair's reload of kit A must NOT have run after B superseded it.
    await new Promise((r) => setTimeout(r, 0));
    expect(loadRemoteSchema).not.toHaveBeenCalledWith('draft-kit');
  });

  it('hosted mode never calls the File System Access pickers', async () => {
    const savePicker = vi.fn();
    const dirPicker = vi.fn();
    (window as unknown as Record<string, unknown>).showSaveFilePicker = savePicker;
    (window as unknown as Record<string, unknown>).showDirectoryPicker = dirPicker;
    try {
      await passGate();
      fireEvent.click(screen.getByText('Draft Form'));
      await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());
      fireEvent.click(screen.getByTestId('edit-field'));
      fireEvent.keyDown(window, { key: 's', metaKey: true });
      await waitFor(() => expect(saveRemoteSchema).toHaveBeenCalled());
      expect(savePicker).not.toHaveBeenCalled();
      expect(dirPicker).not.toHaveBeenCalled();
      // FS-only affordances are hidden in hosted mode.
      expect(screen.queryByText('Save As...')).not.toBeInTheDocument();
      expect(screen.queryByText('Reload from file')).not.toBeInTheDocument();
    } finally {
      delete (window as unknown as Record<string, unknown>).showSaveFilePicker;
      delete (window as unknown as Record<string, unknown>).showDirectoryPicker;
    }
  });

  it('a mid-session 401 on save drops back to the access gate', async () => {
    await passGate();
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-field'));
    vi.mocked(saveRemoteSchema).mockRejectedValue(new AuthError());
    vi.mocked(probeSession).mockRejectedValue(new AuthError()); // stored code is dead too
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(screen.getByLabelText('Access code')).toBeInTheDocument());
  });

  it('a failed kit-B open keeps kit A pointing at a LIVE blob URL (fresh-eyes r2)', async () => {
    // Opening kit B while A is open must not revoke A's PDF blob URL until
    // B's fetches SUCCEED: if B's PDF fetch 401s, the auth-drop path preserves
    // the open kit -- which must still render, not point at a revoked URL.
    const revoke = vi.fn();
    const origRevoke = URL.revokeObjectURL;
    URL.revokeObjectURL = revoke as typeof URL.revokeObjectURL;
    try {
      vi.mocked(listRemoteKits).mockResolvedValue([KIT, KIT_B]);
      vi.mocked(loadRemotePdfBlobUrl).mockResolvedValueOnce('blob:kit-a');
      await passGate();
      fireEvent.click(screen.getByText('Draft Form'));
      await waitFor(() =>
        expect(screen.getByTestId('pdf')).toHaveTextContent('blob:kit-a'));

      // Open kit B: schema loads, but the PDF fetch answers 401.
      vi.mocked(loadRemotePdfBlobUrl).mockRejectedValueOnce(new AuthError());
      vi.mocked(probeSession).mockRejectedValueOnce(new AuthError());
      fireEvent.click(screen.getByText('Second Form'));
      const input = await screen.findByLabelText('Access code');

      // Kit A's URL was never revoked mid-open...
      expect(revoke).not.toHaveBeenCalledWith('blob:kit-a');

      // ...and after re-auth the preserved kit A still renders its LIVE URL.
      vi.mocked(probeSession).mockResolvedValue({ role: 'editor' });
      fireEvent.change(input, { target: { value: 'new-code' } });
      fireEvent.click(screen.getByText('Open the workspace'));
      await waitFor(() =>
        expect(screen.getByTestId('pdf')).toHaveTextContent('blob:kit-a'));
    } finally {
      URL.revokeObjectURL = origRevoke;
    }
  });

  it('unsaved edits SURVIVE a 401 gate round trip and save under the new code', async () => {
    // Deliberate behavior (fresh-eyes gap 4, resolved as keep-the-work): a code
    // rotation mid-polish must not destroy a contractor's unsaved edits. After
    // re-entering a valid code the editor resumes where it was, and the save
    // goes through re-authenticated with the NEW code.
    await passGate();
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-field')); // dirty the schema

    vi.mocked(saveRemoteSchema).mockRejectedValueOnce(new AuthError());
    vi.mocked(probeSession).mockRejectedValueOnce(new AuthError()); // stored code dead
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    const input = await screen.findByLabelText('Access code');

    // Re-enter a (new) valid code -- probeSession succeeds again.
    vi.mocked(probeSession).mockResolvedValue({ role: 'editor' });
    vi.mocked(saveRemoteSchema).mockResolvedValue(undefined);
    fireEvent.change(input, { target: { value: 'rotated-code' } });
    fireEvent.click(screen.getByText('Open the workspace'));

    // The open kit + dirty edit are still there (no teardown)...
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());
    expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
    // ...and the save now lands with the edited field intact.
    fireEvent.keyDown(window, { key: 's', metaKey: true });
    await waitFor(() => expect(saveRemoteSchema).toHaveBeenCalledTimes(2));
    const [, saved] = vi.mocked(saveRemoteSchema).mock.calls[1];
    expect((saved as FormSchema).fields[0]).toMatchObject({ spoken_name: 'edited' });
  });

  it('non-hosted default renders the local catalogue path unchanged', async () => {
    vi.mocked(isHostedMode).mockReturnValue(false);
    render(<App />);
    // No gate, no remote catalogue -- the local front door renders instead
    // (in jsdom the directory API is absent, so FormCatalogue shows its
    // unsupported-browser message: that IS the local path).
    expect(screen.queryByTestId('access-code-gate')).not.toBeInTheDocument();
    expect(screen.queryByTestId('remote-catalogue')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/File System Access directory API/)).toBeInTheDocument());
    expect(probeSession).not.toHaveBeenCalled();
  });
});

describe('App hosted mode Codex r1 fixes (PR #280)', () => {
  it('edits made WHILE a save is in flight stay marked unsaved', async () => {
    // The PUT resolves only when we say so; the user edits mid-flight.
    let resolveSave: () => void = () => {};
    vi.mocked(saveRemoteSchema).mockImplementation(
      () => new Promise<void>((res) => { resolveSave = res; }),
    );
    await passGate();
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('edit-field')); // dirty -> payload v1
    fireEvent.keyDown(window, { key: 's', metaKey: true }); // PUT starts (pending)
    await waitFor(() => expect(saveRemoteSchema).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId('edit-field')); // NEW edit mid-flight
    resolveSave(); // the OLD payload's PUT completes

    // The newer edit was never sent -- the state must still read unsaved
    // (marking it clean would lose it on unload -- Codex P1, PR #280).
    await waitFor(() =>
      expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument());
    expect(screen.queryByText(/Saved to the shared workspace/)).not.toBeInTheDocument();
  });

  it('a slow kit-A open never overwrites a faster kit-B open (race guard)', async () => {
    vi.mocked(listRemoteKits).mockResolvedValue([KIT, KIT_B]);
    // Kit A's schema resolves LATE; kit B's immediately.
    let resolveA: (s: FormSchema) => void = () => {};
    vi.mocked(loadRemoteSchema).mockImplementation((id: string) => {
      if (id === 'draft-kit') {
        return new Promise<FormSchema | null>((res) => { resolveA = res as never; });
      }
      return Promise.resolve(
        JSON.parse(JSON.stringify({ ...SCHEMA, form_metadata: { title: 'B', version: '1' } })) as FormSchema,
      );
    });
    vi.mocked(loadRemotePdfBlobUrl).mockImplementation(
      (id: string) => Promise.resolve(`blob:${id}`),
    );

    await passGate();
    fireEvent.click(screen.getByText('Draft Form'));   // A: hangs
    fireEvent.click(screen.getByText('Second Form'));  // B: completes
    await waitFor(() =>
      expect(screen.getByTestId('pdf')).toHaveTextContent('blob:second-kit'));

    // A's slow response lands AFTER B -- it must be discarded, not applied.
    resolveA(JSON.parse(JSON.stringify(SCHEMA)) as FormSchema);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId('pdf')).toHaveTextContent('blob:second-kit');
  });
});

describe('App hosted UX pass (bd 92qe.5)', () => {
  /** Open the draft kit and dirty it (enables Save). Dismisses the guide. */
  async function openAndDirtyKit() {
    await passGate();
    fireEvent.click(screen.getByText('Got it')); // clear the first-run guide
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Draft Form'));
    await waitFor(() => expect(screen.getByTestId('edit-field')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('edit-field'));
  }

  it('a failed remote save shows a dismissible banner and keeps the editor alive', async () => {
    vi.mocked(saveRemoteSchema).mockRejectedValue(
      new Error('Kit is complete -- revert to draft before saving'),
    );
    await openAndDirtyKit();
    fireEvent.click(screen.getByText('Save (Cmd+S)'));

    // The failure renders as a banner, NOT the full-screen error state...
    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent('revert to draft');
    // ...so the editor (and the unsaved work) is still fully mounted.
    expect(screen.getByTestId('list')).toBeInTheDocument();
    expect(screen.getByTestId('edit-field')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Error' })).not.toBeInTheDocument();

    // Dismissing clears the banner without touching the schema.
    fireEvent.click(screen.getByLabelText('Dismiss save error'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByTestId('list')).toBeInTheDocument();
  });

  it('a later successful save clears a lingering failure banner', async () => {
    vi.mocked(saveRemoteSchema).mockRejectedValueOnce(new Error('network blip'));
    await openAndDirtyKit();
    fireEvent.click(screen.getByText('Save (Cmd+S)'));
    await screen.findByRole('alert');

    fireEvent.click(screen.getByText('Save (Cmd+S)')); // mock now resolves
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('the first-run guide shows once and its dismissal persists per browser', async () => {
    await passGate();
    // First visit: the 3-step overlay is up.
    const dialog = screen.getByRole('dialog', { name: 'Getting started guide' });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(screen.getByText('Got it'));
    expect(
      screen.queryByRole('dialog', { name: 'Getting started guide' }),
    ).not.toBeInTheDocument();
    expect(window.localStorage.getItem('schema-editor.guideSeen')).toBe('1');

    // A fresh mount in the same browser: no guide (the flag persisted).
    cleanup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByTestId('remote-catalogue')).toBeInTheDocument());
    expect(
      screen.queryByRole('dialog', { name: 'Getting started guide' }),
    ).not.toBeInTheDocument();
  });

  it('Escape closes the guide and persists the dismissal', async () => {
    await passGate();
    expect(
      screen.getByRole('dialog', { name: 'Getting started guide' }),
    ).toBeInTheDocument();
    // HostedGuide attaches its Escape keydown listener in a useEffect, which runs
    // AFTER the dialog is queryable in the DOM. A single fireEvent right after the
    // getByRole above can land before the effect registers the listener, so Escape
    // is dropped and the guide never closes (~1/3 flake in isolation, bd
    // polyglot-pdf-fgdo). Re-fire Escape inside waitFor so it retries until the
    // listener is attached AND the resulting setGuideOpen(false) re-render unmounts
    // the dialog. Idempotent: an extra Escape after the guide is gone is a no-op.
    await waitFor(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(
        screen.queryByRole('dialog', { name: 'Getting started guide' }),
      ).not.toBeInTheDocument();
    });
    // markGuideSeen() runs synchronously in the same handler, before onClose().
    expect(window.localStorage.getItem('schema-editor.guideSeen')).toBe('1');
  });

  it('Help reopens the dismissed guide', async () => {
    await passGate();
    fireEvent.click(screen.getByText('Got it'));
    fireEvent.click(screen.getByText('Help'));
    expect(
      screen.getByRole('dialog', { name: 'Getting started guide' }),
    ).toBeInTheDocument();
  });

  it('local (non-hosted) mode gets neither the guide nor the Help button', async () => {
    vi.mocked(isHostedMode).mockReturnValue(false);
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText(/Welcome to PDF Schema Editor/)).toBeInTheDocument());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText('Help')).not.toBeInTheDocument();
  });
});
