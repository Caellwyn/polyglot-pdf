import React from 'react';
import { FormSelector } from './components/FormSelector';
import { FormCatalogue } from './components/FormCatalogue';
import { RemoteCatalogue } from './components/RemoteCatalogue';
import { AccessCodeGate } from './components/AccessCodeGate';
import { HostedGuide, hasSeenGuide } from './components/HostedGuide';
import { PDFViewer } from './components/PDFViewer';
import { FieldList } from './components/FieldList';
import { FieldEditor } from './components/FieldEditor';
import PreviewPane from './components/PreviewPane';
import { ValidationPanel } from './components/ValidationPanel';
import { loadSchema, saveSchema } from './utils/schemaLoader';
import {
  isDirectoryAccessSupported,
  isFileSystemAccessSupported,
  isUserAbort,
  pickSchemaFile,
  readSchemaFromHandle,
  writeSchemaToHandle,
  type FsDirectoryHandle,
  type FsFileHandle,
} from './utils/fileSystemAccess';
import {
  loadKitSchema, verifySameFolder, versionInfoFromSchema,
  type CatalogueEntry, type FolderCheck, type KitVersionInfo,
} from './utils/formKitDirectory';
import {
  AuthError,
  hasBackend,
  isHostedMode,
  loadRemotePdfBlobUrl,
  loadRemoteSchema,
  loadUnclaimedWidgets,
  regenerateDivisions,
  regenerateGuidance,
  repairKit,
  verifyStoreFolder,
  saveRemoteSchema,
  type EditorRole,
  type LintFinding,
  type LintReport,
  type RemoteKitEntry,
} from './utils/remoteKitStore';
import { isReviewTargetFromFindings, reviewCounts } from './utils/reviewStatus';
import {
  bucketFindingsByField, visibleFormFindings, withFormFindingDismissed,
} from './utils/lintFindings';
import { mergeFields, ungroupField, changeGroupKind } from './utils/fieldGrouping';
import {
  recoverSelectionAfterVanish, renameBlockReason, renameFieldId,
} from './utils/fieldRename';
import {
  dependentsOf, describeIgnoreBlock, ignoreBlockReason, ignoreField,
  isIgnored, restoreField,
} from './utils/ignoreField';
import { SectionManager } from './components/SectionManager';
import type { DivisionsPatch } from './utils/sectionOps';
import { useSchemaHistory } from './hooks/useSchemaHistory';
import type { FormField, FormConfig, FormSchema, FormSection } from './types/schema';

// Live review stats for the open kit's catalogue bar (percent + the matching
// complete/total counts, so the bar AND its hover detail both track edits).
// Also carries the live version summary so an in-session metadata edit refreshes
// the card's version line instead of showing the stale disk-scan value (Codex
// PR #263). Exported for App.liveStats.test.ts, which pins the lintFindings
// argument reaching the guidance-ack gate (Opus round 4). `lintFindings` is
// deliberately REQUIRED -- pass undefined explicitly when none exist: as an
// optional parameter, a call site could silently revert to the gate-blind
// `liveStats(schema)` with the whole suite green (Opus round 5, measured);
// required, that revert is a compile error.
export function liveStats(
  schema: FormSchema,
  lintFindings: LintFinding[] | undefined,
): { percent: number; complete: number; total: number; version: KitVersionInfo } {
  // ONE count predicate (sprint-18 C1, decision 2): the catalogue bar's live %
  // computes the same reviewCounts the bottom strip shows -- reviewed_correct,
  // not demoted by the ack gate or the timeliness rule, no field lint ERROR --
  // over the same shared bucketing, so the two surfaces can never disagree
  // about the open kit.
  const s = reviewCounts(schema.fields, bucketFindingsByField(lintFindings));
  return {
    percent: s.percentage, complete: s.reviewed, total: s.total,
    version: versionInfoFromSchema(schema),
  };
}

