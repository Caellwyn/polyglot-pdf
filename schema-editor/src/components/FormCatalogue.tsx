import React from 'react';
import {
  isDirectoryAccessSupported, pickDirectory, isUserAbort,
  type FsDirectoryHandle,
} from '../utils/fileSystemAccess';
import {
  listKits, onboardPdf, readKitProgress, summarizeCatalogue, setKitLabel, setKitStatus,
  verifySameFolder, writeInstructionsPdf,
  type CatalogueEntry, type KitProgress, type KitStatus, type KitVersionInfo,
} from '../utils/formKitDirectory';
import {
  isExtractionAvailable, runExtraction, verifyExtractorFolder,
} from '../utils/extractionClient';

interface FormCatalogueProps {
  /** Called when the human opens a kit for editing. */
  onOpenKit: (entry: CatalogueEntry) => void;
  /**
   * Guard run BEFORE opening the folder picker: returns false to ABORT the switch
   * (e.g. the user declined to discard unsaved edits), in which case the picker is
   * not opened. Must NOT mutate state -- it may be called and then the picker
   * cancelled, leaving the open kit intact.
   */
  confirmFolderChange?: () => boolean;
  /**
   * Run AFTER the picker returns a new directory: drops the open-kit state so a
   * same-named kit in the new folder can't inherit the prior form's live progress.
   */
  clearOpenKit?: () => void;
  /**
   * The folder now in use (bd polyglot-pdf-s2bf). The host runs the same-folder
   * handshake against it: the backend resolves kit ids against its OWN root, so
   * the server-side actions must be disabled unless both sides agree on the
   * directory -- otherwise they rewrite a different copy than the one on screen.
   */
  onRootChange?: (dir: FsDirectoryHandle | null) => void;
  /** The currently-open kit id (to highlight it in the list). */
  selectedKitId: string | null;
  /**
   * Live in-editor review stats for the open kit, so its catalogue bar AND hover
   * detail track unsaved edits instead of the stale disk-scan value. Null when no
   * kit is open.
   */
  liveProgress?: {
    kitId: string; saved: boolean; percent: number; complete: number; total: number;
    // Live version summary so a metadata edit refreshes the card (Codex PR #263).
    // Optional: a caller that only tracks review % may omit it (card falls back
    // to the disk-scan version then).
    version?: KitVersionInfo;
  } | null;
}

const STATUS_STYLE: Record<string, string> = {
  complete: 'bg-green-100 text-green-700',
  draft: 'bg-yellow-100 text-yellow-700',
  unknown: 'bg-gray-100 text-gray-600',
};

/**
 * The editor's front door (bd polyglot-pdf-b0pe): pick a local form-kits/
 * directory, list every kit found, drag-drop an AcroForm PDF to onboard a new
 * one. Replaces the hardcoded form dropdown. Falls back to a clear message when
 * the browser lacks the File System Access directory API.
 */
