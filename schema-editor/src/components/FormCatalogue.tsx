import React from 'react';
import {
  isDirectoryAccessSupported, pickDirectory, isUserAbort,
  type FsDirectoryHandle,
} from '../utils/fileSystemAccess';
import {
  listKits, onboardPdf, readKitProgress, summarizeCatalogue,
  type CatalogueEntry, type KitProgress,
} from '../utils/formKitDirectory';

interface FormCatalogueProps {
  /** Called when the human opens a kit for editing. */
  onOpenKit: (entry: CatalogueEntry) => void;
  /**
   * Called when the user is about to switch to a different form-kits folder.
   * Returns false to ABORT the switch (e.g. the user declined to discard unsaved
   * edits), in which case the folder picker is not opened.
   */
  onFolderChange?: () => boolean;
  /** The currently-open kit id (to highlight it in the list). */
  selectedKitId: string | null;
  /**
   * Live in-editor review stats for the open kit, so its catalogue bar AND hover
   * detail track unsaved edits instead of the stale disk-scan value. Null when no
   * kit is open.
   */
  liveProgress?: { kitId: string; percent: number; complete: number; total: number } | null;
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
  onOpenKit, onFolderChange, selectedKitId, liveProgress,
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
  // Monotonic token: each refresh bumps it so a slow progress load from a prior
  // folder cannot overwrite the current folder's progress (stale-folder race).
  const refreshSeq = React.useRef(0);

  const refresh = React.useCallback(async (dir: FsDirectoryHandle) => {
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
    } catch (err) {
      if (seq !== refreshSeq.current) return;
      setError(err instanceof Error ? err.message : 'Failed to read folder');
    } finally {
      if (seq === refreshSeq.current) setBusy(false);
    }
  }, []);

  const summary = React.useMemo(() => summarizeCatalogue(kits), [kits]);

  const handlePickFolder = React.useCallback(async () => {
    // Confirm/clear the open-kit state BEFORE opening the picker: this both
    // guards unsaved edits (returns false to abort) and prevents a same-named kit
    // in the new folder from inheriting the previous form's live progress
    // (Codex PR #224). Only the first folder-open (no prior state) skips it.
    if (onFolderChange && onFolderChange() === false) return;
    setNotice(null); // a prior "Added X" notice is stale once the folder changes
    try {
      const dir = await pickDirectory();
      setRoot(dir);
      await refresh(dir);
    } catch (err) {
      if (isUserAbort(err)) return;
      setError(err instanceof Error ? err.message : 'Failed to open folder');
    }
  }, [refresh, onFolderChange]);

  const handleDrop = React.useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setNotice(null); // any drop attempt supersedes a prior "Added X" notice
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
  }, [root, refresh]);

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
        <button className="btn btn-primary" onClick={handlePickFolder} disabled={busy}>
          {root ? 'Change folder' : 'Open form-kits folder'}
        </button>
        {root && (
          <button className="btn btn-secondary" onClick={() => void refresh(root)} disabled={busy}>
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
            // The open kit shows its LIVE in-editor stats (tracks unsaved edits);
            // others show the disk-scanned value. Percent AND the complete/total
            // hover counts come from the same source so they never disagree.
            const live = liveProgress && liveProgress.kitId === kit.id ? liveProgress : null;
            const pct = live ? live.percent : (prog?.reviewPercent ?? null);
            const completeFields = live ? live.complete : (prog?.completeFields ?? 0);
            const totalFields = live ? live.total : (prog?.totalFields ?? 0);
            // Present-but-unreadable schema: show a notice instead of nothing, so
            // a broken schema isn't mistaken for a pre-extraction kit. A live
            // override (open kit) always has measurable stats, so suppress it then.
            const showSchemaError = !live && prog?.schemaError && pct === null;
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
            </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
