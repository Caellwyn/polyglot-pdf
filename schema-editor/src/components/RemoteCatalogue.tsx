import React from 'react';
import {
  AuthError, listRemoteKits, loadRemoteSchema, setRemoteStatus,
  type EditorRole, type RemoteKitEntry,
} from '../utils/remoteKitStore';
import { getCompletionStats } from '../utils/validation';
import { versionInfoFromSchema, type KitVersionInfo } from '../utils/formKitDirectory';

interface RemoteCatalogueProps {
  /** Called when the human opens a kit for editing. */
  onOpenKit: (entry: RemoteKitEntry) => void;
  /** The currently-open kit id (to highlight it in the list). */
  selectedKitId: string | null;
  /** The caller's access tier (author-only controls arrive with bd 92qe.3). */
  role: EditorRole;
  /** A call answered 401 (rotated/revoked code): the app drops to the gate. */
  onAuthError?: () => void;
  /**
   * Live in-editor review stats for the open kit (same contract as
   * FormCatalogue's liveProgress), so the open card tracks unsaved edits.
   */
  liveProgress?: {
    kitId: string; saved: boolean; percent: number; complete: number; total: number;
    version?: KitVersionInfo;
  } | null;
}

interface RemoteKitProgress {
  reviewPercent: number | null;
  completeFields: number;
  totalFields: number;
  schemaError: boolean;
  version: KitVersionInfo | null;
}

const STATUS_STYLE: Record<string, string> = {
  complete: 'bg-green-100 text-green-700',
  draft: 'bg-yellow-100 text-yellow-700',
  unknown: 'bg-gray-100 text-gray-600',
};

/**
 * The hosted editor's front door (bd polyglot-pdf-92qe.2): the same catalogue
 * card UI as the local FormCatalogue, but listing kits from the backend's
 * token-gated /api/editor routes (the shared store) instead of a picked local
 * directory. Drafts are included -- that IS the contractor's work list.
 *
 * Deliberately a SIBLING of FormCatalogue rather than a mode inside it:
 * FormCatalogue is tightly bound to the File System Access directory API
 * (folder picker, drag-drop onboarding, host extraction), none of which exist
 * in hosted mode in this bead (author-tier onboarding/extraction is bd 92qe.3).
 */
