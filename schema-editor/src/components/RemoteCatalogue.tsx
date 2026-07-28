import React from 'react';
import {
  AuthError, extractRemoteKit, listRemoteKits, loadRemoteSchema,
  onboardRemoteKit, setRemoteLabel, setRemoteStatus, translateRemoteKitOptions,
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
  /**
   * Start with the full card grid visible (bd tynm). Default FALSE: the
   * catalogue renders as a compact selector strip and the cards live behind a
   * "Show form cards" toggle, so the header gives its space to the editor.
   */
  defaultExpanded?: boolean;
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
  defaultExpanded = false,
}) => {
  const [kits, setKits] = React.useState<RemoteKitEntry[]>([]);
  // bd tynm: the card grid is collapsed by default behind a compact selector
  // strip; `actionKitId` is the strip's selection (a schemaless kit can be
  // selected for its actions -- e.g. Run extraction -- without being opened).
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const [actionKitId, setActionKitId] = React.useState<string | null>(null);
  // When the parent CONFIRMS an open (selectedKitId changes -- via the dropdown,
  // a card, or any other route), drop the local optimistic selection so the
  // strip tracks the kit that is actually open.
  React.useEffect(() => { setActionKitId(null); }, [selectedKitId]);
  const [progress, setProgress] = React.useState<Record<string, RemoteKitProgress>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  // Monotonic token: a slow progress load from a superseded refresh must not
  // clobber the current one (same stale-scan discipline as FormCatalogue).
  const refreshSeq = React.useRef(0);
  // Author tier (bd 92qe.3): id of the kit currently extracting (ONE at a
  // time -- the server also serializes), elapsed seconds for progress, and the
  // per-kit optional instructions PDF picked but not yet sent.
  const [extractingId, setExtractingId] = React.useState<string | null>(null);
  const [extractElapsed, setExtractElapsed] = React.useState(0);
  const [instructionsPdfByKit, setInstructionsPdfByKit] =
    React.useState<Record<string, File>>({});
  // bd 2h9j: extraction also bakes translated option labels by default; the
  // checkbox opts OUT for cheap extraction-strategy test runs. The standalone
  // Translate-options action covers already-extracted kits (one at a time).
  const [translateOptionsChecked, setTranslateOptionsChecked] = React.useState(true);
  const [enrichGuidanceChecked, setEnrichGuidanceChecked] = React.useState(true);
  const [translatingId, setTranslatingId] = React.useState<string | null>(null);
  // Mark-complete drift sweep (bd polyglot-pdf-783r): the id of the kit whose
  // completion is running its server-side re-translation + validation, plus an
  // elapsed-seconds ticker. The sweep makes one pro-tier call per language with
  // retry, so a complete flip can take tens of seconds -- the button shows the
  // ticker (same pattern as extraction) so it does not read as a hang.
  const [completingId, setCompletingId] = React.useState<string | null>(null);
  const [completeElapsed, setCompleteElapsed] = React.useState(0);
  const uploadInputRef = React.useRef<HTMLInputElement | null>(null);
  const isAuthor = role === 'author';

  // Elapsed-seconds ticker while an extraction runs (it takes minutes; a dead
  // button with no feedback reads as a hang).
  React.useEffect(() => {
    if (extractingId === null) return;
    setExtractElapsed(0);
    const t = window.setInterval(() => setExtractElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [extractingId]);

  // Elapsed-seconds ticker while a Mark-complete sweep runs (bd 783r), same
  // rationale as the extraction ticker.
  React.useEffect(() => {
    if (completingId === null) return;
    setCompleteElapsed(0);
    const t = window.setInterval(() => setCompleteElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [completingId]);

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
          // Same shape guard as the local readKitProgress (Codex P1 r2,
          // PR #280): fields must be an array OF OBJECTS -- a corrupted draft
          // whose entries are strings/arrays would otherwise "measure" as a
          // bogus 0% card instead of surfacing as unreadable.
          const fieldsOk = schema && Array.isArray(schema.fields)
            && schema.fields.every(
              (f) => f !== null && typeof f === 'object' && !Array.isArray(f));
          if (!schema || !fieldsOk) {
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
  // server's publish gate (schema must validate) -- surface that detail. A
  // complete flip ALSO runs the server-side translation drift sweep (bd
  // polyglot-pdf-783r): re-translating spoken names / option labels whose
  // English drifted during review, then refusing completion until every
  // language is covered. The sweep is slow (a pro-tier call per language with
  // retry), so a complete flip shows the elapsed ticker via completingId, and a
  // 409 "N of M translations complete" refusal surfaces as the error to re-press.
  const handleSetStatus = React.useCallback(async (
    kit: RemoteKitEntry, status: 'draft' | 'complete',
  ) => {
    setNotice(null);
    setBusy(true);
    setError(null);
    if (status === 'complete') setCompletingId(kit.id);
    try {
      const result = await setRemoteStatus(kit.id, status);
      if (status === 'complete') {
        // result.retranslated counts translation ENTRIES baked (one per
        // location x language), not distinct drifted strings -- a label shared
        // by several options across N languages contributes many entries. Word
        // it as "entries refreshed" so the number is not mistaken for a
        // drifted-item count (Opus outer-review nit, bd 783r).
        const drift = result.retranslated > 0
          ? ` Refreshed ${result.retranslated} translation ` +
            `entr${result.retranslated === 1 ? 'y' : 'ies'} first.`
          : '';
        setNotice(
          `"${kit.label}" marked complete -- it ships with the maintainer's ` +
          `next deploy.${drift}`,
        );
      } else {
        setNotice(`"${kit.label}" reverted to draft.`);
      }
      await refresh();
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError?.();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to update status');
      setBusy(false);
    } finally {
      setCompletingId(null);
    }
  }, [refresh, onAuthError]);

  // Rename a kit's DISPLAY label (bd 15ic): metadata-only, so it is safe for
  // ANY selected kit (no open involved -- unlike the status actions, which
  // need the parent-confirmed open). renamingId gates the inline input.
  const [renamingId, setRenamingId] = React.useState<string | null>(null);
  const [renameText, setRenameText] = React.useState('');
  const handleRename = React.useCallback(async (kit: RemoteKitEntry) => {
    const label = renameText.trim();
    setRenamingId(null);
    if (!label || label === kit.label) return;  // no-op rename
    setNotice(null);
    setBusy(true);
    setError(null);
    try {
      await setRemoteLabel(kit.id, label);
      setNotice(`Renamed "${kit.label}" to "${label}".`);
      await refresh();
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError?.();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to rename the form');
      setBusy(false);
    }
  }, [renameText, refresh, onAuthError]);

  // Author tier (bd 92qe.3): upload a blank form PDF -> a new draft kit in the
  // shared store (the hosted counterpart of the local drag-drop onboarding).
  const handleUploadPdf = React.useCallback(async (file: File) => {
    setNotice(null);
    setError(null);
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setError('Pick an AcroForm PDF file to add a form.');
      return;
    }
    setBusy(true);
    try {
      const created = await onboardRemoteKit(file);
      await refresh();
      setNotice(`Added "${created.id}" -- run the extraction to produce its schema, then open it here.`);
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError?.();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to add form');
      setBusy(false);
    }
  }, [refresh, onAuthError]);

  // Author tier (bd 92qe.3): run the server-side PDF -> schema extraction for
  // a schemaless kit. Minutes-long synchronous call; the ticker shows elapsed.
  const handleRunExtraction = React.useCallback(async (kit: RemoteKitEntry) => {
    if (extractingId !== null) return;
    setNotice(null);
    setError(null);
    setExtractingId(kit.id);
    try {
      const instructionsPdf = instructionsPdfByKit[kit.id];
      const result = await extractRemoteKit(kit.id, {
        instructionsPdf, translateOptions: translateOptionsChecked,
        enrichGuidance: enrichGuidanceChecked,
      });
      await refresh();
      // Store-with-issues (bd v96b): a stored-but-imperfect draft surfaces its
      // lint counts here so the author knows to open + repair it, rather than
      // the old all-or-nothing "success"/error split.
      if (result.storedWithIssues) {
        const errs = result.errorCount ?? 0;
        const warns = result.warningCount ?? 0;
        const parts = [
          errs ? `${errs} error${errs === 1 ? '' : 's'}` : '',
          warns ? `${warns} warning${warns === 1 ? '' : 's'}` : '',
        ].filter(Boolean).join(', ');
        setNotice(
          `Extracted "${kit.id}" with issues (${parts || 'needs review'}). ` +
          `Open it to review and repair before marking complete.`,
        );
      } else {
        setNotice(`Extracted "${kit.id}" -- ${result.detail}. Open it to review.`);
      }
      setInstructionsPdfByKit((prev) => {
        const next = { ...prev };
        delete next[kit.id];
        return next;
      });
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError?.();
        return;
      }
      setError(err instanceof Error ? err.message : 'Extraction failed');
    } finally {
      setExtractingId(null);
    }
  }, [refresh, onAuthError, extractingId, instructionsPdfByKit,
      translateOptionsChecked, enrichGuidanceChecked]);

  // bd 2h9j: bake translated option labels into an ALREADY-extracted kit's
  // stored schema, standalone (the decoupled counterpart of the extraction
  // checkbox). Idempotent server-side; on success the open kit is re-opened so
  // the editor shows the stored (translated) schema. Gated on saved state by
  // the callers (like Mark complete) -- the bake rewrites the stored schema.
  const handleTranslateOptions = React.useCallback(async (kit: RemoteKitEntry) => {
    if (translatingId !== null) return;
    setNotice(null);
    setError(null);
    setTranslatingId(kit.id);
    try {
      const report = await translateRemoteKitOptions(kit.id);
      const updated = Object.values(report.languages)
        .reduce((n, e) => n + e.options_updated, 0);
      const failed = report.failedLanguages;
      // Verify/rectify gate flags (bd 9djc): persisted server-side, so after
      // the reload below the ValidationPanel lists them -- the notice just
      // points the author there.
      const flagCount = report.flags?.length ?? 0;
      const flagNote = flagCount
        ? `; ${flagCount} translation flag${flagCount === 1 ? '' : 's'} to ` +
          'review (open the kit -- the validation panel lists them)'
        : '';
      if (!report.changed && flagCount === 0) {
        setNotice(`"${kit.id}" option labels are already fully translated.`);
      } else if (!report.changed) {
        // No label changed, but the verify gate still flagged translations
        // (reachable on a force re-bake that reproduces identical values):
        // the backend persisted the flags into provenance, so point at the
        // panel and reload the stored schema like any other change.
        setNotice(
          `"${kit.id}" option labels are already fully translated` +
          flagNote + '.',
        );
        if (kit.id === selectedKitId) onOpenKit(kit);
      } else {
        setNotice(
          `Translated option labels for "${kit.id}" -- ${updated} ` +
          `option-language entr${updated === 1 ? 'y' : 'ies'} baked` +
          (failed.length
            ? `; FAILED: ${failed.join(', ')} (run again to fill the gap)`
            : '') + flagNote + '.',
        );
        // Reload the stored schema when this kit is open (safe: the button is
        // disabled while the open kit has unsaved edits).
        if (kit.id === selectedKitId) onOpenKit(kit);
      }
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError?.();
        return;
      }
      setError(err instanceof Error ? err.message : 'Option translation failed');
    } finally {
      setTranslatingId(null);
    }
  }, [translatingId, selectedKitId, onOpenKit, onAuthError]);

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
    <div data-testid="remote-catalogue" className="px-4 py-2 bg-white border-b border-gray-200">
      <div className="flex items-center gap-3 flex-wrap">
        <button className="btn btn-secondary" onClick={() => void refresh(true)} disabled={busy || extractingId !== null}>
          Refresh
        </button>
        {/* Author tier: onboard a new form by uploading its blank PDF. */}
        {isAuthor && (
          <>
            <input
              ref={uploadInputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              data-testid="upload-pdf-input"
              disabled={busy || extractingId !== null}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleUploadPdf(f);
                e.target.value = '';
              }}
            />
            <button
              className="btn btn-primary"
              onClick={() => uploadInputRef.current?.click()}
              disabled={busy || extractingId !== null}
              title="Upload a blank AcroForm PDF to add a new form to the shared workspace"
            >
              Add a form (PDF)
            </button>
          </>
        )}
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

      {/* bd tynm: the compact selector strip -- the default, low-footprint way
          to switch forms. The full card grid stays available behind the toggle. */}
      {kits.length > 0 && (
        <div className="mt-2 flex items-center gap-2 flex-wrap" data-testid="catalogue-strip">
          <select
            className="input text-sm max-w-xs"
            aria-label="Select a form"
            value={(actionKitId ?? selectedKitId) ?? ''}
            onChange={(e) => {
              const kit = kits.find((k) => k.id === e.target.value) ?? null;
              setActionKitId(kit?.id ?? null);
              // Opening needs a schema; a schemaless kit is still selectable so
              // its actions (Run extraction) are reachable from the strip.
              if (kit?.hasSchema) onOpenKit(kit);
            }}
          >
            <option value="" disabled>
              Select a form...
            </option>
            {kits.map((k) => {
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
          {(() => {
            // Rename (bd 15ic): metadata-only, safe for ANY selected kit --
            // no open involved, so it is deliberately NOT gated on the
            // parent-confirmed open (unlike the status actions below).
            const kit = kits.find((k) => k.id === (actionKitId ?? selectedKitId)) ?? null;
            if (!kit) return null;
            if (renamingId === kit.id) {
              return (
                <span className="flex items-center gap-1">
                  <input
                    className="input text-sm w-44"
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
              );
            }
            return (
              <button
                className="btn-sm btn-secondary text-xs"
                onClick={() => { setRenameText(kit.label); setRenamingId(kit.id); }}
                disabled={busy}
                title="Rename this form's display name (its id and files stay unchanged)"
              >
                Rename
              </button>
            );
          })()}
          {(() => {
            const kit = kits.find((k) => k.id === (actionKitId ?? selectedKitId)) ?? null;
            if (!kit) return null;
            // The open is ASYNC and can fail: `actionKitId` is set on selection
            // (optimistically), but selectedKitId only advances when the parent
            // CONFIRMS the open. Status-changing actions (Mark complete/Revert)
            // must never render for a schema-bearing kit that is not actually
            // open -- else a failed open would leave the strip offering to
            // complete a kit the user never reviewed (fresh-eyes, bd tynm). A
            // SCHEMALESS kit has no open semantics, so its actions (Run
            // extraction) are always safe to show.
            if (kit.hasSchema && kit.id !== selectedKitId) return null;
            const stripDirty = liveProgress !== null && liveProgress !== undefined
              && liveProgress.kitId === kit.id && !liveProgress.saved;
            return (
              <>
                <span className={`text-xs px-2 py-0.5 rounded ${STATUS_STYLE[kit.status]}`}>
                  {kit.status}
                </span>
                {kit.hasSchema && (kit.status === 'complete' ? (
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
                    disabled={busy || stripDirty || completingId !== null}
                    title={stripDirty
                      ? 'Save your changes first (Cmd+S) -- completing now '
                        + 'would publish the last saved version, not your edits'
                      : "Mark complete (re-translates any drifted names/options, "
                        + "then ships with the maintainer's next deploy)"}
                  >
                    {completingId === kit.id
                      ? `Re-translating & validating... ${completeElapsed}s`
                      : 'Mark complete'}
                  </button>
                ))}
                {isAuthor && kit.hasSchema && kit.status !== 'complete' && (
                  <button
                    className="btn-sm btn-secondary text-xs"
                    onClick={() => void handleTranslateOptions(kit)}
                    disabled={busy || extractingId !== null
                      || translatingId !== null || stripDirty}
                    title={stripDirty
                      ? 'Save your changes first (Cmd+S) -- translation '
                        + 'rewrites the stored schema'
                      : 'Bake translated option labels (all supported spoken '
                        + 'languages) into this form on the server'}
                  >
                    {translatingId === kit.id
                      ? 'Translating...'
                      : 'Translate options'}
                  </button>
                )}
                {isAuthor && !kit.hasSchema && kit.hasPdf && (
                  <button
                    className="btn-sm btn-primary text-xs"
                    onClick={() => void handleRunExtraction(kit)}
                    disabled={busy || extractingId !== null}
                    title="Run the automated PDF -> schema extraction on the server (takes a few minutes)"
                  >
                    {extractingId === kit.id
                      ? `Extracting... ${extractElapsed}s`
                      : 'Run extraction'}
                  </button>
                )}
              </>
            );
          })()}
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

      {expanded && kits.length > 0 && (
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
                        disabled={busy || openDirty || completingId !== null}
                        title={openDirty
                          ? 'Save your changes first (Cmd+S) -- completing now '
                            + 'would publish the last saved version, not your edits'
                          : "Mark complete (re-translates any drifted names/options, "
                            + "then ships with the maintainer's next deploy)"}
                      >
                        {completingId === kit.id
                          ? `Re-translating & validating... ${completeElapsed}s`
                          : 'Mark complete'}
                      </button>
                    )}
                  </div>
                )}

                {/* Author tier (bd 92qe.3): a schemaless kit WITH a PDF can be
                    extracted server-side. Editor-tier users see neither this
                    nor the upload control -- the server also refuses them. */}
                {isAuthor && !kit.hasSchema && kit.hasPdf && (
                  <div className="mt-1 flex items-center justify-end gap-2 px-1">
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
                          const isPdf = (file: File) =>
                            file.type === 'application/pdf'
                            || file.name.toLowerCase().endsWith('.pdf');
                          if (f && !isPdf(f)) {
                            setError('The instructions file must be a PDF.');
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
                          e.target.value = '';
                        }}
                      />
                      {instructionsPdfByKit[kit.id]
                        ? `instructions: ${instructionsPdfByKit[kit.id].name}`
                        : '+ instructions PDF'}
                    </label>
                    <label
                      className="text-xs text-gray-500 cursor-pointer hover:text-gray-700"
                      title="Also bake translated option labels (all supported spoken languages, pro-tier) into the extracted schema. Uncheck when just testing extraction strategies -- the standalone Translate options action can bake them later."
                    >
                      <input
                        type="checkbox"
                        className="mr-1 align-middle"
                        data-testid="translate-options-checkbox"
                        checked={translateOptionsChecked}
                        disabled={busy || extractingId !== null}
                        onChange={(e) => setTranslateOptionsChecked(e.target.checked)}
                      />
                      translate options
                    </label>
                    <label
                      className="text-xs text-gray-500 cursor-pointer hover:text-gray-700"
                      title="Also author booklet-grounded field guidance (instructions + official reference text) during extraction -- the larger of the two LLM add-ons. Uncheck when just testing extraction strategies."
                    >
                      <input
                        type="checkbox"
                        className="mr-1 align-middle"
                        data-testid="enrich-guidance-checkbox"
                        checked={enrichGuidanceChecked}
                        disabled={busy || extractingId !== null}
                        onChange={(e) => setEnrichGuidanceChecked(e.target.checked)}
                      />
                      enrich guidance
                    </label>
                    <button
                      className="btn-sm btn-primary text-xs"
                      onClick={() => void handleRunExtraction(kit)}
                      disabled={busy || extractingId !== null}
                      title="Run the automated PDF -> schema extraction on the server (takes a few minutes)"
                    >
                      {extractingId === kit.id
                        ? `Extracting... ${extractElapsed}s`
                        : 'Run extraction'}
                    </button>
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
