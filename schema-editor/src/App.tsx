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
  type FsFileHandle,
} from './utils/fileSystemAccess';
import { loadKitSchema, versionInfoFromSchema, type CatalogueEntry, type KitVersionInfo } from './utils/formKitDirectory';
import {
  AuthError,
  isHostedMode,
  loadRemotePdfBlobUrl,
  loadRemoteSchema,
  loadUnclaimedWidgets,
  regenerateDivisions,
  repairKit,
  saveRemoteSchema,
  type EditorRole,
  type LintFinding,
  type LintReport,
  type RemoteKitEntry,
} from './utils/remoteKitStore';
import { getCompletionStats } from './utils/validation';
import { mergeFields, ungroupField, changeGroupKind } from './utils/fieldGrouping';
import { renameBlockReason, renameFieldId } from './utils/fieldRename';
import { SectionManager } from './components/SectionManager';
import type { DivisionsPatch } from './utils/sectionOps';
import { useSchemaHistory } from './hooks/useSchemaHistory';
import type { FormField, FormConfig, FormSchema, FormSection } from './types/schema';

// Live review stats for the open kit's catalogue bar (percent + the matching
// complete/total counts, so the bar AND its hover detail both track edits).
// Also carries the live version summary so an in-session metadata edit refreshes
// the card's version line instead of showing the stale disk-scan value (Codex
// PR #263).
function liveStats(
  schema: FormSchema,
): { percent: number; complete: number; total: number; version: KitVersionInfo } {
  const s = getCompletionStats(schema);
  return {
    percent: s.percentage, complete: s.complete, total: s.total,
    version: versionInfoFromSchema(schema),
  };
}