export const RemoteCatalogue: React.FC<RemoteCatalogueProps> = ({
  onOpenKit, selectedKitId, role, onAuthError, liveProgress,
}) => {
  const [kits, setKits] = React.useState<RemoteKitEntry[]>([]);
  const [progress, setProgress] = React.useState<Record<string, RemoteKitProgress>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  // Monotonic token: a slow progress load from a superseded refresh must not
  // clobber the current one (same stale-scan discipline as FormCatalogue).
  const refreshSeq = React.useRef(0);

  // Last SAVED in-editor stats per kit (the FormCatalogue editedProgress
  // pattern -- Codex P1, PR #280): liveProgress only covers the kit that is
  // open RIGHT NOW, so after saving kit A and opening kit B, A's card would
  // revert to the mount-time scan until a manual Refresh. Remembering saved
  // values keeps the shared catalogue honest between refreshes; unsaved edits
  // still show live on the open card but are never remembered (a discarded
  // edit must not leave phantom progress). A Refresh (fresh server scan)
  // supersedes the cache.
  const [editedProgress, setEditedProgress] = React.useState<
    Record<string, { percent: number; complete: number; total: number; version?: KitVersionInfo }>
  >({});
  React.useEffect(() => {
    if (!liveProgress || !liveProgress.saved) return;
    const { kitId, percent, complete, total, version } = liveProgress;
    setEditedProgress((prev) => {
      const e = prev[kitId];
      if (e && e.percent === percent && e.complete === complete && e.total === total
          && e.version?.label === version?.label
          && e.version?.lowConfidence === version?.lowConfidence) return prev;
      return { ...prev, [kitId]: { percent, complete, total, version } };
    });
  }, [liveProgress]);

  // `deliberate` = a user-clicked Refresh: only THAT treats the fresh scan as
  // superseding remembered saved values. An automatic scan (mount, post-status,
  // post-onboard) must NOT clear the cache -- a scan that STARTED before a save
  // landed would otherwise wipe the just-saved value and revert the card (the
  // exact FormCatalogue lesson, Codex PR #224 r7).
  const refresh = React.useCallback(async (deliberate = false) => {
    const seq = ++refreshSeq.current;
    setBusy(true);
    setError(null);
    try {
      const entries = await listRemoteKits();
      if (seq !== refreshSeq.current) return;
      setKits(entries);
      setProgress({});
      // Review % per kit: load each schema and reuse getCompletionStats -- the
      // SAME definition the editor + local catalogue use, so the numbers can
      // never disagree. Client-side on purpose: a server-side re-implementation
      // of checkFieldComplete would drift. Fine at current catalogue scale.
      const withSchema = entries.filter((e) => e.hasSchema);
      // A 401 during this scan (code revoked between the list call and the
      // per-kit fetches) is an AUTH state, not a broken schema -- it must
      // route to onAuthError, never paint every card with a misleading
      // "schema unreadable" error (fresh-eyes gap 1). Flag-and-resolve rather
      // than rethrow: with several kits, more than one fetch can reject, and
      // a rethrow through Promise.all would leave the siblings' rejections
      // unhandled.
      let authFailed = false;
      const computed = await Promise.all(withSchema.map(async (e) => {
        try {
          const schema = await loadRemoteSchema(e.id);
          if (!schema || !Array.isArray(schema.fields)) {
            return [e.id, { reviewPercent: null, completeFields: 0, totalFields: 0, schemaError: true, version: null }] as const;
          }
          const stats = getCompletionStats(schema);
          return [e.id, {
            reviewPercent: stats.percentage,
            completeFields: stats.complete,
            totalFields: stats.total,
            schemaError: false,
            version: versionInfoFromSchema(schema),
          }] as const;
        } catch (err) {
          if (err instanceof AuthError) authFailed = true;
          return [e.id, { reviewPercent: null, completeFields: 0, totalFields: 0, schemaError: true, version: null }] as const;
        }
      }));
      if (seq !== refreshSeq.current) return;
      if (authFailed) {
        onAuthError?.();
        return;
      }
      setProgress(Object.fromEntries(computed));
      if (deliberate) setEditedProgress({});
    } catch (err) {
      if (seq !== refreshSeq.current) return;
      if (err instanceof AuthError) {
        onAuthError?.();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to load the kit list');
    } finally {
      if (seq === refreshSeq.current) setBusy(false);
    }
  }, [onAuthError]);

  React.useEffect(() => { void refresh(); }, [refresh]);

  // Promote/demote a kit in the SHARED store. Promotion can be refused by the
  // server's publish gate (schema must validate) -- surface that detail.
  const handleSetStatus = React.useCallback(async (
    kit: RemoteKitEntry, status: 'draft' | 'complete',
  ) => {
    setNotice(null);
    setBusy(true);
    setError(null);
    try {
      await setRemoteStatus(kit.id, status);
      setNotice(status === 'complete'
        ? `"${kit.label}" marked complete -- it ships with the maintainer's next deploy.`
        : `"${kit.label}" reverted to draft.`);
      await refresh();
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError?.();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to update status');
      setBusy(false);
    }
  }, [refresh, onAuthError]);

  const summary = React.useMemo(() => {
    let complete = 0, inProgress = 0, noSchema = 0;
    for (const k of kits) {
      if (!k.hasSchema) noSchema++;
      else if (k.status === 'complete') complete++;
      else inProgress++;
    }
    return { total: kits.length, complete, inProgress, noSchema };
  }, [kits]);

  return (
    <div data-testid="remote-catalogue" className="p-4 bg-white border-b border-gray-200">
      <div className="flex items-center gap-3 flex-wrap">
        <button className="btn btn-secondary" onClick={() => void refresh(true)} disabled={busy}>
          Refresh
        </button>
        <span className="text-sm text-gray-500">
          {busy && kits.length === 0
            ? 'Loading the shared form catalogue...'
            : `${kits.length} form${kits.length === 1 ? '' : 's'} in the shared workspace`}
        </span>
        <span className="ml-auto text-xs text-gray-400" title="Your access tier">
          access: {role}
        </span>
      </div>

      {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
      {notice && <div className="mt-2 text-sm text-green-700">{notice}</div>}

      {kits.length > 0 && (
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

      {kits.length > 0 && (
        <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {kits.map((kit) => {
            const prog = progress[kit.id];
            // Precedence: the OPEN kit's live stats (tracks unsaved edits) >
            // the last remembered SAVED value for this kit > the scan.
            const live = liveProgress && liveProgress.kitId === kit.id ? liveProgress : null;
            const edited = editedProgress[kit.id] ?? null;
            const source = live ?? edited;
            const pct = source ? source.percent : (prog?.reviewPercent ?? null);
            const completeFields = source ? source.complete : (prog?.completeFields ?? 0);
            const totalFields = source ? source.total : (prog?.totalFields ?? 0);
            const showSchemaError = !source && prog?.schemaError && pct === null;
            const cardVersion = source?.version ?? prog?.version ?? null;
            // The open kit has UNSAVED edits: promoting now would publish the
            // stale persisted schema (and the follow-up save would then be
            // refused by the published-kit guard) -- block until saved
            // (Codex P1, PR #280).
            const openDirty = live !== null && !live.saved;
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
                    : `${kit.label} has no schema yet`}
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

                  {showSchemaError && (
                    <div className="mt-2 text-xs text-red-600">
                      Schema present but unreadable -- can't measure review progress.
                    </div>
                  )}
                </button>

                {kit.hasSchema && (
                  <div className="mt-1 flex items-center justify-end gap-2 px-1">
                    {kit.status === 'complete' ? (
                      <button
                        className="btn-sm btn-secondary text-xs"
                        onClick={() => void handleSetStatus(kit, 'draft')}
                        disabled={busy}
                        title="Revert to draft (removes it from the next deploy)"
                      >
                        Revert to draft
                      </button>
                    ) : (
                      <button
                        className="btn-sm btn-primary text-xs"
                        onClick={() => void handleSetStatus(kit, 'complete')}
                        disabled={busy || openDirty}
                        title={openDirty
                          ? 'Save your changes first (Cmd+S) -- completing now '
                            + 'would publish the last saved version, not your edits'
                          : "Mark complete (ships with the maintainer's next deploy)"}
                      >
                        Mark complete
                      </button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {!busy && !error && kits.length === 0 && (
        <div className="mt-3 text-sm text-gray-500">
          The shared workspace is empty -- no forms have been uploaded yet.
        </div>
      )}
    </div>
  );
};