export const FormCatalogue: React.FC<FormCatalogueProps> = ({
  onOpenKit, confirmFolderChange, clearOpenKit, selectedKitId, liveProgress,
  onRootChange,
}) => {
  const supported = React.useMemo(isDirectoryAccessSupported, []);
  const [root, setRoot] = React.useState<FsDirectoryHandle | null>(null);
  // Tell the host which folder is in use so it can run the same-folder
  // handshake (bd polyglot-pdf-s2bf). An effect rather than a call beside
  // setRoot, so it stays correct if a second path to change the root is ever
  // added (today the picker is the only one) and fires exactly once per change.
  React.useEffect(() => { onRootChange?.(root); }, [root, onRootChange]);
  const [kits, setKits] = React.useState<CatalogueEntry[]>([]);
  // bd tynm parity: the card grid is collapsed by default behind a compact
  // selector strip (a dropdown to switch forms + a "Show form cards" toggle), so
  // the header gives its vertical space to the editor. The full grid -- with its
  // per-card Rename / status / Run-extraction actions -- stays one click away.
  // The hosted RemoteCatalogue already worked this way; this brings the local
  // catalogue to the same footprint.
  const [expanded, setExpanded] = React.useState(false);
  // The strip's current selection. Distinct from selectedKitId so a schemaless
  // kit (no open semantics) can be picked in the dropdown without being "open".
  const [actionKitId, setActionKitId] = React.useState<string | null>(null);
  // When the parent confirms an open (selectedKitId advances), drop the local
  // optimistic strip selection so the dropdown tracks the actually-open kit.
  React.useEffect(() => { setActionKitId(null); }, [selectedKitId]);
  // Per-kit review progress, keyed by kit id (filled in after the list renders).
  const [progress, setProgress] = React.useState<Record<string, KitProgress>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [dragOver, setDragOver] = React.useState(false);
  // Whether the host-side extraction endpoint exists (only under `vite dev`).
  // Probed once on mount; gates the "Run extraction" button so a static build
  // (no endpoint) keeps the instructions-only flow with no broken button.
  const [extractionAvailable, setExtractionAvailable] = React.useState(false);
  // id of the kit currently extracting (one at a time), for the spinner/disable.
  const [extractingId, setExtractingId] = React.useState<string | null>(null);
  // Optional instructions PDF selected (but not yet uploaded) per schemaless kit,
  // keyed by kit id (bd s4dp.3). Cleared after a run. When set, handleRunExtraction
  // writes it into the kit dir and asks the extractor to enrich help from it.
  const [instructionsPdfByKit, setInstructionsPdfByKit] =
    React.useState<Record<string, File>>({});
  // Monotonic token: each refresh bumps it so a slow progress load from a prior
  // folder cannot overwrite the current folder's progress (stale-folder race).
  const refreshSeq = React.useRef(0);

  // `deliberate` = a user-initiated Refresh (disk truth supersedes remembered
  // saved edits). Automatic scans (folder open, post-onboard) must NOT clear the
  // cache: a stale initial scan completing after a save would otherwise wipe a
  // just-saved value and reintroduce the post-save revert (Codex PR #224 r7).
  const refresh = React.useCallback(async (dir: FsDirectoryHandle, deliberate = false) => {
    const seq = ++refreshSeq.current;
    setBusy(true);
    setError(null);
    try {
      const entries = await listKits(dir);
      if (seq !== refreshSeq.current) return; // superseded by a newer refresh
      setKits(entries);
      setProgress({}); // clear prior folder's bars while this folder's compute
      // Compute review progress per kit (loads each schema). Done after the list
      // is set so the catalogue renders immediately and the bars fill in; a kit
      // whose schema fails to load just shows no bar.
      const computed = await Promise.all(entries.map(readKitProgress));
      if (seq !== refreshSeq.current) return; // a newer refresh won; drop these
      const byId: Record<string, KitProgress> = {};
      for (const p of computed) byId[p.entry.id] = p;
      setProgress(byId);
      // Only a DELIBERATE Refresh treats the scan as superseding remembered saved
      // values (so an external/on-disk change can update a cached kit's bar --
      // Codex r6). An automatic scan must not clear the cache (Codex r7). The OPEN
      // kit keeps its live override (liveProgress), which is separate.
      if (deliberate) setEditedProgress({});
    } catch (err) {
      if (seq !== refreshSeq.current) return;
      setError(err instanceof Error ? err.message : 'Failed to read folder');
    } finally {
      if (seq === refreshSeq.current) setBusy(false);
    }
  }, []);

  const summary = React.useMemo(() => summarizeCatalogue(kits), [kits]);

  // Last live in-editor value seen per kit, kept SEPARATELY from the disk-scan
  // `progress` map so it survives after that kit stops being the live one AND is
  // immune to a folder-scan completing later and clobbering it (Codex PR #224).
  // The render overlays this on top of the scan. Editing kit A then opening B
  // would otherwise revert A's card to its stale scan % until a manual Refresh;
  // because liveProgress reflects in-memory edits, this also covers post-save.
  const [editedProgress, setEditedProgress] =
    React.useState<Record<string, { percent: number; complete: number; total: number; version?: KitVersionInfo }>>({});
  React.useEffect(() => {
    if (!liveProgress) return;
    const { kitId, saved, percent, complete, total, version } = liveProgress;
    // Only remember SAVED values. An unsaved edit still shows live on the open
    // card (the `live` override below), but caching it would leave phantom
    // progress after the user discards the edit and switches kits (Codex PR #224).
    if (!saved) return;
    setEditedProgress(prev => {
      const e = prev[kitId];
      if (e && e.percent === percent && e.complete === complete && e.total === total
          && e.version?.label === version?.label && e.version?.lowConfidence === version?.lowConfidence) return prev;
      return { ...prev, [kitId]: { percent, complete, total, version } };
    });
  }, [liveProgress]);

  const handlePickFolder = React.useCallback(async () => {
    // Refuse a folder switch while extraction is in flight: the running
    // extraction captured the current root and will refresh it on completion, so
    // switching now would have that stale refresh clobber the new folder (Codex r3).
    if (extractingId !== null) {
      setError('Extraction is running -- wait for it to finish before changing folders.');
      return;
    }
    // Guard unsaved edits BEFORE opening the picker (returns false to abort), but
    // do NOT mutate state yet: if the user then cancels the native picker, the
    // open kit must survive intact (Codex PR #224). Only after the picker returns
    // a directory do we clear the open-kit state -- which also prevents a
    // same-named kit in the new folder from inheriting the prior form's progress.
    if (confirmFolderChange && confirmFolderChange() === false) return;
    setNotice(null); // a prior "Added X" notice is stale once the folder changes
    try {
      const dir = await pickDirectory();
      clearOpenKit?.();
      setEditedProgress({}); // remembered edits belong to the old folder
      setExpanded(false); // a fresh folder returns to the collapsed default (bd tynm parity)
      setRoot(dir);
      await refresh(dir);
    } catch (err) {
      if (isUserAbort(err)) return; // picker cancelled -> open kit left intact
      setError(err instanceof Error ? err.message : 'Failed to open folder');
    }
  }, [refresh, confirmFolderChange, clearOpenKit, extractingId]);

  const handleDrop = React.useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setNotice(null); // any drop attempt supersedes a prior "Added X" notice
    if (extractingId !== null) {
      // A drop mid-extraction would run its own onboard/refresh against the same
      // folder the extraction captured -- and its finally must not be able to
      // clear the extraction guard (Codex r3). Refuse until extraction finishes.
      setError('Extraction is running -- wait for it to finish before adding a form.');
      return;
    }
    if (!root) {
      setError('Open a form-kits folder first, then drop a PDF to add a form.');
      return;
    }
    const pdf = Array.from(e.dataTransfer.files).find(
      f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
    if (!pdf) {
      setError('Drop an AcroForm PDF file to onboard a new form.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { id } = await onboardPdf(root, pdf);
      await refresh(root);
      // Do NOT auto-open: a freshly dropped PDF has no schema yet (extraction
      // runs separately), so opening it would error. Surface it as added; the
      // human opens it once it has a schema.
      setNotice(`Added "${id}" -- run the extraction to produce its schema, then open it here.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add form');
    } finally {
      setBusy(false);
    }
  }, [root, refresh, extractingId]);

  // Promote/demote a kit's metadata.json status (bd nr8u, D2). Only complete kits
  // reach GCS via the deploy gate, so this is the human's publish/unpublish toggle.
  const handleSetStatus = React.useCallback(async (kit: CatalogueEntry, status: KitStatus) => {
    if (!root) return;
    setNotice(null);
    setBusy(true);
    setError(null);
    try {
      await setKitStatus(kit, status);
      await refresh(root);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status');
    } finally {
      setBusy(false);
    }
  }, [root, refresh]);

  // Rename a kit's DISPLAY label (bd 15ic): a metadata.json-only write; the
  // kit's directory/id never changes.
  const [renamingId, setRenamingId] = React.useState<string | null>(null);
  const [renameText, setRenameText] = React.useState('');
  const handleRename = React.useCallback(async (kit: CatalogueEntry) => {
    if (!root) return;
    const label = renameText.trim();
    setRenamingId(null);
    if (!label || label === kit.label) return;  // no-op rename
    setNotice(null);
    setBusy(true);
    setError(null);
    try {
      await setKitLabel(kit, label);
      setNotice(`Renamed "${kit.label}" to "${label}".`);
      await refresh(root);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename the form');
    } finally {
      setBusy(false);
    }
  }, [root, renameText, refresh]);

  // Probe the host extraction endpoint once on mount (dev-only; absent in a
  // static build). Errors resolve false inside the client, so this never throws.
  React.useEffect(() => {
    let alive = true;
    void isExtractionAvailable().then((ok) => { if (alive) setExtractionAvailable(ok); });
    return () => { alive = false; };
  }, []);

  // Run the PDF->schema extractor for a schemaless kit (bd 7a9.17). On success
  // the kit gains a schema.json on disk; refresh so its card lights up openable.
  const handleRunExtraction = React.useCallback(async (kit: CatalogueEntry) => {
    if (!root || extractingId !== null) return;
    setNotice(null);
    setError(null);
    // `extractingId` (NOT the shared `busy`) is the extraction-in-flight guard:
    // folder-switch and drop both refuse while it is set, so the user cannot
    // switch folders mid-run and have this captured `root` refresh clobber the
    // new folder's state when the (minutes-long) extraction returns. It must be a
    // DEDICATED flag -- a concurrent drop's own `finally { setBusy(false) }` would
    // otherwise clear a shared `busy` and re-open the folder controls (Codex r3).
    // `root` is captured so the refresh below targets the SAME folder.
    setExtractingId(kit.id);
    const extractionRoot = root;
    try {
      // SAME-FOLDER GATE (bd polyglot-pdf-ball). The extractor resolves this kit
      // id against the VITE HOST's own FORM_KITS_ROOT and WRITES schema.json
      // there -- so if the picked folder is a copy elsewhere, "Run extraction"
      // silently overwrites a DIFFERENT kit while the catalogue refreshes the
      // picked one and shows no change. Prove the two are one directory first.
      //
      // This is its own channel, NOT the App-level serverActionsOk gate (bd
      // polyglot-pdf-s2bf): that one proves agreement with the FastAPI backend's
      // FORM_KITS_LOCAL_ROOT, a separate setting from the Vite host's root, so it
      // cannot vouch for where the extractor writes.
      //
      // Checked HERE rather than once per folder because it must hold at the
      // moment of the write: it is the last thing before any file is touched.
      // Tracks whether the host ANSWERED. The verdict is the same either way
      // (refuse -- fail closed), but a dead dev server needs different advice
      // than a wrong folder: telling that user to open a different folder or
      // edit FORM_KITS_ROOT sends them to change correct configuration.
      let hostAnswered = true;
      const folder = await verifySameFolder(
        extractionRoot, (nonce) => verifyExtractorFolder(nonce, () => { hostAnswered = false; }),
      );
      if (!folder.ok) {
        setError(
          !hostAnswered && folder.reason !== 'unwritable'
            ? `Cannot run extraction for "${kit.id}": the editor could not reach the `
              + 'extraction service to confirm which folder it uses. Check the dev server '
              + 'is still running, then try again.'
            : folder.reason === 'unwritable'
            // NOT the "make a copy elsewhere and open that" advice the s2bf modal
            // gives. That fits SAVING (which targets whatever folder you picked),
            // but extraction always writes under the HOST's FORM_KITS_ROOT -- so a
            // copy made anywhere else is by construction not the host root, and the
            // next click would just fail the mismatch branch instead. The only
            // route to a working state here is a writable host root.
            ? `Cannot run extraction for "${kit.id}": the folder you opened cannot be `
              + 'written to, so the editor cannot confirm it is the folder the extractor '
              + 'uses. Make this folder writable, or point the dev server at a writable '
              + 'form-kits folder (FORM_KITS_ROOT) and open that one.'
            : 'Cannot run extraction: the folder you opened is not the one the extractor '
              + `uses${folder.backendRoot ? ` (it uses ${folder.backendRoot})` : ''}, so it `
              + 'would rewrite a different copy of this form. Open that folder, or set '
              + 'FORM_KITS_ROOT to the folder you opened and restart the dev server.',
        );
        return;
      }
      // Optional instructions PDF (bd s4dp.3): write it into the kit dir first so
      // the host extractor can read it by filename, then pass that filename. None
      // selected -> /TU-only extraction (no error). Written only AFTER the gate
      // above -- on a mismatched folder it would land here while the endpoint
      // looked for it in the host's root, and 400 with "instructions PDF not
      // found" despite the browser having just written it.
      let instructionsPdfFile: string | undefined;
      const instructionsPdf = instructionsPdfByKit[kit.id];
      if (instructionsPdf) {
        instructionsPdfFile = await writeInstructionsPdf(kit.dirHandle, instructionsPdf);
      }
      const result = await runExtraction(kit.id, {
        pdfFile: kit.pdfFile, schemaFile: kit.schemaFile, instructionsPdfFile,
      });
      if (result.ok) {
        await refresh(extractionRoot);
        setNotice(`Extracted "${kit.id}" -- ${result.detail}. Open it to review.`);
        // Clear the consumed selection so a later re-run is /TU-only unless re-picked.
        setInstructionsPdfByKit((prev) => {
          const next = { ...prev };
          delete next[kit.id];
          return next;
        });
      } else {
        setError(`Extraction failed for "${kit.id}": ${result.detail}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed');
    } finally {
      setExtractingId(null);
    }
  }, [root, refresh, extractingId, instructionsPdfByKit]);

  if (!supported) {
    return (
      <div className="p-4 bg-white border-b border-gray-200 text-sm text-red-600">
        This browser does not support the File System Access directory API
        (needed to open a form-kits folder). Use Chrome or Edge.
      </div>
    );
  }

  return (
    <div
      data-testid="form-catalogue"
      className={`p-4 bg-white border-b border-gray-200 ${dragOver ? 'ring-2 ring-blue-400 bg-blue-50' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <div className="flex items-center gap-3 flex-wrap">
        <button className="btn btn-primary" onClick={handlePickFolder} disabled={busy || extractingId !== null}>
          {root ? 'Change folder' : 'Open form-kits folder'}
        </button>
        {root && (
          <button className="btn btn-secondary" onClick={() => void refresh(root, true)} disabled={busy || extractingId !== null}>
            Refresh
          </button>
        )}
        <span className="text-sm text-gray-500">
          {root
            ? `${kits.length} form${kits.length === 1 ? '' : 's'} in ${root.name}/ -- drop a PDF here to add one`
            : 'Open your form-kits/ folder to see the catalogue, or drop a PDF after opening it.'}
        </span>
      </div>

      {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
      {notice && <div className="mt-2 text-sm text-green-700">{notice}</div>}

      {/* Aggregate dashboard overview (bd vl3o, D3): complete vs in-progress at a glance. */}
      {root && kits.length > 0 && (
        <div
          data-testid="catalogue-summary"
          className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm"
        >
          <span className="font-medium text-gray-700">{summary.total} forms</span>
          <span className="text-green-700">{summary.complete} complete</span>
          <span className="text-yellow-700">{summary.inProgress} in progress</span>
          {summary.noSchema > 0 && (
            <span className="text-gray-500">{summary.noSchema} awaiting extraction</span>
          )}
        </div>
      )}

      {/* bd tynm parity: the compact selector strip -- the default, low-footprint
          way to switch forms. The full card grid stays available behind the
          toggle. Mirrors RemoteCatalogue's strip (dropdown + Show/Hide toggle). */}
      {root && kits.length > 0 && (
        <div className="mt-2 flex items-center gap-2 flex-wrap" data-testid="catalogue-strip">
          <select
            className="input text-sm max-w-xs"
            aria-label="Select a form"
            value={(actionKitId ?? selectedKitId) ?? ''}
            onChange={(e) => {
              const kit = kits.find((k) => k.id === e.target.value) ?? null;
              setActionKitId(kit?.id ?? null);
              // Opening needs a schema; a schemaless kit is still selectable so
              // the user can find it (its Run-extraction action lives on its card).
              if (kit?.hasSchema) onOpenKit(kit);
            }}
          >
            <option value="" disabled>
              Select a form...
            </option>
            {kits.map((k) => {
              // Same precedence as the card: live > cached-saved > disk scan.
              const pct = liveProgress && liveProgress.kitId === k.id
                ? liveProgress.percent
                : (editedProgress[k.id]?.percent ?? progress[k.id]?.reviewPercent ?? null);
              return (
                <option key={k.id} value={k.id}>
                  {k.label} -- {k.status}
                  {pct !== null ? `, ${pct}%` : ''}
                  {k.hasSchema ? '' : ' (no schema yet)'}
                </option>
              );
            })}
          </select>
          <button
            className="btn-sm btn-secondary text-xs ml-auto"
            onClick={() => setExpanded((v) => !v)}
            title={expanded
              ? 'Collapse the form cards back to the compact selector'
              : 'Show every form as a card (status, version, review progress, actions)'}
          >
            {expanded ? 'Hide form cards' : 'Show form cards'}
          </button>
        </div>
      )}

      {root && expanded && kits.length > 0 && (
        <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {kits.map((kit) => {
            const prog = progress[kit.id];
            // Precedence: the OPEN kit's live stats (tracks unsaved edits) > the
            // last remembered edited value for this kit > the disk-scan value.
            // Percent AND the complete/total hover counts come from one source so
            // they never disagree.
            const live = liveProgress && liveProgress.kitId === kit.id ? liveProgress : null;
            const edited = editedProgress[kit.id] ?? null;
            const source = live ?? edited;
            const pct = source ? source.percent : (prog?.reviewPercent ?? null);
            const completeFields = source ? source.complete : (prog?.completeFields ?? 0);
            const totalFields = source ? source.total : (prog?.totalFields ?? 0);
            // Present-but-unreadable schema: show a notice instead of nothing, so
            // a broken schema isn't mistaken for a pre-extraction kit. A live/edited
            // override always has measurable stats, so suppress it then.
            const showSchemaError = !source && prog?.schemaError && pct === null;
            // Version line: prefer the live/edited summary (tracks an in-session
            // metadata edit) over the stale disk-scan value (Codex PR #263).
            const cardVersion = source?.version ?? prog?.version ?? null;
            return (
            <li key={kit.id}>
              <button
                className={`w-full text-left p-3 rounded border ${
                  kit.id === selectedKitId
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                } ${kit.hasSchema ? '' : 'opacity-80'}`}
                onClick={() => onOpenKit(kit)}
                disabled={!kit.hasSchema}
                title={kit.hasSchema
                  ? `Open ${kit.label} for editing`
                  : `${kit.label} has no schema yet -- run the extraction first`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-gray-900 truncate">{kit.label}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${STATUS_STYLE[kit.status]}`}>
                    {kit.status}
                  </span>
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {kit.id} -- {kit.hasSchema ? 'schema' : 'no schema yet'}
                  {kit.hasPdf ? ', pdf' : ', no pdf'}
                </div>

                {/* Form version (bd polyglot-pdf-s4dp.2). Shown for any kit with a
                    readable schema. "Version: unknown" is explicit (not blank), and
                    a low-confidence / unknown version carries a "verify" hint. */}
                {cardVersion && (
                  <div className="mt-1 text-xs" data-testid="kit-version">
                    <span className="text-gray-500">Version: </span>
                    <span className={cardVersion.lowConfidence ? 'text-yellow-700' : 'text-gray-700'}>
                      {cardVersion.label}
                    </span>
                    {cardVersion.lowConfidence && (
                      <span className="text-yellow-600"> (verify)</span>
                    )}
                  </div>
                )}

                {/* Per-form review progress (% of fields complete). */}
                {pct !== null && (
                  <div className="mt-2" title={`${completeFields} of ${totalFields} fields complete`}>
                    <div className="flex items-center justify-between text-xs text-gray-500">
                      <span>Review</span>
                      <span>{pct}%</span>
                    </div>
                    <div className="mt-0.5 h-1.5 bg-gray-200 rounded overflow-hidden">
                      <div
                        className={`h-full ${pct === 100 ? 'bg-green-500' : 'bg-yellow-500'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Present-but-unreadable schema (distinct from no schema). */}
                {showSchemaError && (
                  <div className="mt-2 text-xs text-red-600">
                    Schema present but unreadable -- can't measure review progress.
                  </div>
                )}
              </button>

              {/* Status toggle (bd nr8u, D2): promote a reviewed draft to
                  complete (so it deploys) or revert a complete kit to draft.
                  Only for kits that have a schema -- a PDF-only kit can't be
                  complete (the deploy gate skips schema-less kits anyway). */}
              <div className="mt-1 flex items-center justify-end gap-2 px-1">
                {renamingId === kit.id ? (
                  <span className="flex items-center gap-1">
                    <input
                      className="input text-sm w-40"
                      aria-label="New form name"
                      value={renameText}
                      autoFocus
                      onChange={(e) => setRenameText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void handleRename(kit);
                        if (e.key === 'Escape') setRenamingId(null);
                      }}
                      disabled={busy}
                    />
                    <button
                      className="btn-sm btn-primary text-xs"
                      onClick={() => void handleRename(kit)}
                      disabled={busy || !renameText.trim()}
                    >
                      Save
                    </button>
                    <button
                      className="btn-sm btn-secondary text-xs"
                      onClick={() => setRenamingId(null)}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    className="btn-sm btn-secondary text-xs"
                    onClick={() => { setRenameText(kit.label); setRenamingId(kit.id); }}
                    disabled={busy}
                    title="Rename this form's display name (its folder and files stay unchanged)"
                  >
                    Rename
                  </button>
                )}
              </div>
              {kit.hasSchema && (
                <div className="mt-1 flex items-center justify-end gap-2 px-1">
                  {kit.status === 'complete' ? (
                    <button
                      className="btn-sm btn-secondary text-xs"
                      onClick={() => void handleSetStatus(kit, 'draft')}
                      disabled={busy}
                      title="Revert to draft (removes it from deploys)"
                    >
                      Revert to draft
                    </button>
                  ) : (
                    <button
                      className="btn-sm btn-primary text-xs"
                      onClick={() => void handleSetStatus(kit, 'complete')}
                      disabled={busy}
                      title="Mark complete (makes it eligible to deploy)"
                    >
                      Mark complete
                    </button>
                  )}
                </div>
              )}

              {/* Run-extraction (bd 7a9.17): a schemaless kit WITH a PDF can be
                  extracted in place when the host endpoint is available (vite
                  dev). Without the endpoint (static build), show the manual-step
                  hint instead of a button that can't work. */}
              {!kit.hasSchema && kit.hasPdf && (
                extractionAvailable ? (
                  <div className="mt-1 flex items-center justify-end gap-2 px-1">
                    {/* OPTIONAL instructions PDF (bd s4dp.3): when picked, its text
                        enriches help.instructions on top of the /TU baseline. */}
                    <label
                      className="text-xs text-gray-500 cursor-pointer hover:text-gray-700"
                      title="Optional: attach the form's official instructions PDF to enrich each field's help text"
                    >
                      <input
                        type="file"
                        accept="application/pdf,.pdf"
                        className="hidden"
                        disabled={busy || extractingId !== null}
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          // Validate it is actually a PDF before storing (Codex
                          // PR #274): the `accept` filter is advisory, so a user
                          // can still pick a .txt/.html; the client would then
                          // store it as the fixed "instructions.pdf", the
                          // endpoint's .pdf-name guard would pass, and
                          // _parse_instructions_pdf would silently yield no text --
                          // a success-reported run that ignored the selection.
                          const isPdf = (file: File) =>
                            file.type === 'application/pdf'
                            || file.name.toLowerCase().endsWith('.pdf');
                          if (f && !isPdf(f)) {
                            setError('The instructions file must be a PDF.');
                            // Drop any prior (valid) selection too, so the UI never
                            // shows the error alongside a kept "instructions: x.pdf"
                            // label that would still be threaded (Opus fallback PR #274).
                            setInstructionsPdfByKit((prev) => {
                              const next = { ...prev };
                              delete next[kit.id];
                              return next;
                            });
                            e.target.value = '';
                            return;
                          }
                          setError(null);
                          setInstructionsPdfByKit((prev) => {
                            const next = { ...prev };
                            if (f) next[kit.id] = f; else delete next[kit.id];
                            return next;
                          });
                          // Allow re-picking the same file later (onChange won't
                          // fire on an identical path otherwise).
                          e.target.value = '';
                        }}
                      />
                      {instructionsPdfByKit[kit.id]
                        ? `instructions: ${instructionsPdfByKit[kit.id].name}`
                        : '+ instructions PDF'}
                    </label>
                    <button
                      className="btn-sm btn-primary text-xs"
                      onClick={() => void handleRunExtraction(kit)}
                      disabled={busy || extractingId !== null}
                      title="Run the automated PDF -> schema extraction (uses a local model; can take a minute)"
                    >
                      {extractingId === kit.id ? 'Extracting...' : 'Run extraction'}
                    </button>
                  </div>
                ) : (
                  <div className="mt-1 px-1 text-right text-xs text-gray-400">
                    Run the extractor to produce its schema.
                  </div>
                )
              )}
            </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