export const App: React.FC = () => {
  // Hosted delivery mode (bd polyglot-pdf-92qe.2): kits come from the backend's
  // token-gated /api/editor routes (the shared store) instead of a local
  // folder. `role` is null until the access code validates (the gate screen);
  // author-only affordances (onboard/extract, bd 92qe.3) key off it later.
  const hosted = React.useMemo(isHostedMode, []);
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
  const lintFindingsByField = React.useMemo(() => {
    const map = new Map<string, LintFinding[]>();
    for (const f of lintFindings) {
      if (!f.field_id) continue;
      const bucket = map.get(f.field_id);
      if (bucket) bucket.push(f);
      else map.set(f.field_id, [f]);
    }
    return map;
  }, [lintFindings]);
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
    // A new form means a new destination -- drop the prior file handle so the
    // next save prompts for where to put THIS form's schema.
    fileHandleRef.current = null;
    setSavedFileName(null);
    setSelectedKitId(null); // leaving catalogue mode
    if (pdfBlobUrlRef.current) {
      URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = null;
    }

    try {
      const loadedSchema = await loadSchema(form.schemaPath);
      loadSchemaState(loadedSchema); // fresh baseline -> history cleared
      setSelectedForm(form);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schema');
      console.error('Failed to load schema:', err);
    } finally {
      setLoading(false);
    }
  }, [hasUnsavedChanges, loadSchemaState]);

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
    try {
      const loaded = await loadKitSchema(entry);
      if (!loaded) {
        throw new Error(`${entry.label} has no schema yet -- run the extraction first.`);
      }
      // Save target = the kit's own schema.json handle (in-place save).
      fileHandleRef.current = await entry.dirHandle.getFileHandle(entry.schemaFile);
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
  }, [hasUnsavedChanges, loadSchemaState]);

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
  }, []);

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
    fileHandleRef.current = null; // hosted mode never saves via a file handle
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
  }, [hasUnsavedChanges, loadSchemaState, handleAuthExpired]);

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
    clearSchema();
    fileHandleRef.current = null;
    if (pdfBlobUrlRef.current) {
      URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = null;
    }
  }, [clearSchema]);

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
      loadSchemaState(reloaded); // fresh baseline -> history cleared
      setSaveError(null);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to reload schema');
      console.error('Failed to reload schema from file:', err);
    }
  }, [hasUnsavedChanges, loadSchemaState]);

  // One-click Repair-all (bd polyglot-pdf-zgln, P5.3b): runs the server-side
  // deterministic repair on the kit's STORED schema, then reloads the repaired
  // result. Because it operates on the stored draft, unsaved edits must be saved
  // first (or discarded) -- reloading would otherwise clobber them silently.
  // Hosted + author + an open kit only; the ValidationPanel gates the button so
  // this is not reached otherwise.
  const handleRepairAll = React.useCallback(async () => {
    if (!hosted || !selectedKitId) return;
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
      const repaired = await loadRemoteSchema(selectedKitId);
      if (seq !== openSeqRef.current) return; // superseded while reloading
      if (repaired) loadSchemaState(repaired); // fresh baseline -> history cleared
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
  }, [hosted, selectedKitId, hasUnsavedChanges, loadSchemaState, handleAuthExpired]);

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
    if (!hosted || !selectedKitId) return;
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
      const derived = await loadRemoteSchema(selectedKitId);
      if (seq !== openSeqRef.current) return; // superseded while reloading
      if (derived) loadSchemaState(derived); // fresh baseline -> history cleared
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
  }, [hosted, selectedKitId, hasUnsavedChanges, loadSchemaState, handleAuthExpired]);

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
            liveProgress={
              selectedKitId && schema
                ? { kitId: selectedKitId, saved: !hasUnsavedChanges && savingToKit, ...liveStats(schema) }
                : null
            }
          />
        ) : (
          <FormCatalogue
            onOpenKit={handleOpenKit}
            confirmFolderChange={confirmFolderChange}
            clearOpenKit={clearOpenKit}
            selectedKitId={selectedKitId}
            liveProgress={
              // Keep the open kit's catalogue bar in sync with in-editor edits:
              // the disk-scanned % is stale after an edit/save, so feed the live
              // in-memory stats (same getCompletionStats the ValidationPanel uses).
              // `saved` lets the catalogue cache only persisted values: an UNSAVED
              // edit still shows live on the open card, but is not remembered after
              // the kit closes (else a discarded edit would leave phantom progress).
              selectedKitId && schema
                ? { kitId: selectedKitId, saved: !hasUnsavedChanges && savingToKit, ...liveStats(schema) }
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
      {showSectionManager && schema && (
        <SectionManager
          fields={schema.fields}
          sections={schema.sections}
          parts={schema.parts}
          canRegenerate={hosted && role === 'author' && !!selectedKitId}
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
                  onUpdateField={handleUpdateField}
                  onRenameField={handleRenameField}
                  onUnmergeField={handleUnmergeField}
                  onChangeGroupKind={handleChangeGroupKind}
                  onUpdateMetadata={handleUpdateMetadata}
                  onUpdateFields={handleUpdateFields}
                  authorTier={!hosted || role === 'author'}
                  // The "Add from PDF widgets" picker (bd nivy) is hosted
                  // author-tier on an open kit only -- the callback fetches that
                  // kit's unclaimed widgets; absent otherwise (no backend dump).
                  onLoadUnclaimedWidgets={
                    hosted && role === 'author' && selectedKitId
                      ? handleLoadUnclaimedWidgets
                      : undefined
                  }
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Bottom: Validation Panel. Findings come from the backend's single
          Python linter (bd h76m.11); clicking a field-anchored finding focuses
          that field (and, in preview mode, drops back to edit so the selection
          is visible). */}
      {schema && (
        <ValidationPanel
          schema={schema}
          onSelectField={(fieldId) => {
            setViewMode('edit');
            setSelectedFieldId(fieldId);
          }}
          onAuthError={handleAuthExpired}
          onReport={handleLintReport}
          // Repair-all is author-tier on an open hosted kit only (bd zgln); the
          // panel additionally shows the button only when errors exist.
          onRepairAll={
            hosted && role === 'author' && selectedKitId
              ? handleRepairAll
              : undefined
          }
        />
      )}
    </div>
  );
};
