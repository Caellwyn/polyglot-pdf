import React from 'react';
import {
  AuthError, extractRemoteKit, listRemoteKits, loadRemoteSchema,
  deleteRemoteKit,
  onboardRemoteKit, releaseKitLock, setRemoteLabel, setRemoteStatus, takeKitLock,
  translateRemoteKitOptions, fetchRetireCandidates,
  type EditorRole, type KitLifecycleStatus, type RemoteKitEntry,
  type RetireCandidate,
} from '../utils/remoteKitStore';
import { readStamp, stampHint, STAMP_MARKER_SHORT } from '../utils/readinessStamp';
import { versionInfoFromSchema, type KitVersionInfo , isWriteLocked} from '../utils/formKitDirectory';
import { AuthorVersionDialog } from './AuthorVersionDialog';
import { RetireCandidatesDialog } from './RetireCandidatesDialog';
import { DeleteKitDialog } from './DeleteKitDialog';

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
  /**
   * Mirror a Mark-complete server refusal (publish gate 409/422, translation
   * coverage) up to the host, which homes it on the bottom strip's
   * refusal/error line with field links (sprint-18 C1, decision 1). Called
   * with null when a later status flip succeeds. The card's own inline error
   * stays -- the strip line is the home NEXT TO the counts the refusal
   * contradicts.
   */
  onStatusRefusal?: (detail: string | null) => void;
  /**
   * Reset the host's open-kit state (bd polyglot-pdf-hbfky), the same
   * callback FormCatalogue already receives for exactly this purpose.
   * Deleting the kit that is CURRENTLY OPEN must close the editor pane too --
   * without it, the card vanishes from the catalogue while the editor keeps
   * showing the deleted kit's fields, and Cmd+S then 404s with no indication
   * why (the kit simply no longer exists to save to). Optional so a caller
   * that never opens a kit through this catalogue (none exist today, but the
   * contract shouldn't force one) is not required to supply it.
   */
  clearOpenKit?: () => void;
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
  // Awaiting an author's review: visibly NOT done, but not a draft either
  // -- the editor's work is finished and out of their hands (bd
  // polyglot-pdf-hqztg).
  submitted: 'bg-blue-100 text-blue-700',
  // A retired revision reads as neutral-but-deliberate: it is not a draft
  // awaiting work, and not an error (bd polyglot-pdf-6dz0).
  unpublished: 'bg-slate-200 text-slate-700',
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
  defaultExpanded = false, onStatusRefusal, clearOpenKit,
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
  // The kit whose publish is waiting on an author version (bd polyglot-pdf-xzw5);
  // null when no dialog is open. Set from the publish gate's REFUSAL, not from
  // listing data -- the catalogue deliberately does not read every kit's schema,
  // so the server is what knows a version is needed.
  // Carries the ticked replacement THROUGH the version prompt (bd
  // polyglot-pdf-bdedm). The publish gate validates replaces_kit_id BEFORE it
  // asks for an author version, so a kit with a same-form candidate and no
  // edition date -- precisely the firm-tier custom form this bead targets --
  // takes both dialogs in turn. Re-calling the publish with only the version
  // dropped the retirement silently: the author ticked a kit, named a version,
  // and got a publish with nothing retired and no error (Opus fresh-eyes
  // round 1).
  const [versionPrompt, setVersionPrompt] = React.useState<
    { kit: RemoteKitEntry; replaces?: string } | null
  >(null);
  // The kit queued for permanent deletion (bd polyglot-pdf-6x1j), plus the
  // server's refusal when the guard says no. The refusal lives HERE rather
  // than in the page-level error line: a 409 explaining why this form cannot
  // be deleted has to be read next to the form it names.
  const [deletePrompt, setDeletePrompt] = React.useState<RemoteKitEntry | null>(null);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);
  const [deletingId, setDeletingId] = React.useState<string | null>(null);
  // The kit whose lock is being taken/released right now (bd
  // polyglot-pdf-hqztg), so its buttons can disable without freezing the
  // whole catalogue.
  const [lockingId, setLockingId] = React.useState<string | null>(null);
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
      // Review % per kit comes from the kit's READINESS STAMP, which the
      // backend wrote at save/publish with publish_readiness -- the same
      // definition the open editor's strip mirrors (sprint-18 C4, bd
      // polyglot-pdf-g687). The card reports a stored answer rather than
      // deriving a second one, so a card and the open kit cannot disagree
      // (bd polyglot-pdf-q3rm was exactly that disagreement). An absent,
      // unverified, or stale stamp yields the verify hint -- never a
      // re-scanned percentage, which would restore the two-definitions bug.
      //
      // The schema fetch below survives ONLY for the card's VERSION line
      // (edition date), which no stamp carries; it no longer computes any
      // percentage. Folding version into the stamp would let the listing drop
      // this fetch entirely -- filed as its own bead rather than widened into
      // this one.
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
          // Percentage comes from the stamp (read at render), NOT from here --
          // this fetch now yields only the version line.
          return [e.id, {
            reviewPercent: null,
            completeFields: 0,
            totalFields: 0,
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

  // Permanently remove a kit. The ONLY destructive handler in this module: the
  // server's guard decides (records exist / verified clean / could not check),
  // and a 409 is the guard WORKING, so it renders inside the dialog rather
  // than dismissing it.
  const handleDelete = React.useCallback(async (kit: RemoteKitEntry) => {
    setDeleteError(null);
    // Clear any stale success banner, as every sibling handler does. Without
    // it, deleting kit A and then being REFUSED on kit B showed a green
    // '"A" was deleted permanently' beside B's red refusal -- on the one
    // workflow where "did that just delete something?" must never be
    // ambiguous (Opus fresh-eyes round 4).
    setNotice(null);
    setDeletingId(kit.id);
    try {
      await deleteRemoteKit(kit.id);
      setDeletePrompt(null);
      setNotice(`"${kit.label}" was deleted permanently.`);
      // Close the editor pane if the deleted kit was the OPEN one (bd
      // polyglot-pdf-hbfky) -- without this, the card vanishes from the
      // catalogue below while the editor keeps showing the deleted kit's
      // fields, and Cmd+S then 404s with no indication why.
      if (kit.id === selectedKitId) clearOpenKit?.();
      await refresh();
    } catch (err) {
      if (err instanceof AuthError) { onAuthError?.(); return; }
      // The guard refusing (409) is the NORMAL outcome for a form anyone has
      // filled, and for one whose records cannot be checked. Keep the dialog
      // open and show the server's own words -- it names the safe alternative.
      setDeleteError(err instanceof Error ? err.message : 'Could not delete the form');
    } finally {
      setDeletingId(null);
    }
  }, [refresh, onAuthError, selectedKitId, clearOpenKit]);

  // Promote/demote a kit in the SHARED store. Promotion can be refused by the
  // server's publish gate (schema must validate) -- surface that detail. A
  // complete flip ALSO runs the server-side translation drift sweep (bd
  // polyglot-pdf-783r): re-translating spoken names / option labels whose
  // English drifted during review, then refusing completion until every
  // language is covered. The sweep is slow (a pro-tier call per language with
  // retry), so a complete flip shows the elapsed ticker via completingId, and a
  // 409 "N of M translations complete" refusal surfaces as the error to re-press.
  // Take or release a kit for editing. An author can always take one back from
  // an editor -- that preemption IS the stale-lock release, so a kit someone
  // abandoned is freed by a human rather than a timer (bd polyglot-pdf-hqztg).
  const handleLock = React.useCallback(async (
    kit: RemoteKitEntry, take: boolean,
  ) => {
    setError(null);
    // Clear the stale notice too, as all six sibling handlers do. This is the
    // one handler that WRITES a success notice, so it is precisely the one
    // that can leave "You have X for editing" sitting above a later failure
    // about the same kit (Opus fresh-eyes round 5).
    setNotice(null);
    setLockingId(kit.id);
    try {
      const res = take ? await takeKitLock(kit.id) : await releaseKitLock(kit.id);
      // Say so when we TOOK it from someone, rather than silently winning --
      // the other person cannot be notified (there is no server-to-client
      // channel), so the person who did it should at least know they did.
      setNotice(res.preempted
        ? `You took "${kit.label}" from an editor. They will find out when they `
          + 'next try to save.'
        : take
          ? `You have "${kit.label}" for editing.`
          : `Released "${kit.label}".`);
      await refresh();
    } catch (err) {
      if (err instanceof AuthError) { onAuthError?.(); return; }
      setError(err instanceof Error ? err.message : 'Could not change the lock');
    } finally {
      setLockingId(null);
    }
  }, [refresh, onAuthError]);

  // publishWithRetireCheck is declared before handleSetStatus (it is what the
  // buttons call), so it reaches the handler through a ref rather than forcing
  // a reorder of the whole component.
  const handleSetStatusRef = React.useRef<
    ((kit: RemoteKitEntry, status: KitLifecycleStatus,
      authorVersion?: string, replacesKitId?: string) => Promise<void>) | null
  >(null);

  // Set only while an author is being ASKED which older version to retire.
  // Holds the pending publish so the answer can complete it.
  const [retirePrompt, setRetirePrompt] = React.useState<
    { kit: RemoteKitEntry; authorVersion?: string; candidates: RetireCandidate[] } | null
  >(null);

  /**
   * Publish, ASKING FIRST if another live kit looks like the same form.
   *
   * Zero candidates -> straight through, no extra step (the common case; the
   * bead is explicit that the normal publish must not grow a dialog).
   *
   * A FAILED lookup also goes straight through. The suggestion is a
   * convenience; blocking a publish because we could not compute one would
   * make an optional nicety load-bearing.
   */
  const publishWithRetireCheck = React.useCallback(async (
    kit: RemoteKitEntry, authorVersion?: string,
  ) => {
    let candidates: RetireCandidate[] = [];
    try {
      candidates = await fetchRetireCandidates(kit.id);
    } catch {
      candidates = [];
    }
    if (candidates.length === 0) {
      await handleSetStatusRef.current?.(kit, 'complete', authorVersion);
      return;
    }
    setRetirePrompt({ kit, authorVersion, candidates });
  }, []);

  const handleSetStatus = React.useCallback(async (
    kit: RemoteKitEntry, status: KitLifecycleStatus, authorVersion?: string,
    replacesKitId?: string,
  ) => {
    setNotice(null);
    setBusy(true);
    setError(null);
    // The strip's refusal line describes the OPEN kit only. The compact
    // selector gates status actions to the open kit, but the EXPANDED card
    // grid offers Mark complete on every schema-bearing card -- so a refusal
    // about kit B must never land on (or clear) open kit A's strip, where
    // its "Go to:" links would name B's fields (Opus outer review, pass 3;
    // the same gate FormCatalogue's local cards got in pass 2).
    const mirrorsToStrip = kit.id === selectedKitId;
    if (mirrorsToStrip) onStatusRefusal?.(null);
    if (status === 'complete') setCompletingId(kit.id);
    try {
      const result = await setRemoteStatus(kit.id, status, { authorVersion, replacesKitId });
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
      } else if (status === 'unpublished') {
        // Name what actually happened: this is a retirement, not a revert.
        // The stale two-branch notice called it "reverted to draft", which is
        // the wrong action AND implies it is editable again -- it is not.
        setNotice(
          `"${kit.label}" is unpublished -- clients no longer see it, its `
          + 'files are kept, and it cannot be edited. Publish it again to put '
          + 'it back in service.',
        );
      } else if (status === 'submitted') {
        // A FOURTH status, and this chain's terminal `else` said "reverted to
        // draft" for anything it did not name -- so the editor tier's most-used
        // new action reported the OPPOSITE of what happened. The `unpublished`
        // branch above exists because that status hit this same bug; adding a
        // status without adding a branch reintroduced it (Opus fresh-eyes
        // round 6). Name every status explicitly rather than relying on the
        // fall-through.
        setNotice(
          `"${kit.label}" is submitted for review. An author checks it and `
          + 'publishes it; it is frozen until they do.',
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
      const detail = err instanceof Error ? err.message : 'Failed to update status';
      // The kit has no government edition date and no version yet, so the
      // publish gate is asking for one (bd polyglot-pdf-xzw5). Open the dialog
      // and let the author name the revision, rather than showing them a raw
      // refusal they cannot act on. Keyed on the machine-readable token the
      // route emits -- the catalogue listing deliberately does not read every
      // kit's schema, so the SERVER is what knows a version is needed.
      if (detail.startsWith('AUTHOR_VERSION_REQUIRED:')) {
        setVersionPrompt({ kit, replaces: replacesKitId });
        return;
      }
      setError(detail);
      // A refused completion of the OPEN kit also lands on the strip's
      // refusal line (sprint-18 C1): the refusal renders next to the counts
      // it contradicts, with click-to-focus links for any "(id=x)" the gate
      // names. A refusal about a DIFFERENT kit stays on its card only.
      // BOTH gated transitions, not just publish: an editor's SUBMIT runs
      // the same readiness/lint gate, and its refusal names the same
      // fields -- so it belongs on the strip beside the counts it
      // contradicts. Keying on 'complete' alone meant the tier that
      // actually does the work never saw the field links (bd
      // polyglot-pdf-hqztg; caught by an App-level test, not by this file).
      if ((status === 'complete' || status === 'submitted') && mirrorsToStrip) {
        onStatusRefusal?.(detail);
      }
    } finally {
      // BOTH resets belong here. setBusy(false) used to live at the end of the
      // catch, which every early `return` in that block skipped -- and `busy`
      // gates every control in this catalogue (Mark complete, Unpublish,
      // Revert, Refresh, Rename, Extract), so one skipped reset disabled the
      // whole component until a reload. The version-prompt return made that
      // reachable by simply cancelling the dialog (Opus fresh-eyes,
      // reproduced); the AuthError return had the same shape and was only
      // survivable because it tears down to the auth gate anyway.
      setBusy(false);
      setCompletingId(null);
    }
  }, [refresh, onAuthError, onStatusRefusal, selectedKitId]);

  handleSetStatusRef.current = handleSetStatus;

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
      // the reload below the lint pass re-emits them and they render at their
      // option rows in the field editor (sprint-18 C1 -- the warnings pane
      // that used to list them is gone). The notice points the author there.
      const flagCount = report.flags?.length ?? 0;
      const flagNote = flagCount
        ? `; ${flagCount} translation flag${flagCount === 1 ? '' : 's'} to ` +
          'review (open the kit -- flagged fields are marked in the list, ' +
          'and each flag shows on its answer choice in the field editor)'
        : '';
      if (!report.changed && flagCount === 0) {
        setNotice(`"${kit.id}" option labels are already fully translated.`);
      } else if (!report.changed) {
        // No label changed, but the verify gate still flagged translations
        // (reachable on a force re-bake that reproduces identical values):
        // the backend persisted the flags into provenance, so point at the
        // flagged rows and reload the stored schema like any other change.
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
    let complete = 0, inProgress = 0, noSchema = 0, unpublished = 0;
    for (const k of kits) {
      if (!k.hasSchema) noSchema++;
      else if (k.status === 'complete') complete++;
      // A retired revision is NOT pending work -- counting it as in-progress
      // would inflate the backlog with forms nobody is expected to finish.
      else if (k.status === 'unpublished') unpublished++;
      else inProgress++;
    }
    return { total: kits.length, complete, inProgress, noSchema, unpublished };
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
          {/* Rendered so the sub-counts still add up to the total: a retired
              revision is neither complete nor pending work, so without this it
              would silently vanish from the breakdown. */}
          {summary.unpublished > 0 && (
            <span className="text-slate-600">{summary.unpublished} retired</span>
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
              // Same precedence AND the same stamp rule as the expanded card
              // (sprint-18 C4): live > this session's saved value > the kit's
              // stamp. NEVER progress[].reviewPercent -- see the FormCatalogue
              // twin (fresh-eyes gap 1); it is dead null here today, but
              // leaving the read in place invites the fallback back.
              // Withheld when the schema is unreadable, exactly as on the card
              // (round 3 fixed the card and MISSED the strip -- so the default
              // view still printed a confident % that the card below it
              // simultaneously denied; Opus fresh-eyes round 4).
              const stripStamp = progress[k.id]?.schemaError
                ? null : readStamp(k.readiness);
              const pct = liveProgress && liveProgress.kitId === k.id
                ? liveProgress.percent
                : (editedProgress[k.id]?.percent
                   ?? (stripStamp?.kind === 'ok' ? stripStamp.stamp.percent : null));
              // Says so when there is no trustworthy stamp -- see the
              // FormCatalogue twin for why withholding the number alone was
              // not enough (both Opus outer reviewers flagged it).
              const stripUnmeasured = pct === null && k.hasSchema
                && !progress[k.id]?.schemaError;
              return (
                <option key={k.id} value={k.id}>
                  {k.label} -- {k.status}
                  {pct !== null ? `, ${pct}%` : ''}
                  {stripUnmeasured ? STAMP_MARKER_SHORT : ''}
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
                  // BOTH live-kit actions are author-only (bd
                  // polyglot-pdf-hqztg): reopening AND retiring reach back into
                  // a form clients are using. Rendering them to an editor left
                  // two controls that 403 -- one of which (Unpublish) actually
                  // SUCCEEDED before the server gate was widened. An editor
                  // gets the reason instead of a dead button.
                  isAuthor ? (
                  <>
                    <button
                      className="btn-sm btn-secondary text-xs"
                      onClick={() => void handleSetStatus(kit, 'draft')}
                      disabled={busy}
                      title="Revert to draft to edit it (archives the published version first, and removes it from the next deploy)"
                    >
                      Revert to draft
                    </button>
                    <button
                      className="btn-sm btn-secondary text-xs"
                      onClick={() => void handleSetStatus(kit, 'unpublished')}
                      disabled={busy}
                      title="Retire this version: clients stop seeing it, the files stay, and it cannot be edited -- earlier confirmations point at it. Publish again to restore."
                    >
                      Unpublish
                    </button>
                  </>
                  ) : (
                    <span
                      className="text-xs text-slate-600"
                      title="This form is live. Only an author can reopen or retire it."
                    >
                      Published -- ask an author to reopen it
                    </span>
                  )
                ) : kit.status === 'unpublished' ? (
                  // A retired revision returns to service ONLY through the full
                  // publish gate -- never via draft, which would make its
                  // audit-referenced bytes editable again.
                  <button
                    className="btn-sm btn-primary text-xs"
                    onClick={() => void publishWithRetireCheck(kit)}
                    disabled={busy || completingId !== null}
                    title="Publish this retired version again (runs the full publish gate)"
                  >
                    {completingId === kit.id
                      ? `Re-translating & validating... ${completeElapsed}s`
                      : 'Publish again'}
                  </button>
                ) : kit.status === 'submitted' ? (
                  // The strip's twin of the card-grid block below. Both must
                  // move together -- editing one of a pair and missing the
                  // other is this repo's most repeated defect.
                  isAuthor ? (
                    <>
                      <button
                        className="btn-sm btn-primary text-xs"
                        onClick={() => void publishWithRetireCheck(kit)}
                        disabled={busy || completingId !== null}
                        title="Publish this form -- runs the full publish gate"
                      >
                        {completingId === kit.id
                          ? `Re-translating & validating... ${completeElapsed}s`
                          : 'Publish'}
                      </button>
                      <button
                        className="btn-sm text-xs"
                        onClick={() => void handleSetStatus(kit, 'draft')}
                        disabled={busy || completingId !== null}
                        title="Send this back to the editor for more work. Any version they entered is cleared, since it was never published."
                      >
                        Send back
                      </button>
                    </>
                  ) : (
                    <button
                      className="btn-sm text-xs"
                      onClick={() => void handleSetStatus(kit, 'draft')}
                      disabled={busy || completingId !== null}
                      title="Reopen your own submission to keep working on it"
                    >
                      Reopen
                    </button>
                  )
                ) : (
                  <button
                    className="btn-sm btn-primary text-xs"
                    // An AUTHOR publishing goes through the retire check; an
                    // EDITOR is only submitting for review, which retires
                    // nothing and must not be asked about it.
                    onClick={() => void (isAuthor
                      ? publishWithRetireCheck(kit)
                      : handleSetStatus(kit, 'submitted'))}
                    disabled={busy || stripDirty || completingId !== null}
                    title={stripDirty
                      ? 'Save your changes first (Cmd+S) -- submitting now '
                        + 'would send the last saved version, not your edits'
                      : isAuthor
                        ? "Publish (re-translates any drifted names/options, "
                          + "then ships with the maintainer's next deploy)"
                        : 'Submit for review -- an author checks it and '
                          + 'publishes it'}
                  >
                    {completingId === kit.id
                      ? `Re-translating & validating... ${completeElapsed}s`
                      : isAuthor ? 'Publish' : 'Submit for review'}
                  </button>
                ))}
                {/* Derived, not hand-listed: this predicate named two of the
                    three write-locked statuses, so it offered a live-looking
                    action on a submitted kit that the server 409s. */}
                {isAuthor && kit.hasSchema && !isWriteLocked(kit.status) && (
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
            // With no live/session value, the card reports the kit's STAMP
            // (sprint-18 C4). A stamp that is absent, unverified, or stale
            // yields the hint instead of a number -- deliberately NOT a
            // re-scan (that is the two-definitions bug this bead ends).
            // An unreadable schema is reported REGARDLESS of whether a stamp
            // exists. Before C4 this could safely key on `pct === null`,
            // because pct came from the same scan that set schemaError. Now
            // pct comes from the STAMP, so a kit whose schema.json became
            // corrupt AFTER its last save would have rendered a confident
            // percentage AND swallowed the corruption notice -- a card
            // asserting progress about a schema nobody can read, which is the
            // very class of lie this bead exists to end (Opus fresh-eyes
            // round 3; regression introduced by this diff).
            const showSchemaError = !source && Boolean(prog?.schemaError);
            // ...and the stamp is withheld in that case at the SOURCE: a stamp
            // measured an earlier, readable schema, so it cannot describe the
            // one on disk now. Suppressing here (rather than at each render
            // site) means the bar, the hover counts and the hint all follow.
            const reading = source || showSchemaError
              ? null : readStamp(kit.readiness);
            const stamped = reading?.kind === 'ok' ? reading.stamp : null;
            const pct = source ? source.percent : (stamped ? stamped.percent : null);
            const completeFields = source ? source.complete : (stamped?.reviewed ?? 0);
            const totalFields = source ? source.total : (stamped?.total ?? 0);
            // The verify hint: only for a schema-bearing kit (a kit with no
            // schema has nothing to measure and already says so) and never
            // alongside the louder unreadable-schema error.
            const stampGap = !source && kit.hasSchema && !showSchemaError
              && reading?.kind === 'hint' ? reading.reason : null;
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
                          // Exact ratio, not the ROUNDED pct (bd polyglot-pdf-87zbs):
                          // pct===100 also fires at 199/200 (Math.round(99.5)),
                          // painting a confident GREEN 100% bar on a kit that is
                          // NOT actually finished -- directly contradicting this
                          // same card's own hover title a few lines up.
                          className={`h-full ${completeFields === totalFields && totalFields > 0 ? 'bg-green-500' : 'bg-yellow-500'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {stampGap && (
                    <div className="mt-2 text-xs text-gray-500"
                         data-testid="readiness-hint">
                      {stampHint(stampGap)}
                    </div>
                  )}

                  {showSchemaError && (
                    <div className="mt-2 text-xs text-red-600">
                      Schema present but unreadable -- can't measure review progress.
                    </div>
                  )}
                </button>

                {/* The editing lock (bd polyglot-pdf-hqztg). Shown per kit so
                    an author can see who has it and take it back. There is no
                    server-to-client channel, so a preempted editor learns of it
                    on their next save (a 409) rather than from a push. */}
                {kit.hasSchema && (
                  <div className="mt-1 flex items-center justify-end gap-2 px-1">
                    {kit.heldBy && (
                      <span
                        className="text-xs text-slate-500"
                        title={kit.heldBy === 'author'
                          ? 'An author has this form for editing.'
                          : 'An editor has this form for editing.'}
                      >
                        {kit.heldBy === 'author' ? 'Author editing' : 'Editor editing'}
                      </span>
                    )}
                    {kit.heldBy === (isAuthor ? 'author' : 'editor') ? (
                      <button
                        className="btn-sm text-xs"
                        onClick={() => void handleLock(kit, false)}
                        disabled={busy || lockingId !== null}
                        title="Release this form so someone else can edit it"
                      >
                        {lockingId === kit.id ? 'Releasing...' : 'Release'}
                      </button>
                    ) : (isAuthor || kit.heldBy !== 'author') && (
                      <>
                        <button
                          className="btn-sm text-xs"
                          onClick={() => void handleLock(kit, true)}
                          disabled={busy || lockingId !== null}
                          title={kit.heldBy === 'editor' && isAuthor
                            ? 'Take this form back from the editor who has it'
                            : 'Take this form for editing'}
                        >
                          {lockingId === kit.id
                            ? 'Taking...'
                            : kit.heldBy === 'editor' && isAuthor ? 'Take back' : 'Take for editing'}
                        </button>
                        {kit.heldBy === 'editor' && isAuthor && (
                          // The stale-lock escape, and it must be its own
                          // action: "Take back" TRANSFERS the lock to the
                          // author, so freeing an abandoned kit would take two
                          // steps and leave it locked to an absent author if
                          // they forgot the second (found by enumerating the
                          // six holder x viewer cells).
                          <button
                            className="btn-sm text-xs"
                            onClick={() => void handleLock(kit, false)}
                            disabled={busy || lockingId !== null}
                            title="Free this form without taking it -- for a lock someone left behind"
                          >
                            {lockingId === kit.id ? 'Releasing...' : 'Free it'}
                          </button>
                        )}
                      </>
                    )}
                  </div>
                )}

                {kit.hasSchema && (
                  <div className="mt-1 flex items-center justify-end gap-2 px-1">
                    {kit.status === 'complete' ? (
                      // The card-grid TWIN of the strip block above. Both
                      // live-kit actions are author-only (bd
                      // polyglot-pdf-hqztg); an editor sees the reason.
                      isAuthor ? (
                      <>
                        <button
                          className="btn-sm btn-secondary text-xs"
                          onClick={() => void handleSetStatus(kit, 'draft')}
                          disabled={busy}
                          title="Revert to draft to edit it (archives the published version first, and removes it from the next deploy)"
                        >
                          Revert to draft
                        </button>
                        <button
                          className="btn-sm btn-secondary text-xs"
                          onClick={() => void handleSetStatus(kit, 'unpublished')}
                          disabled={busy}
                          title="Retire this version: clients stop seeing it, the files stay, and it cannot be edited -- earlier confirmations point at it. Publish again to restore."
                        >
                          Unpublish
                        </button>
                      </>
                      ) : (
                        <span
                          className="text-xs text-slate-600"
                          title="This form is live. Only an author can reopen or retire it."
                        >
                          Published -- ask an author to reopen it
                        </span>
                      )
                    ) : kit.status === 'unpublished' ? (
                      // Retired: back into service ONLY through the publish
                      // gate, never via draft (which would make its
                      // audit-referenced bytes editable again).
                      <button
                        className="btn-sm btn-primary text-xs"
                        onClick={() => void publishWithRetireCheck(kit)}
                        disabled={busy || completingId !== null}
                        title="Publish this retired version again (runs the full publish gate)"
                      >
                        {completingId === kit.id
                          ? `Re-translating & validating... ${completeElapsed}s`
                          : 'Publish again'}
                      </button>
                    ) : kit.status === 'submitted' ? (
                      // Awaiting review. An AUTHOR publishes or sends it back;
                      // the EDITOR who submitted it can only reopen their own
                      // work (bd polyglot-pdf-hqztg).
                      isAuthor ? (
                        <>
                          <button
                            className="btn-sm btn-primary text-xs"
                            onClick={() => void publishWithRetireCheck(kit)}
                            disabled={busy || completingId !== null}
                            title="Publish this form -- runs the full publish gate"
                          >
                            {completingId === kit.id
                              ? `Re-translating & validating... ${completeElapsed}s`
                              : 'Publish'}
                          </button>
                          <button
                            className="btn-sm text-xs"
                            onClick={() => void handleSetStatus(kit, 'draft')}
                            disabled={busy || completingId !== null}
                            title="Send this back to the editor for more work. Any version they entered is cleared, since it was never published."
                          >
                            Send back
                          </button>
                        </>
                      ) : (
                        <button
                          className="btn-sm text-xs"
                          onClick={() => void handleSetStatus(kit, 'draft')}
                          disabled={busy || completingId !== null}
                          title="Reopen your own submission to keep working on it"
                        >
                          Reopen
                        </button>
                      )
                    ) : (
                      <button
                        className="btn-sm btn-primary text-xs"
                        // Twin of the strip button above -- both must move
                        // together, which is this repo's most repeated defect.
                        onClick={() => void (isAuthor
                          ? publishWithRetireCheck(kit)
                          : handleSetStatus(kit, 'submitted'))}
                        disabled={busy || openDirty || completingId !== null}
                        title={openDirty
                          ? 'Save your changes first (Cmd+S) -- submitting now '
                            + 'would send the last saved version, not your edits'
                          : isAuthor
                            ? "Publish (re-translates any drifted names/options, "
                              + "then ships with the maintainer's next deploy)"
                            : 'Submit for review -- an author checks it and '
                              + 'publishes it'}
                      >
                        {completingId === kit.id
                          ? `Re-translating & validating... ${completeElapsed}s`
                          : isAuthor ? 'Publish' : 'Submit for review'}
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
                {/* AUTHOR ONLY, deliberately (bd polyglot-pdf-6x1j): editors
                    never take destructive actions -- their work must always be
                    recoverable. The server enforces the same rule, since an
                    editor holds a token and can call the API directly. Kept
                    visually apart from the publish controls and last in the
                    card, so it is never the button next to the one you meant. */}
                {isAuthor && (
                  <div className="mt-2 flex items-center justify-end border-t border-slate-100 px-1 pt-1">
                    <button
                      className="text-xs text-slate-400 hover:text-red-700"
                      onClick={() => { setDeleteError(null); setDeletePrompt(kit); }}
                      disabled={busy || deletingId !== null}
                      title="Delete this form permanently -- refused if anyone has already filled it"
                    >
                      Delete
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

      {/* Opened by the publish gate's AUTHOR_VERSION_REQUIRED refusal, never
          from listing data (bd polyglot-pdf-xzw5). Confirming re-runs the same
          publish with the version attached -- so the server decides, and this
          client never has to duplicate the "does this kit need one?" rule. */}
      {/* Author-only, and the server enforces that too -- an editor holds a
          token and can call the API directly, so hiding the button is not the
          gate (bd polyglot-pdf-6x1j). */}
      {deletePrompt && (
        <DeleteKitDialog
          kitId={deletePrompt.id}
          kitLabel={deletePrompt.label}
          busy={deletingId === deletePrompt.id}
          error={deleteError}
          onCancel={() => { setDeletePrompt(null); setDeleteError(null); }}
          onConfirm={() => { void handleDelete(deletePrompt); }}
        />
      )}

      {/* Suggest-and-confirm, never auto-retire (maintainer decision
          2026-08-07). Opens ONLY when the server found a live kit that looks
          like the same form; zero candidates publishes straight through, so
          the normal flow gains no step. */}
      {retirePrompt && (
        <RetireCandidatesDialog
          kitLabel={retirePrompt.kit.label}
          candidates={retirePrompt.candidates}
          busy={completingId === retirePrompt.kit.id}
          onCancel={() => setRetirePrompt(null)}
          onPublish={(replaces) => {
            const { kit, authorVersion } = retirePrompt;
            setRetirePrompt(null);
            void handleSetStatus(kit, 'complete', authorVersion, replaces);
          }}
        />
      )}

      {versionPrompt && (
        <AuthorVersionDialog
          kitLabel={versionPrompt.kit.label}
          // versionInfoFromSchema's fallback chain ends in the literal
          // 'unknown', and this dialog only ever opens for a kit with NO
          // marker -- so passing the label straight through rendered
          // "Previous version: unknown" 100% of the time. Map it to null so
          // the line hides instead.
          previousVersion={(() => {
            const label = progress[versionPrompt.kit.id]?.version?.label;
            return label && label !== 'unknown' ? label : null;
          })()}
          // Stays mounted through the retry: the publish re-translates one
          // language per LLM call, so it can run for tens of seconds. Closing
          // the dialog first left the author staring at an unchanged catalogue
          // with no progress and an inviting Mark complete button -- and made
          // the dialog's own busy/double-submit guard unreachable.
          busy={completingId === versionPrompt.kit.id}
          onCancel={() => setVersionPrompt(null)}
          onConfirm={(version) => {
            // The 4th argument is what round 1 found missing: without it
            // the ticked kit is silently not retired.
            void handleSetStatus(
              versionPrompt.kit, 'complete', version, versionPrompt.replaces)
              .finally(() => setVersionPrompt(null));
          }}
        />
      )}
    </div>
  );
};