export const App: React.FC = () => {
  // Hosted delivery mode (bd polyglot-pdf-92qe.2): kits come from the backend's
  // token-gated /api/editor routes (the shared store) instead of a local
  // folder. `role` is null until the access code validates (the gate screen);
  // author-only affordances (onboard/extract, bd 92qe.3) key off it later.
  const hosted = React.useMemo(isHostedMode, []);
  // Can we call the server for authoritative lint / repair / regeneration?
  // Hosted always can; local dev can whenever the backend is running
  // (scripts/run-schema-editor.sh starts it). Kept SEPARATE from `hosted`,
  // which answers the different question of WHERE KITS LIVE -- conflating the
  // two is what silently made local a reduced-feature surface
  // (bd polyglot-pdf-cpiw). Safe for local kit ids because the backend's
  // default store is this same form-kits/ directory (LocalFormKitStore), so a
  // kit id from the picked folder resolves server-side unchanged.
  const backendAvailable = React.useMemo(hasBackend, []);
  // Same-folder handshake (bd polyglot-pdf-s2bf). In LOCAL mode the editor
  // reads/writes the folder the human PICKED while the backend resolves kit ids
  // against its OWN root; when those differ, the server-side actions rewrite a
  // DIFFERENT copy than the one on screen -- destructive and invisible. Until
  // the two are proven to agree, those actions stay off.
  //   null    -> not checked yet (or nothing picked): server actions OFF
  //   {ok}    -> proven same folder: server actions ON
  //   {!ok}   -> proven different / unwritable: OFF, and the modal explains
  const [folderCheck, setFolderCheck] = React.useState<FolderCheck | null>(null);
  const [folderModalOpen, setFolderModalOpen] = React.useState(false);
  // Drops a stale handshake result when the folder changes mid-flight -- see
  // handleRootChange for why this guard is load-bearing rather than tidy.
  const folderSeqRef = React.useRef(0);
  const [role, setRole] = React.useState<EditorRole | null>(null);
  // Remote saves have real latency (a GCS write) -- surface a Saving... state.
  const [saving, setSaving] = React.useState(false);
  const [selectedForm, setSelectedForm] = React.useState<FormConfig | null>(null);
  // Schema + undo/redo history (bd v3y8). `commit` is a user edit, `load` a
  // fresh load, `markSaved` clears the dirty flag, `clear` drops the schema.
  const {
    schema, isDirty: hasUnsavedChanges, canUndo, canRedo,
    commit: commitSchema, load: loadSchemaState, markSaved, clear: clearSchema,
    undo, redo,
  } = useSchemaHistory();
  // The LATEST schema, readable after an await: a remote save's completion
  // handler must compare against what the schema IS then, not the closure's
  // stale capture, or edits made while the PUT was in flight would be marked
  // clean and silently lost on unload (Codex P1, PR #280).
  const schemaRef = React.useRef(schema);
  React.useEffect(() => { schemaRef.current = schema; }, [schema]);
  const [selectedFieldId, setSelectedFieldId] = React.useState<string | null>(null);
  // The loaded PDF's page count, reported by PDFViewer (bd polyglot-pdf-g63j).
  // Threaded into the field list so a field claiming a page the document does
  // not have is named as such instead of silently painting nowhere. undefined
  // until the PDF loads -- the page-range check simply stays quiet until then.
  const [pdfPageCount, setPdfPageCount] = React.useState<number | undefined>(undefined);
  // Right-pane view mode (bd polyglot-pdf-s4dp.4): 'edit' shows the FieldEditor,
  // 'preview' swaps in the standalone interactive PreviewPane so the author can
  // TEST the form's logic (radio exclusivity, checkbox multi-select, show_if
  // visibility). PDF + field list stay visible in both modes.
  const [viewMode, setViewMode] = React.useState<'edit' | 'preview'>('edit');
  // Section-management modal (bd polyglot-pdf-6cfu.3).
  const [showSectionManager, setShowSectionManager] = React.useState(false);
  // The latest lint findings, mirrored up from the ValidationPanel (which owns
  // the lint round-trip) so the FIELD LIST can explain a red row in place
  // (bd polyglot-pdf-0x10.6).
  const [lintFindings, setLintFindings] = React.useState<LintFinding[]>([]);
  const handleLintReport = React.useCallback((report: LintReport | null) => {
    setLintFindings(report?.findings ?? []);
  }, []);
  const lintFindingsByField = React.useMemo(
    () => bucketFindingsByField(lintFindings), [lintFindings]);
  // Form-level findings (no field anchor) for the pinned Form row at the top
  // of the field list -- minus standalone-dismissed WARNINGs (sprint-18 C1).
  const formFindings = React.useMemo(
    () => (schema ? visibleFormFindings(schema, lintFindings) : []),
    [schema, lintFindings],
  );
  // Standalone dismiss for a form-level WARNING -- the ONLY standalone dismiss
  // in the editor (no field review can cover a schema-level finding). A
  // normal undoable commit, like any other schema edit.
  const handleDismissFormFinding = React.useCallback((finding: LintFinding) => {
    if (!schema) return;
    const next = withFormFindingDismissed(schema, finding);
    if (next !== schema) commitSchema(next);
  }, [schema, commitSchema]);
  // "M to review" as a CONTROL (sprint-18 C1, decision 2): the strip's count
  // jumps to the next review target; its secondary action filters the field
  // list to flagged fields -- the overview that used to justify a pane.
  const [reviewFilterActive, setReviewFilterActive] = React.useState(false);
  // The latest server refusal (publish gate / translation coverage), homed on
  // the strip's refusal line (decision 1: no refusal is ever homeless).
  const [publishRefusal, setPublishRefusal] = React.useState<string | null>(null);
  // All three are PER-FORM state, so every open/close path resets them
  // alongside selectedFieldId/viewMode -- a refusal naming form A's fields
  // (with dead "Go to:" links) must not sit on form B's strip, A's review
  // filter must not narrow B's list, and A's FINDINGS must not leak onto B:
  // visibleFormFindings promotes any finding whose id resolves to no field
  // onto the pinned Form row, so stale findings from A would render as B's
  // form-level errors -- and dismissing one would write A's fingerprint into
  // B's schema (Opus outer review, pass 1). The strip and field list are
  // additionally KEYED per form below, so their internal state (last lint
  // report, Form-row expansion, search) resets with the switch.
  const resetPerFormReviewUi = React.useCallback(() => {
    setReviewFilterActive(false);
    setPublishRefusal(null);
    // NOTE: lintFindings is deliberately NOT cleared here. This runs at the
    // TOP of an open, before the async load can fail -- and a failed open
    // leaves the previous form on screen with its strip (which keys on the
    // unchanged kit id, so it neither remounts nor re-fires onReport).
    // Clearing the mirror there would blank every row's findings while the
    // strip still counted them: the strip-vs-rows disagreement this bead
    // exists to end (Opus outer review, pass 9). The mirror is instead
    // cleared on SUCCESS, beside loadSchemaState, via clearLintMirror.
  }, []);
  // Clear the findings mirror at the point a DIFFERENT form actually becomes
  // the open one. The strip remounts on the same transition (it is keyed per
  // form) and re-lints, so this only covers the window before its first
  // report lands -- but in that window a stale finding from the previous
  // form would otherwise resolve to no field here and be promoted onto the
  // new form's pinned Form row.
  const clearLintMirror = React.useCallback(() => setLintFindings([]), []);
  // The fields in reading order -- sections as listed, then orphans -- the
  // same order the FieldList renders, so the strip's jump and the list's own
  // "Next to review" walk one order.
  const orderedFields = React.useMemo(() => {
    if (!schema) return [] as FormField[];
    // Defensive `?? []`s: a hand-authored or legacy schema can lack sections
    // (the editor opens it fine; only the publish gate demands the full shape).
    const fields = schema.fields ?? [];
    const byId = new Map(fields.map(f => [f.id, f]));
    const seen = new Set<string>();
    const ordered: FormField[] = [];
    for (const section of schema.sections ?? []) {
      for (const id of section.fields ?? []) {
        const f = byId.get(id);
        if (f && !seen.has(id)) { ordered.push(f); seen.add(id); }
      }
    }
    for (const f of fields) {
      if (!f.section_id && !seen.has(f.id)) ordered.push(f);
    }
    return ordered;
  }, [schema]);
  const handleJumpToReview = React.useCallback(() => {
    if (orderedFields.length === 0) return;
    // Option rows select as "<fieldId>:option:<n>" -- start from the base.
    const baseId = selectedFieldId ? selectedFieldId.split(':option:')[0] : null;
    const current = baseId ? orderedFields.findIndex(f => f.id === baseId) : -1;
    for (let step = 1; step <= orderedFields.length; step++) {
      const candidate = orderedFields[(current + step) % orderedFields.length];
      if (isReviewTargetFromFindings(
            candidate, lintFindingsByField.get(candidate.id))) {
        setViewMode('edit');
        setSelectedFieldId(candidate.id);
        return;
      }
    }
    // Every field is reviewed -> nothing to jump to.
  }, [orderedFields, selectedFieldId, lintFindingsByField]);
  // Multi-selection for the merge/group operation (bd polyglot-pdf-s4dp.1). This
  // is the set of fields ticked for a merge; insertion order is preserved (the
  // first ticked field is the merge primary). Separate from selectedFieldId,
  // which drives the single-field editor panel.
  const [groupSelection, setGroupSelection] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Save/reload failures are NON-blocking: they render as a dismissible banner
  // over the live editor instead of the full-screen error state, whose Dismiss
  // drops the schema -- a failed save must never cost the work being saved
  // (bd 92qe.5).
  const [saveError, setSaveError] = React.useState<string | null>(null);
  // First-run guide (hosted): shown once per browser, reopenable via Help.
  const [guideOpen, setGuideOpen] = React.useState(false);
  // The File System Access handle the human picked: once set, saves write
  // straight to that file with no re-prompt (bd s1e2). Cleared on form switch.
  const fileHandleRef = React.useRef<FsFileHandle | null>(null);
  // The OPEN kit's catalogue entry in local mode (null when hosted, or when
  // nothing is open). Server-side actions -- repair, regenerate-divisions,
  // regenerate-guidance -- rewrite the STORED schema and the editor must then
  // reload it; local mode has to re-read the file from disk rather than call
  // loadRemoteSchema, since its kits never went through the remote store
  // (bd polyglot-pdf-cpiw).
  const localEntryRef = React.useRef<CatalogueEntry | null>(null);
  const [savedFileName, setSavedFileName] = React.useState<string | null>(null);
  const fsAccess = React.useMemo(isFileSystemAccessSupported, []);
  const dirAccess = React.useMemo(isDirectoryAccessSupported, []);
  // The catalogue kit currently open (bd b0pe): its id (to highlight in the
  // catalogue) and a blob URL for its PDF (revoked when switching forms).
  const [selectedKitId, setSelectedKitId] = React.useState<string | null>(null);
  const pdfBlobUrlRef = React.useRef<string | null>(null);
  // True while the active save target is the OPEN kit's own schema file. A
  // "Save As..." to an arbitrary file flips this false, so the catalogue won't
  // cache progress that was never written back to the kit (Codex PR #224 r6).
  const [savingToKit, setSavingToKit] = React.useState(false);

  // Load schema when form is selected
  const handleSelectForm = React.useCallback(async (form: FormConfig) => {
    if (hasUnsavedChanges) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to switch forms?'
      );
      if (!confirmed) return;
    }

    setLoading(true);
    setError(null);
    setSaveError(null);
    setSelectedFieldId(null);
    setGroupSelection([]); // merge selection is per-form (bd polyglot-pdf-s4dp.1)
    setViewMode('edit'); // start a freshly-loaded form in edit mode (bd s4dp.4)
    resetPerFormReviewUi(); // refusal + review filter are per-form (s18 C1)
    // A new form means a new destination -- drop the prior file handle so the
    // next save prompts for where to put THIS form's schema.
    fileHandleRef.current = null;
    localEntryRef.current = null;
    setSavedFileName(null);
    setSelectedKitId(null); // leaving catalogue mode
    if (pdfBlobUrlRef.current) {
      URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = null;
    }

    try {
      const loadedSchema = await loadSchema(form.schemaPath);
      clearLintMirror(); // a DIFFERENT form is now open (s18 C1)
      loadSchemaState(loadedSchema); // fresh baseline -> history cleared
      setSelectedForm(form);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schema');
      console.error('Failed to load schema:', err);
    } finally {
      setLoading(false);
    }
  }, [hasUnsavedChanges, loadSchemaState, resetPerFormReviewUi, clearLintMirror]);

  // Open a kit from the catalogue (bd b0pe): read its schema from the directory
  // handle and build a blob URL for its PDF, then drive the existing schema +
  // PDFViewer flow. The kit's own schema file handle becomes the save target, so
  // Cmd+S writes back in place (no picker).
  const handleOpenKit = React.useCallback(async (entry: CatalogueEntry) => {
    if (hasUnsavedChanges) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to switch forms?'
      );
      if (!confirmed) return;
    }
    setLoading(true);
    setError(null);
    setSaveError(null);
    setSelectedFieldId(null);
    setGroupSelection([]); // merge selection is per-form (bd polyglot-pdf-s4dp.1)
    setViewMode('edit'); // start a freshly-opened kit in edit mode (bd s4dp.4)
    resetPerFormReviewUi(); // refusal + review filter are per-form (s18 C1)
    try {
      const loaded = await loadKitSchema(entry);
      if (!loaded) {
        throw new Error(`${entry.label} has no schema yet -- run the extraction first.`);
      }
      // Save target = the kit's own schema.json handle (in-place save).
      fileHandleRef.current = await entry.dirHandle.getFileHandle(entry.schemaFile);
      localEntryRef.current = entry; // for re-reading after a server-side rewrite
      setSavedFileName(entry.schemaFile);

      // Build a blob URL for the PDF so PDFViewer (which takes a URL) can render
      // it. Swap the blob URL only now that the fetch has succeeded. Revoking
      // the prior kit's URL BEFORE the fetch (the old order) meant a failed
      // getFileHandle/getFile call left the still-displayed prior kit pointing
      // at a dead URL: a silently broken PDF viewer (mirrors handleOpenRemoteKit,
      // bd 92qe.2).
      let pdfUrl = '';
      if (entry.hasPdf) {
        const pdfHandle = await entry.dirHandle.getFileHandle(entry.pdfFile);
        const pdfFile = await pdfHandle.getFile();
        pdfUrl = URL.createObjectURL(pdfFile);
      }
      if (pdfBlobUrlRef.current) URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = pdfUrl || null;

      clearLintMirror(); // a DIFFERENT kit is now open (s18 C1)
      loadSchemaState(loaded); // fresh baseline -> history cleared
      setSelectedForm({ name: entry.label, pdfPath: pdfUrl, schemaPath: entry.schemaFile });
      setSelectedKitId(entry.id);
      setSavingToKit(true); // save target is the kit's own schema until a Save As

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open form');
      console.error('Failed to open kit:', err);
    } finally {
      setLoading(false);
    }
  }, [hasUnsavedChanges, loadSchemaState, resetPerFormReviewUi, clearLintMirror]);

  // A remote call answered 401 mid-session (rotated/revoked code): drop back to
  // the access gate. The gate re-probes the stored code, finds it dead, clears
  // it, and shows the entry form -- so the contractor lands on "enter your code"
  // rather than a dead editor.
  //
  // DELIBERATE: this does NOT tear down the open kit or dirty edits. A code
  // rotation mid-polish must not destroy a contractor's unsaved work -- after
  // re-entering a valid code they resume exactly where they were and can save.
  // Nothing stale is trusted: every subsequent request re-authenticates with
  // the NEW code server-side; the in-memory schema/PDF are display state only.
  // (Fresh-eyes flagged the asymmetry vs the kit-switch teardowns; keeping the
  // work is the chosen behavior, locked by a test in App.hosted.test.tsx.)
  const handleAuthExpired = React.useCallback(() => {
    setRole(null);
    // setRole(null) only DOES anything hosted, where it drops back to the
    // access-code gate (`hosted && !role`). LOCAL mode has no gate, so every
    // caller that catches AuthError and returns would leave the failure
    // completely invisible -- the button stops spinning and nothing happens.
    // That is reachable for real: relaunching the editor mints a FRESH per-run
    // token while an already-open tab still holds the previous one, so every
    // request 401s (bd polyglot-pdf-cpiw). Surface it once, centrally, so all
    // six catch sites are covered rather than each remembering to.
    if (!hosted) {
      setSaveError(
        'The editor was not accepted by its backend -- its access token is '
        + 'probably from an earlier run. Reload this page to pick up the '
        + 'current one.',
      );
    }
  }, [hosted]);

  // Open a kit from the REMOTE catalogue (hosted mode, bd 92qe.2): pull its
  // schema + PDF through the token-gated routes and drive the same schema +
  // PDFViewer flow the local kit path uses. The save target is the kit id
  // (saveRemoteSchema), not a file handle.
  // Monotonic open token: remote opens take real network time and the cards
  // stay clickable, so kit A's SLOW response must never apply after kit B was
  // opened -- the stale open would overwrite B's schema/kit id and leave the
  // editor on the wrong kit (Codex P1, PR #280). Each open bumps the token;
  // any await that resumes under a newer token abandons silently.
  const openSeqRef = React.useRef(0);

  const handleOpenRemoteKit = React.useCallback(async (entry: RemoteKitEntry) => {
    if (hasUnsavedChanges) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to switch forms?'
      );
      if (!confirmed) return;
    }
    const seq = ++openSeqRef.current;
    setLoading(true);
    setError(null);
    setSaveError(null);
    setSelectedFieldId(null);
    setGroupSelection([]);
    setViewMode('edit');
    resetPerFormReviewUi(); // refusal + review filter are per-form (s18 C1)
    fileHandleRef.current = null; // hosted mode never saves via a file handle
    localEntryRef.current = null;  // hosted reloads go through the remote store
    try {
      const loaded = await loadRemoteSchema(entry.id);
      if (seq !== openSeqRef.current) return; // superseded by a newer open
      if (!loaded) {
        throw new Error(`${entry.label} has no schema yet.`);
      }
      let pdfUrl = '';
      if (entry.hasPdf) {
        pdfUrl = (await loadRemotePdfBlobUrl(entry.id)) ?? '';
      }
      if (seq !== openSeqRef.current) {
        // A newer open won while our PDF was in flight: discard OUR blob URL
        // (nobody will ever render it) and touch nothing else.
        if (pdfUrl) URL.revokeObjectURL(pdfUrl);
        return;
      }
      // Swap the blob URL only now that BOTH fetches succeeded. Revoking the
      // prior kit's URL BEFORE the fetches (the old order) meant any mid-open
      // failure -- especially a 401, whose auth-drop path deliberately
      // preserves the open kit -- left the still-displayed prior kit pointing
      // at a dead URL: a silently broken PDF viewer after re-auth
      // (fresh-eyes r2).
      if (pdfBlobUrlRef.current) URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = pdfUrl || null;

      clearLintMirror(); // a DIFFERENT kit is now open (s18 C1)
      loadSchemaState(loaded); // fresh baseline -> history cleared
      setSelectedForm({ name: entry.label, pdfPath: pdfUrl, schemaPath: entry.schemaFile });
      setSelectedKitId(entry.id);
      setSavedFileName(null); // nothing saved back yet this session
      setSavingToKit(true); // saves target the kit's own remote schema
    } catch (err) {
      if (seq !== openSeqRef.current) return; // a stale open's failure is moot
      if (err instanceof AuthError) {
        handleAuthExpired();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to open form');
      console.error('Failed to open remote kit:', err);
    } finally {
      if (seq === openSeqRef.current) setLoading(false);
    }
  }, [hasUnsavedChanges, loadSchemaState, handleAuthExpired, resetPerFormReviewUi,
      clearLintMirror]);

  // Guard a folder switch: returns false to ABORT when the user declines to
  // discard unsaved edits (same guard handleOpenKit uses, so a folder change can't
  // silently drop dirty work -- Codex P0). Pure check: it must NOT mutate state,
  // because the picker may still be cancelled after this returns true (Codex
  // round 4 -- clearing here would discard the kit for nothing).
  const confirmFolderChange = React.useCallback((): boolean => {
    if (hasUnsavedChanges) {
      return window.confirm(
        'You have unsaved changes. Are you sure you want to switch folders?'
      );
    }
    return true;
  }, [hasUnsavedChanges]);

  // Drop the open-kit state AFTER a new folder is actually chosen, so a same-named
  // kit in the new folder can't inherit the old form's live progress (Codex PR
  // #224). Clears savedFileName too, else the header keeps showing "Saved to <old
  // schema>" with no schema open (Codex round 4).
  const clearOpenKit = React.useCallback((): void => {
    setSelectedKitId(null);
    setSelectedForm(null);
    setSavedFileName(null);
    setSavingToKit(false);
    setSelectedFieldId(null);
    setGroupSelection([]); // merge selection is per-form (bd polyglot-pdf-s4dp.1)
    resetPerFormReviewUi(); // refusal + review filter are per-form (s18 C1)
    clearLintMirror();      // no form open -> no findings
    clearSchema();
    fileHandleRef.current = null;
    localEntryRef.current = null;
    if (pdfBlobUrlRef.current) {
      URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = null;
    }
  }, [clearSchema, resetPerFormReviewUi, clearLintMirror]);

  // Update a field in the schema
  const handleUpdateField = React.useCallback((updatedField: FormField) => {
    if (!schema) return;

    const newSchema = {
      ...schema,
      fields: schema.fields.map(f => (f.id === updatedField.id ? updatedField : f)),
    };

    commitSchema(newSchema);
  }, [schema, commitSchema]);

  // Replace the whole field list (and optionally sections) at once (bd
  // polyglot-pdf-432u, extended by polyglot-pdf-6b7z): used when an edit needs
  // to touch MULTIPLE fields/sections atomically, e.g. retargeting every
  // dependent's (and every section's) show_if/require_if after an
  // option-slug rename -- unlike handleUpdateField, which can only patch the
  // single field being edited. `sections` is optional so callers that only
  // touch fields (no section referenced the renamed slug) can omit it.
  const handleUpdateFields = React.useCallback((fields: FormField[], sections?: FormSection[]) => {
    if (!schema) return;
    commitSchema({ ...schema, fields, ...(sections ? { sections } : {}) });
  }, [schema, commitSchema]);

  // Rename a field's internal id, retargeting every in-schema reference
  // (conditions, section membership, copy_to, supplements) in ONE undoable
  // commit (bd polyglot-pdf-0x10.1). Returns a human-readable block reason,
  // or null on success/no-op. Selection follows the renamed field.
  const handleRenameField = React.useCallback((oldId: string, newId: string): string | null => {
    if (!schema) return 'No schema loaded.';
    const trimmed = newId.trim();
    const reason = renameBlockReason(schema, oldId, trimmed);
    if (reason) return reason;
    if (trimmed === oldId) return null;
    commitSchema(renameFieldId(schema, oldId, trimmed));
    setSelectedFieldId(prev => (prev === oldId ? trimmed : prev));
    return null;
  }, [schema, commitSchema]);

  // Quarantine a field into the _ignored_fields stash (bd polyglot-pdf-mzkw).
  // Structural, so it cannot ride the single-field onUpdateField patch the
  // review dropdown otherwise uses: it rewrites fields[], the section, AND the
  // stash -- committed as ONE schema so a single Cmd+Z reverses it. Returns a
  // human-readable block reason (the caller shows it) or null on success.
  // Selection is dropped: the ignored field leaves fields[], so the editor
  // pane would have nothing to render for it.
  const handleIgnoreField = React.useCallback((fieldId: string): string | null => {
    if (!schema) return 'No schema loaded.';
    const reason = ignoreBlockReason(schema, fieldId);
    if (reason) return describeIgnoreBlock(reason, dependentsOf(schema, fieldId));
    commitSchema(ignoreField(schema, fieldId));
    setSelectedFieldId(prev => (prev === fieldId ? null : prev));
    return null;
  }, [schema, commitSchema]);

  // Un-ignore: restore a quarantined field to its exact former place and
  // select it, so the author lands on what they just brought back.
  const handleRestoreField = React.useCallback((fieldId: string) => {
    if (!schema) return;
    commitSchema(restoreField(schema, fieldId));
    setSelectedFieldId(fieldId);
  }, [schema, commitSchema]);

  // Update form-level metadata (version, edition, OMB, expiration -- bd
  // polyglot-pdf-s4dp.2). Merges the patch into form_metadata so a human can
  // correct an auto-extracted version (or fill one a version-less form lacked).
  const handleUpdateMetadata = React.useCallback((patch: Partial<FormSchema['form_metadata']>) => {
    if (!schema) return;
    commitSchema({
      ...schema,
      form_metadata: { ...schema.form_metadata, ...patch },
    });
  }, [schema, commitSchema]);

  // Reorder fields within a section
  const handleReorderFields = React.useCallback((sectionId: string, fieldIds: string[]) => {
    if (!schema) return;

    const newSections = schema.sections.map(section => {
      if (section.id === sectionId) {
        return { ...section, fields: fieldIds };
      }
      return section;
    });

    commitSchema({ ...schema, sections: newSections });
  }, [schema, commitSchema]);

  // Move option from one field to another
  const handleMoveOption = React.useCallback((sourceFieldId: string, optionIndex: number, targetFieldId: string) => {
    if (!schema) return;

    const sourceField = schema.fields.find(f => f.id === sourceFieldId);
    const targetField = schema.fields.find(f => f.id === targetFieldId);

    if (!sourceField?.options || !targetField || (targetField.type !== 'radio' && targetField.type !== 'checkbox')) {
      return;
    }

    // Get the option being moved
    const optionToMove = sourceField.options[optionIndex];
    if (!optionToMove) return;

    // Remove from source
    const newSourceOptions = sourceField.options.filter((_, idx) => idx !== optionIndex);
    const newSourceWidgets = sourceField.consolidated_widgets?.filter(w => w !== optionToMove.value);

    // Add to target
    const newTargetOptions = [...(targetField.options || []), optionToMove];
    const newTargetWidgets = [...(targetField.consolidated_widgets || []), optionToMove.value];

    // Update both fields
    const newFields = schema.fields.map(f => {
      if (f.id === sourceFieldId) {
        return {
          ...f,
          options: newSourceOptions,
          consolidated_widgets: newSourceWidgets,
        };
      }
      if (f.id === targetFieldId) {
        return {
          ...f,
          options: newTargetOptions,
          consolidated_widgets: newTargetWidgets,
        };
      }
      return f;
    });

    commitSchema({ ...schema, fields: newFields });
  }, [schema, commitSchema]);

  // Toggle a field's membership in the merge selection (bd polyglot-pdf-s4dp.1).
  // Order matters: the first-added field is the merge primary, so we append on
  // add and filter on remove rather than rebuilding the array.
  const toggleGroupSelection = React.useCallback((fieldId: string) => {
    setGroupSelection(prev =>
      prev.includes(fieldId) ? prev.filter(id => id !== fieldId) : [...prev, fieldId]
    );
  }, []);

  const clearGroupSelection = React.useCallback(() => setGroupSelection([]), []);

  // Merge the currently-selected fields into one consolidated options[] field
  // (bd polyglot-pdf-s4dp.1). `kind` chooses checkbox_group (several boxes)
  // vs radio (exactly one) -- bd h76m.10. The first-selected field is the
  // primary whose identity survives; each selected widget's pdf_field_name
  // moves onto its option. Selects the merged field and clears the selection.
  const handleMergeFields = React.useCallback((kind: 'checkbox_group' | 'radio') => {
    if (!schema || groupSelection.length < 2) return;
    const { schema: next, mergedFieldId } = mergeFields(schema, groupSelection, kind);
    if (next === schema) return; // no-op (invalid selection)
    commitSchema(next);
    setSelectedFieldId(mergedFieldId);
    setGroupSelection([]);
  }, [schema, groupSelection, commitSchema]);

  // Un-merge a consolidated field back into one standalone field per option
  // (bd polyglot-pdf-s4dp.1, reverse of handleMergeFields).
  const handleUnmergeField = React.useCallback((fieldId: string) => {
    if (!schema) return;
    const next = ungroupField(schema, fieldId);
    if (next === schema) return; // not un-groupable -- no-op
    commitSchema(next);
    setSelectedFieldId(fieldId); // primary keeps its id
  }, [schema, commitSchema]);

  // Flip an existing consolidated group between checkbox_group (multi-select)
  // and radio (single-select) in place, without an ungroup/re-merge round trip
  // (bd polyglot-pdf-checkbox-radio). Dependents' show_if/require_if are moved
  // across the membership boundary by changeGroupKind. The group keeps its id,
  // so the selection is preserved.
  const handleChangeGroupKind = React.useCallback(
    (fieldId: string, kind: 'checkbox_group' | 'radio') => {
      if (!schema) return;
      const next = changeGroupKind(schema, fieldId, kind);
      if (next === schema) return; // not a group, or already that kind -- no-op
      commitSchema(next);
    },
    [schema, commitSchema],
  );

  // Suggested filename for a fresh save (the form's schema basename, *_edited).
  const suggestedFileName = React.useCallback(() => {
    const filename = selectedForm?.schemaPath.split('/').pop() || 'schema.json';
    return filename.replace('.json', '_edited.json');
  }, [selectedForm]);

  // Save schema. With File System Access support: the FIRST save prompts for a
  // destination, every subsequent save writes straight to that same file (the
  // one-step re-save, bd s1e2). Without it: fall back to the download path.
  // `forcePicker` (Save As) always re-prompts for a new destination.
  // Hosted mode short-circuits both: the save is a PUT to the kit's remote
  // schema (bd 92qe.2), with a visible Saving... state for the round trip.
  const handleSave = React.useCallback(async (forcePicker = false) => {
    if (!schema || !selectedForm) return;

    if (hosted) {
      if (!selectedKitId || saving) return;
      setSaving(true);
      // Snapshot what this save actually sends: the editor stays editable
      // while the PUT is in flight, so completion must only mark the state
      // clean if the schema is STILL the snapshot -- otherwise edits made
      // during the round trip would be flagged saved and lost on unload
      // (Codex P1, PR #280). The still-dirty flag then simply prompts the
      // contractor to save again, which sends the newer payload.
      const snapshot = schema;
      try {
        await saveRemoteSchema(selectedKitId, snapshot);
        if (schemaRef.current === snapshot) {
          setSavedFileName('the shared workspace');
          markSaved();
        }
        setSaveError(null);
      } catch (err) {
        if (err instanceof AuthError) {
          handleAuthExpired();
          return;
        }
        setSaveError(err instanceof Error ? err.message : 'Failed to save schema');
        console.error('Failed to save schema remotely:', err);
      } finally {
        setSaving(false);
      }
      return;
    }

    if (!fsAccess) {
      // Fallback: browsers without the API get the original download behavior.
      // Wrapped like the other three save paths so a thrown failure (e.g.
      // JSON.stringify on a circular schema) surfaces in the saveError banner
      // instead of an unhandled exception (bd polyglot-pdf-gtbw).
      try {
        const name = suggestedFileName();
        saveSchema(schema, name);
        markSaved();
        setSaveError(null);
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : 'Failed to save schema');
        console.error('Failed to save schema:', err);
      }
      return;
    }

    try {
      let handle = fileHandleRef.current;
      if (!handle || forcePicker) {
        handle = await pickSchemaFile(suggestedFileName());
        fileHandleRef.current = handle;
        // A picked destination (Save As) is no longer the kit's own schema, so
        // its progress must not be cached against the kit id (Codex PR #224 r6).
        setSavingToKit(false);
      }
      await writeSchemaToHandle(handle, schema);
      setSavedFileName(handle.name);
      markSaved();
      setSaveError(null);
    } catch (err) {
      if (isUserAbort(err)) return; // human cancelled the picker -- no-op
      setSaveError(err instanceof Error ? err.message : 'Failed to save schema');
      console.error('Failed to save schema:', err);
    }
  }, [schema, selectedForm, fsAccess, suggestedFileName, markSaved,
      hosted, selectedKitId, saving, handleAuthExpired]);

  // Reload the schema FROM the saved file handle (verifies the round-trip: the
  // edit just saved is read back, satisfying criterion 1's "reloads cleanly with
  // the edit present"). Only available once a destination has been chosen.
  const handleReloadFromFile = React.useCallback(async () => {
    const handle = fileHandleRef.current;
    if (!handle) return;
    if (hasUnsavedChanges) {
      const ok = window.confirm(
        'Reload from the saved file? Unsaved changes will be discarded.'
      );
      if (!ok) return;
    }
    try {
      const reloaded = await readSchemaFromHandle(handle);
      // Reset selection before the fresh baseline (bd 6hhc parity): a
      // reloaded file can drop/rename the selected field. The count-guard
      // already backstops this, but keeping every loadSchemaState caller
      // uniform removes the asymmetry the fresh-eyes review flagged.
      setSelectedFieldId(null);
      loadSchemaState(reloaded); // fresh baseline -> history cleared
      setSaveError(null);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to reload schema');
      console.error('Failed to reload schema from file:', err);
    }
  }, [hasUnsavedChanges, loadSchemaState]);

  // Run the same-folder handshake whenever the picked folder changes
  // (bd polyglot-pdf-s2bf). Hosted skips it: kits live in the shared store, so
  // there is no local directory for the two sides to agree on.
  const handleRootChange = React.useCallback(async (dir: FsDirectoryHandle | null) => {
    // Monotonic token, same discipline as openSeqRef / refreshSeq. WITHOUT it
    // this guard can FAIL OPEN: switch from folder A (which agrees) to folder B
    // (a copy) while A's handshake is still in flight, and A's late {ok:true}
    // lands after B's {ok:false} -- leaving the server actions ENABLED while B
    // is on screen, which is the exact wrong-folder write this exists to stop.
    // Nothing else serializes it (the Change-folder button gates on busy /
    // extractingId, neither of which tracks the handshake).
    const seq = ++folderSeqRef.current;
    // Clear FIRST: from the instant a new folder is reported, agreement is
    // unproven, so the actions must be off for the whole in-flight window
    // rather than riding the previous folder's verdict.
    setFolderCheck(null);
    if (hosted || !backendAvailable || !dir) return;
    try {
      const res = await verifySameFolder(dir, verifyStoreFolder);
      if (seq !== folderSeqRef.current) return; // superseded by a newer folder
      setFolderCheck(res);
      // Only NAG on a real mismatch. An unwritable folder is surfaced the same
      // way, since it cannot be the write target either.
      if (!res.ok) setFolderModalOpen(true);
    } catch {
      // The backend could not answer (down, 401). Treat as unproven: the
      // server-side actions stay off, and the lint path already reports the
      // failure -- no second dialog for the same cause.
      if (seq !== folderSeqRef.current) return;
      setFolderCheck(null);
    }
  }, [hosted, backendAvailable]);

  // Server-side actions need BOTH a backend and proof it writes where we read.
  // Hosted has no local folder, so the handshake does not apply there.
  const serverActionsOk = backendAvailable && (hosted || folderCheck?.ok === true);

  // Re-read the open kit's STORED schema after a server-side rewrite (repair,
  // regenerate-divisions, regenerate-guidance). Mode-aware: hosted kits come
  // back through the remote store, local kits are re-read from the picked
  // directory -- the backend wrote the same file on disk, so loadRemoteSchema
  // would 404 there (bd polyglot-pdf-cpiw).
  const reloadStoredSchema = React.useCallback(async (): Promise<FormSchema | null> => {
    if (!hosted) {
      const entry = localEntryRef.current;
      return entry ? await loadKitSchema(entry) : null;
    }
    return selectedKitId ? await loadRemoteSchema(selectedKitId) : null;
  }, [hosted, selectedKitId]);

  // One-click Repair-all (bd polyglot-pdf-zgln, P5.3b): runs the server-side
  // deterministic repair on the kit's STORED schema, then reloads the repaired
  // result. Because it operates on the stored draft, unsaved edits must be saved
  // first (or discarded) -- reloading would otherwise clobber them silently.
  // Needs a backend + author + an open kit; the ValidationPanel gates the button
  // so this is not reached otherwise.
  const handleRepairAll = React.useCallback(async () => {
    if (!serverActionsOk || !selectedKitId) return;
    if (hasUnsavedChanges) {
      const ok = window.confirm(
        'Repair works on the saved version. Save your changes first, or click ' +
        'OK to discard unsaved edits and repair the last-saved schema.'
      );
      if (!ok) return;
    }
    // Stale-open guard (bd polyglot-pdf-r5vp): repair is a multi-second round trip
    // (deterministic repair + store write + reload) and the catalogue stays
    // clickable, so if the author opens a DIFFERENT kit mid-flight, this repair's
    // reload must NOT clobber the newer kit's display -- the same openSeqRef token
    // handleOpenRemoteKit uses (Codex PR #280). Capture it at entry; abandon after
    // any await once a newer open (or repair) supersedes us.
    const seq = ++openSeqRef.current;
    try {
      await repairKit(selectedKitId);
      if (seq !== openSeqRef.current) return; // superseded while repairing
      const repaired = await reloadStoredSchema();
      if (seq !== openSeqRef.current) return; // superseded while reloading
      if (repaired) {
        // Reset selection BEFORE the fresh baseline (parity with every other
        // loadSchemaState caller): repair can drop/rename the selected field,
        // and a stale selectedFieldId must fall back to the metadata panel,
        // not be position-re-pointed to an unrelated field (bd 6hhc
        // fresh-eyes).
        setSelectedFieldId(null);
        loadSchemaState(repaired); // fresh baseline -> history cleared
      }
      setSaveError(null);
    } catch (err) {
      if (seq !== openSeqRef.current) return; // a stale repair's failure is moot
      if (err instanceof AuthError) {
        handleAuthExpired();
        return;
      }
      // Surface the repair failure (e.g. a 422 naming hallucinated widgets) in
      // the same non-blocking banner saves use.
      setSaveError(err instanceof Error ? err.message : 'Failed to repair schema');
      console.error('Failed to repair schema:', err);
    }
  }, [serverActionsOk, selectedKitId, hasUnsavedChanges, loadSchemaState,
      reloadStoredSchema, handleAuthExpired]);

  // Section management (bd polyglot-pdf-6cfu.3): one atomic commit for the
  // {fields, sections, parts} triple a section add/rename/merge/remove
  // produces (sectionOps keeps the three consistent) -- one undo step.
  const handleUpdateDivisions = React.useCallback((patch: DivisionsPatch) => {
    if (!schema) return;
    commitSchema({
      ...schema,
      fields: patch.fields,
      sections: patch.sections,
      ...(patch.parts !== undefined ? { parts: patch.parts } : {}),
    });
  }, [schema, commitSchema]);

  // Regenerate divisions (bd 6cfu.3): re-runs the deterministic derivation on
  // the kit's STORED schema server-side, so it mirrors Repair-all exactly --
  // unsaved-edits confirm, its own destructive confirm, the openSeqRef
  // stale-open guard, reload as a fresh baseline (history cleared).
  const handleRegenerateDivisions = React.useCallback(async () => {
    if (!serverActionsOk || !selectedKitId) return;
    if (hasUnsavedChanges) {
      const ok = window.confirm(
        'Regenerate works on the saved version. Save your changes first, or ' +
        'click OK to discard unsaved edits and regenerate from the last-saved '
        + 'schema.'
      );
      if (!ok) return;
    }
    const ok = window.confirm(
      'Recompute all sections and parts from the PDF? This overwrites every '
      + 'manual division edit (sections, ordering, field filing). Field '
      + 'content is untouched.'
    );
    if (!ok) return;
    const seq = ++openSeqRef.current;
    try {
      await regenerateDivisions(selectedKitId);
      if (seq !== openSeqRef.current) return; // superseded while deriving
      const derived = await reloadStoredSchema();
      if (seq !== openSeqRef.current) return; // superseded while reloading
      if (derived) {
        // Reset selection before the fresh baseline (bd 6hhc fresh-eyes):
        // regenerate-divisions re-files fields and can change the selected
        // id, so a stale selection must deselect, not re-point by position.
        setSelectedFieldId(null);
        loadSchemaState(derived); // fresh baseline -> history cleared
      }
      setSaveError(null);
    } catch (err) {
      if (seq !== openSeqRef.current) return;
      if (err instanceof AuthError) {
        handleAuthExpired();
        return;
      }
      setSaveError(err instanceof Error ? err.message : 'Failed to regenerate divisions');
      console.error('Failed to regenerate divisions:', err);
    }
  }, [serverActionsOk, selectedKitId, hasUnsavedChanges, loadSchemaState,
      reloadStoredSchema, handleAuthExpired]);

  // Re-author ONE field's guidance from the form's instruction booklet (bd
  // polyglot-pdf-cpiw) -- the costly half of the staleness gate, which had no
  // implementation, so "re-author it" meant hand-copying prose out of the IRS
  // booklet. Server-side (it rewrites the STORED schema), so it follows the
  // same shape as repair: unsaved edits must be settled first, then reload.
  //
  // Throws on failure rather than swallowing: the button renders the message
  // inline, next to the gate it belongs to.
  const handleRegenerateGuidance = React.useCallback(async (fieldId: string) => {
    if (!serverActionsOk || !selectedKitId) return false;
    if (hasUnsavedChanges) {
      const ok = window.confirm(
        'Rewriting works on the saved version. Save your changes first, or '
        + 'click OK to discard unsaved edits and rewrite from the last-saved '
        + 'schema.'
      );
      if (!ok) return false;
    }
    const seq = ++openSeqRef.current;
    try {
      const report = await regenerateGuidance(selectedKitId, [fieldId]);
      if (seq !== openSeqRef.current) return false; // superseded while rewriting
      const fresh = await reloadStoredSchema();
      if (seq !== openSeqRef.current) return false; // superseded while reloading
      if (fresh) loadSchemaState(fresh); // fresh baseline -> history cleared
      setSaveError(null);
      // The route reports what it actually WROTE, not what it proposed: a
      // hand-edited field is deliberately never clobbered, and a judge outage
      // writes nothing. Hand that back so the button can say so.
      return (report.regenerated || []).includes(fieldId);
    } catch (err) {
      if (seq !== openSeqRef.current) return false;
      if (err instanceof AuthError) {
        handleAuthExpired();
        // LOCAL has no access-code gate to fall back to (App renders it on
        // `hosted && !role`), so swallowing this would leave the button
        // looking successful. Rethrow and let it render the message.
        if (hosted) return false;
      }
      throw err; // surfaced inline by the button
    }
  }, [serverActionsOk, selectedKitId, hasUnsavedChanges, loadSchemaState,
      reloadStoredSchema, handleAuthExpired]);

  // Fetch the open kit's unclaimed PDF button widgets for the FieldEditor's
  // "Add from PDF widgets" picker (bd polyglot-pdf-nivy, P5.3c). Hosted + an open
  // kit only; passed to the editor solely in author mode (see below), so a
  // missing kit id here just yields nothing.
  const handleLoadUnclaimedWidgets = React.useCallback(async () => {
    if (!selectedKitId) return [];
    try {
      return await loadUnclaimedWidgets(selectedKitId);
    } catch (err) {
      if (err instanceof AuthError) {
        handleAuthExpired();
        return [];
      }
      throw err; // the picker surfaces the message inline
    }
  }, [selectedKitId, handleAuthExpired]);

  // Get selected field
  const selectedField = React.useMemo(() => {
    if (!schema || !selectedFieldId) return null;
    return schema.fields.find(f => f.id === selectedFieldId) || null;
  }, [schema, selectedFieldId]);

  // Re-point selection when the selected id vanishes from the schema
  // (bd polyglot-pdf-6hhc nit 2). Selection is deliberately NOT part of the
  // undo/redo history (same as merge/ungroup), so undoing a field-id RENAME
  // leaves selectedFieldId holding the now-absent NEW id, dropping the editor
  // back to the metadata panel. A rename keeps the field at its position, so
  // re-select the field now occupying the index the vanished selection held --
  // recovering the exact field the author was editing (under its restored id).
  //
  // Guards (the third is the load-safety gate, bd 6hhc fresh-eyes):
  //  - a field WAS selected and its id truly vanished (a deliberate deselect
  //    sets selectedFieldId=null, which short-circuits and clears the ref);
  //  - the old index still exists in the new field list;
  //  - the field COUNT is unchanged. A rename is the only mutation that
  //    changes a field's id while keeping the count and position; a
  //    structural RELOAD (Repair-all, Regenerate-divisions, extraction) or a
  //    delete changes the count, so it deselects rather than re-pointing to
  //    an unrelated field at the reused index. Reload handlers ALSO null the
  //    selection before loadSchemaState (parity with the other callers), so
  //    this gate is belt-and-suspenders against a future forgetful caller.
  const prevSelectedIndexRef = React.useRef<number | null>(null);
  const prevFieldCountRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (!schema) {
      prevSelectedIndexRef.current = null;
      prevFieldCountRef.current = null;
      return;
    }
    const count = schema.fields.length;
    const prevCount = prevFieldCountRef.current;
    prevFieldCountRef.current = count;
    const idx = selectedFieldId
      ? schema.fields.findIndex(f => f.id === selectedFieldId)
      : -1;
    if (idx >= 0) {
      // Selection still resolves -- remember its position for a later vanish.
      prevSelectedIndexRef.current = idx;
      return;
    }
    if (!selectedFieldId) {
      // Deliberate deselect -- forget the last position so a subsequent
      // schema change can never resurrect a stale selection.
      prevSelectedIndexRef.current = null;
      return;
    }
    // Selected id no longer resolves. Recover ONLY on an in-place rename
    // (same field count) whose slot still exists -- otherwise deselect
    // (recoverSelectionAfterVanish encodes that decision + is unit-tested).
    const recovered = recoverSelectionAfterVanish(
      schema.fields, prevSelectedIndexRef.current, prevCount);
    if (recovered !== null) {
      setSelectedFieldId(recovered);
    } else {
      prevSelectedIndexRef.current = null;
    }
  }, [schema, selectedFieldId]);

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      // Cmd/Ctrl + S to save; + Shift for Save As (new destination)
      if (e.key === 's') {
        e.preventDefault();
        void handleSave(e.shiftKey);
        return;
      }
      // Cmd/Ctrl + Z = undo; Cmd/Ctrl + Shift + Z (or Cmd/Ctrl + Y) = redo
      if (e.key === 'z' || e.key === 'Z') {
        e.preventDefault();
        if (e.shiftKey) redo(); else undo();
        return;
      }
      if (e.key === 'y' || e.key === 'Y') {
        e.preventDefault();
        redo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSave, undo, redo]);

  // Revoke the PDF blob URL on unmount (bd b0pe -- avoid leaking object URLs).
  React.useEffect(() => () => {
    if (pdfBlobUrlRef.current) URL.revokeObjectURL(pdfBlobUrlRef.current);
  }, []);

  // First-run guide: hosted contractors get the in-app guided-help overlay
  // once per browser, after the access code validates (bd 92qe.5). The Help
  // button reopens it any time (in local mode too); only this auto-open is
  // hosted-only.
  React.useEffect(() => {
    if (hosted && role && !hasSeenGuide()) setGuideOpen(true);
  }, [hosted, role]);

  // Warn on page unload if unsaved changes
  React.useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasUnsavedChanges]);

  // Hosted mode's front gate: no catalogue traffic until the access code
  // validates (bd 92qe.2). onReady carries the role (editor vs author).
  if (hosted && !role) {
    return <AccessCodeGate onReady={setRole} />;
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        {/* bd tynm: tighter padding -- header pixels come out of the editor. */}
        <div className="flex items-center justify-between px-4 py-2">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold text-gray-900">
              📄 PDF Schema Editor
            </h1>
            {saving ? (
              <span className="text-sm text-blue-600 font-medium">
                Saving...
              </span>
            ) : hasUnsavedChanges ? (
              <span className="text-sm text-yellow-600 font-medium">
                • Unsaved changes
              </span>
            ) : savedFileName ? (
              <span className="text-sm text-green-600 font-medium">
                Saved to {savedFileName}
              </span>
            ) : null}
          </div>
          <div className="flex gap-2">
            <button
              className="btn btn-secondary"
              onClick={() => setGuideOpen(true)}
              title="Open the help and guide"
            >
              Help
            </button>
            <button
              className="btn btn-secondary"
              onClick={undo}
              disabled={!canUndo}
              title="Undo (Cmd+Z)"
            >
              Undo
            </button>
            <button
              className="btn btn-secondary"
              onClick={redo}
              disabled={!canRedo}
              title="Redo (Cmd+Shift+Z)"
            >
              Redo
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => window.location.reload()}
              disabled={!schema}
            >
              Reset
            </button>
            {!hosted && fsAccess && savedFileName && (
              <button
                className="btn btn-secondary"
                onClick={() => void handleReloadFromFile()}
                disabled={!schema}
                title={`Reload the schema from ${savedFileName}`}
              >
                Reload from file
              </button>
            )}
            {!hosted && fsAccess && (
              <button
                className="btn btn-secondary"
                onClick={() => void handleSave(true)}
                disabled={!schema}
                title="Choose a new destination file (Cmd+Shift+S)"
              >
                Save As...
              </button>
            )}
            <button
              className="btn btn-primary"
              onClick={() => void handleSave(false)}
              disabled={!schema || !hasUnsavedChanges || saving}
              title={hosted
                ? 'Save back to the shared workspace (Cmd+S)'
                : fsAccess
                  ? (fileHandleRef.current
                      ? 'Save to the chosen file (Cmd+S)'
                      : 'Choose a destination and save (Cmd+S)')
                  : 'Download edited schema (Cmd+S)'}
            >
              {saving ? 'Saving...' : hosted || fsAccess ? 'Save (Cmd+S)' : 'Download (Cmd+S)'}
            </button>
          </div>
        </div>

        {/* The front door. Hosted mode (bd 92qe.2): the remote catalogue over
            the token-gated editor routes. Local mode: the directory-based
            catalogue (bd b0pe), with the hardcoded FormSelector as a fallback
            for browsers without the directory API. */}
        {hosted && role ? (
          <RemoteCatalogue
            onOpenKit={(entry) => void handleOpenRemoteKit(entry)}
            selectedKitId={selectedKitId}
            role={role}
            onAuthError={handleAuthExpired}
            // A Mark-complete refusal is homed on the strip's refusal line
            // beside the counts it contradicts (sprint-18 C1, decision 1).
            onStatusRefusal={setPublishRefusal}
            liveProgress={
              selectedKitId && schema
                ? { kitId: selectedKitId, saved: !hasUnsavedChanges && savingToKit, ...liveStats(schema, lintFindings) }
                : null
            }
          />
        ) : (
          <FormCatalogue
            onOpenKit={handleOpenKit}
            confirmFolderChange={confirmFolderChange}
            clearOpenKit={clearOpenKit}
            onRootChange={handleRootChange}
            // Same refusal home as the hosted catalogue (sprint-18 C1).
            onStatusRefusal={setPublishRefusal}
            // Lets Mark-complete run the server's publish gates + translation
            // drift sweep instead of writing metadata.json blind (bd rh5v).
            serverActionsOk={serverActionsOk}
            selectedKitId={selectedKitId}
            liveProgress={
              // Keep the open kit's catalogue bar in sync with in-editor edits:
              // the disk-scanned % is stale after an edit/save, so feed the live
              // in-memory stats (same reviewCounts predicate the strip shows).
              // `saved` lets the catalogue cache only persisted values: an UNSAVED
              // edit still shows live on the open card, but is not remembered after
              // the kit closes (else a discarded edit would leave phantom progress).
              selectedKitId && schema
                ? { kitId: selectedKitId, saved: !hasUnsavedChanges && savingToKit, ...liveStats(schema, lintFindings) }
                : null
            }
          />
        )}
        {!hosted && !dirAccess && (
          <FormSelector selectedForm={selectedForm} onSelectForm={handleSelectForm} />
        )}
      </header>

      {/* Non-blocking save/reload failure banner: the editor (and the unsaved
          work) stays fully alive underneath (bd 92qe.5). */}
      {saveError && (
        <div
          role="alert"
          className="bg-red-50 border-b border-red-200 px-4 py-2 flex items-center gap-3"
        >
          <svg
            className="w-4 h-4 text-red-600 shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="text-sm text-red-800 flex-1">{saveError}</span>
          <button
            type="button"
            onClick={() => setSaveError(null)}
            aria-label="Dismiss save error"
            className="text-red-400 hover:text-red-600 shrink-0"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      )}

      {guideOpen && <HostedGuide role={role} onClose={() => setGuideOpen(false)} />}

      {/* Section management (bd polyglot-pdf-6cfu.3) */}
      {/* Same-folder guard (bd polyglot-pdf-s2bf). The editor reads and writes
          the folder the human picked; the backend resolves kit ids against its
          OWN root. If they differ, Repair / Regenerate would rewrite a
          DIFFERENT copy than the one on screen -- so they are disabled and this
          explains why, with the fix. */}
      {folderModalOpen && folderCheck && !folderCheck.ok && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="folder-guard-title"
        >
          <div className="max-w-lg rounded-lg bg-white p-5 shadow-xl">
            <h2 id="folder-guard-title" className="text-lg font-semibold text-gray-900">
              {folderCheck.reason === 'unwritable'
                ? 'This folder cannot be written to'
                : 'This folder is not the one the server uses'}
            </h2>
            <div className="mt-3 space-y-3 text-sm text-gray-700">
              {folderCheck.reason === 'unwritable' ? (
                <p>
                  The editor could not write to the folder you opened, so it
                  cannot save your changes there.
                </p>
              ) : (
                <>
                  <p>
                    You opened a form-kits folder that the server does not use,
                    so the two would work on different copies: your edits would
                    save to the folder you picked, while Repair and Regenerate
                    would quietly rewrite the server's copy instead.
                  </p>
                  {folderCheck.backendRoot && (
                    <p className="rounded bg-gray-50 p-2 font-mono text-xs break-all">
                      The server uses: {folderCheck.backendRoot}
                    </p>
                  )}
                </>
              )}
              <p className="font-medium text-gray-900">
                {folderCheck.reason === 'unwritable'
                  ? 'Make a copy of this folder somewhere you can write to, and open the copy instead.'
                  : 'Open the folder shown above, or make a copy of it and point the server at the copy.'}
              </p>
              <p className="text-xs text-gray-500">
                You can keep reviewing and saving to the folder you opened.
                What is switched off is anything that goes through the server:
                Repair all, Regenerate divisions, Rewrite guidance, and the
                &ldquo;Add from PDF widgets&rdquo; picker (it reads the
                server&rsquo;s copy of the PDF, so its answers would describe
                the wrong form).
              </p>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                className="btn-sm btn-primary"
                data-testid="folder-guard-dismiss"
                onClick={() => setFolderModalOpen(false)}
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}

      {showSectionManager && schema && (
        <SectionManager
          fields={schema.fields}
          sections={schema.sections}
          parts={schema.parts}
          canRegenerate={serverActionsOk && (!hosted || role === 'author') && !!selectedKitId}
          onApply={handleUpdateDivisions}
          onRegenerate={handleRegenerateDivisions}
          onClose={() => setShowSectionManager(false)}
        />
      )}

      {/* Main Content */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin w-12 h-12 border-4 border-primary-500 border-t-transparent rounded-full mx-auto mb-4" />
            <p className="text-gray-600">Loading schema...</p>
          </div>
        </div>
      )}

      {error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <svg
              className="w-16 h-16 text-red-500 mx-auto mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Error</h2>
            <p className="text-gray-600 mb-4">{error}</p>
            <button
              className="btn btn-primary"
              onClick={() => {
                setError(null);
                clearSchema();
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {!loading && !error && !schema && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <svg
              className="w-24 h-24 text-gray-300 mx-auto mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <h2 className="text-2xl font-semibold text-gray-900 mb-2">
              Welcome to PDF Schema Editor
            </h2>
            <p className="text-gray-600 mb-6">
              {hosted
                ? 'Pick a form from the shared catalogue above to start reviewing.'
                : 'Open your form-kits folder above to see the catalogue, or drop an ' +
                  'AcroForm PDF to add a new form -- then pick a form to start editing.'}
            </p>
            <div className="text-left bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h3 className="font-semibold text-blue-900 mb-2">Quick Guide:</h3>
              <ul className="text-sm text-blue-800 space-y-1">
                {hosted ? (
                  <>
                    <li>- Pick a form from the catalogue to load it</li>
                    <li>- Click fields in the list or PDF viewer; edit in the right panel</li>
                    <li>- Yellow/red fields need attention; green fields are done</li>
                    <li>- Undo/redo with Cmd+Z / Cmd+Shift+Z; Cmd+S saves back to the workspace</li>
                    <li>- When every field looks right, click Mark complete on its card</li>
                  </>
                ) : (
                  <>
                    <li>- Open your form-kits/ folder, or drop a PDF to onboard a new form</li>
                    <li>- Pick a form from the catalogue to load it</li>
                    <li>- Click fields in the list or PDF viewer; edit in the right panel</li>
                    <li>- Undo/redo with Cmd+Z / Cmd+Shift+Z</li>
                    <li>- Press Cmd+S to save (Cmd+Shift+S to save to a new file)</li>
                  </>
                )}
              </ul>
            </div>
          </div>
        </div>
      )}

      {schema && selectedForm && !loading && !error && (
        <div className="flex-1 flex overflow-hidden">
          {/* Left: PDF Viewer */}
          <div className="w-2/5 border-r border-gray-200">
            <PDFViewer
              pdfPath={selectedForm.pdfPath}
              schema={schema}
              selectedFieldId={selectedFieldId}
              onSelectField={setSelectedFieldId}
              onPageCountChange={setPdfPageCount}
              // Same findings the FieldList reads, so the canvas overlay and
              // the row agree on every field (bd polyglot-pdf-l7u0).
              lintFindingsByField={lintFindingsByField}
            />
          </div>

          {/* Middle: Field List */}
          <div className="w-1/5 border-r border-gray-200 flex flex-col">
            <div className="p-3 bg-white border-b border-gray-200 flex items-start justify-between gap-2">
              <div>
                <h3 className="font-semibold text-gray-900">Fields</h3>
                <p className="text-xs text-gray-500">
                  {schema.fields.length} total
                </p>
              </div>
              <button
                className="shrink-0 text-xs px-2 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                onClick={() => setShowSectionManager(true)}
                title="Add, rename, merge or remove sections"
              >
                Sections
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <FieldList
                // Remount per form (same idiom as PreviewPane): the list's
                // local state -- search, section expansion, the Form row's
                // expand/collapse -- is per-form, and a survived collapse
                // latch hid the NEXT kit's blocking form ERROR behind an
                // unopened chevron (Opus outer review, pass 1).
                key={selectedKitId ?? selectedForm.schemaPath}
                schema={schema}
                selectedFieldId={selectedFieldId}
                onSelectField={setSelectedFieldId}
                onDeselect={() => setSelectedFieldId(null)}
                onReorderFields={handleReorderFields}
                onMoveOption={handleMoveOption}
                groupSelection={groupSelection}
                onToggleGroupSelection={toggleGroupSelection}
                onClearGroupSelection={clearGroupSelection}
                onMergeFields={handleMergeFields}
                lintFindingsByField={lintFindingsByField}
                pageCount={pdfPageCount}
                onRestoreField={handleRestoreField}
                formFindings={formFindings}
                onDismissFormFinding={handleDismissFormFinding}
                reviewFilterActive={reviewFilterActive}
                onClearReviewFilter={() => setReviewFilterActive(false)}
              />
            </div>
          </div>

          {/* Right: Field Editor OR interactive Preview (bd s4dp.4) */}
          <div className="w-2/5 flex flex-col">
            <div className="p-3 bg-white border-b border-gray-200 flex items-center justify-between gap-2">
              <h3 className="font-semibold text-gray-900">
                {viewMode === 'preview'
                  ? 'Preview'
                  : selectedFieldId ? 'Field Properties' : 'Form Metadata'}
              </h3>
              <div className="flex items-center gap-2">
                {/* When a field is selected the metadata panel is otherwise
                    unreachable (it shows only with no selection); this clears the
                    selection to get back to it (Codex PR #263). */}
                {viewMode === 'edit' && selectedFieldId && (
                  <button
                    className="btn-sm btn-secondary"
                    onClick={() => setSelectedFieldId(null)}
                    title="Edit form-level metadata (version, OMB, expiration)"
                  >
                    Form metadata
                  </button>
                )}
                {/* Edit / Preview view toggle. Preview is a standalone interactive
                    render of the form's logic (no voice app), letting the author
                    test radio exclusivity, checkbox multi-select, and show_if. */}
                <div className="flex rounded-md overflow-hidden border border-gray-300">
                  <button
                    className={`btn-sm ${viewMode === 'edit' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setViewMode('edit')}
                    title="Edit field properties"
                  >
                    Edit
                  </button>
                  <button
                    className={`btn-sm ${viewMode === 'preview' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setViewMode('preview')}
                    title="Interactively preview the form's logic"
                  >
                    Preview
                  </button>
                </div>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              {viewMode === 'preview' ? (
                // Key by the loaded form so the pane REMOUNTS (clearing its local
                // preview values) when the form changes -- otherwise stale values
                // from the prior form leak into the new one's show_if evaluation
                // (fresh-eyes finding 4).
                <PreviewPane key={selectedKitId ?? selectedForm.schemaPath} schema={schema} />
              ) : (
                <FieldEditor
                  field={selectedField}
                  schema={schema}
                  lintFindings={
                    selectedField
                      ? lintFindingsByField.get(selectedField.id)
                      : undefined
                  }
                  pageCount={pdfPageCount}
                  onIgnoreField={handleIgnoreField}
                  ignoreBlocked={(() => {
                    if (!selectedField) return null;
                    const reason = ignoreBlockReason(schema, selectedField.id);
                    return reason
                      ? describeIgnoreBlock(reason, dependentsOf(schema, selectedField.id))
                      : null;
                  })()}
                  onUpdateField={handleUpdateField}
                  onRenameField={handleRenameField}
                  onUnmergeField={handleUnmergeField}
                  onChangeGroupKind={handleChangeGroupKind}
                  onUpdateMetadata={handleUpdateMetadata}
                  onUpdateFields={handleUpdateFields}
                  authorTier={!hosted || role === 'author'}
                  // The "Add from PDF widgets" picker (bd nivy) needs a backend
                  // (the callback fetches that kit's unclaimed widgets from the
                  // AcroForm dump) + author tier + an open kit. Local dev with
                  // the backend up now qualifies (bd polyglot-pdf-cpiw).
                  onLoadUnclaimedWidgets={
                    serverActionsOk && (!hosted || role === 'author') && selectedKitId
                      ? handleLoadUnclaimedWidgets
                      : undefined
                  }
                  // Re-author guidance from the booklet (bd polyglot-pdf-cpiw).
                  // Same gating as the other server-side author actions; the
                  // button only renders inside the staleness banner anyway.
                  onRegenerateGuidance={
                    serverActionsOk && (!hosted || role === 'author') && selectedKitId
                      ? handleRegenerateGuidance
                      : undefined
                  }
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Bottom: the one-truth strip (sprint-18 C1). It owns the lint
          round-trip (kit-scoped when a kit is open, so the strip lints with
          the same dump-loaded inputs as the publish gate) and the single
          count line; findings themselves render at their fields. */}
      {schema && (
        <ValidationPanel
          // Remount per form: the strip's last lint REPORT is per-form state
          // (keep-last-report-on-blip is for a transient failure on the SAME
          // form, never for carrying form A's findings across a switch --
          // Opus outer review, pass 1).
          key={selectedKitId ?? selectedForm?.schemaPath ?? 'no-form'}
          schema={schema}
          // Kit-scope the lint only when server actions are trusted for this
          // kit (hosted, or a local folder that passed the same-folder
          // handshake) -- a mismatched local folder must not pull ANOTHER
          // copy's AcroForm dump into this schema's findings.
          kitId={serverActionsOk && selectedKitId ? selectedKitId : undefined}
          onJumpToReview={handleJumpToReview}
          onToggleReviewFilter={() => setReviewFilterActive(v => !v)}
          reviewFilterActive={reviewFilterActive}
          refusal={publishRefusal}
          onDismissRefusal={() => setPublishRefusal(null)}
          onSelectField={(fieldId) => {
            // A finding can point at a field that is now QUARANTINED (bd mzkw)
            // -- lint flags persisted before it was ignored still name it. The
            // editor pane has nothing to render for such an id, so clicking
            // would silently fall back to the metadata panel with no
            // explanation (fresh-eyes). Say so instead.
            if (schema && isIgnored(schema, fieldId)) {
              window.alert(
                `"${fieldId}" is currently ignored (set aside, not deleted), so `
                + 'it has no editor pane. Un-ignore it from the Ignored list at '
                + 'the bottom of the field list to work on it again.',
              );
              return;
            }
            setViewMode('edit');
            setSelectedFieldId(fieldId);
          }}
          onAuthError={handleAuthExpired}
          onReport={handleLintReport}
          // Repair-all is author-tier on an open kit with a backend (bd zgln);
          // the panel additionally shows the button only when errors exist.
          onRepairAll={
            serverActionsOk && (!hosted || role === 'author') && selectedKitId
              ? handleRepairAll
              : undefined
          }
        />
      )}
    </div>
  );
};
