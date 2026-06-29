import React from 'react';
import {
  isDirectoryAccessSupported, pickDirectory, isUserAbort,
  type FsDirectoryHandle,
} from '../utils/fileSystemAccess';
import {
  listKits, onboardPdf, readKitProgress, summarizeCatalogue, setKitStatus,
  type CatalogueEntry, type KitProgress, type KitStatus, type KitVersionInfo,
} from '../utils/formKitDirectory';
import { isExtractionAvailable, runExtraction } from '../utils/extractionClient';

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
}) => {
  const supported = React.useMemo(isDirectoryAccessSupported, []);
  const [root, setRoot] = React.useState<FsDirectoryHandle | null>(null);
  const [kits, setKits] = React.useState<CatalogueEntry[]>([]);
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
      const result = await runExtraction(kit.id, {
        pdfFile: kit.pdfFile, schemaFile: kit.schemaFile,
      });
      if (result.ok) {
        await refresh(extractionRoot);
        setNotice(`Extracted "${kit.id}" -- ${result.detail}. Open it to review.`);
      } else {
        setError(`Extraction failed for "${kit.id}": ${result.detail}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed');
    } finally {
      setExtractingId(null);
    }
  }, [root, refresh, extractingId]);

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

      {root && kits.length > 0 && (
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
                  <div className="mt-1 flex items-center justify-end px-1">
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
