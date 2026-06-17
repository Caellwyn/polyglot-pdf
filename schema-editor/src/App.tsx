import React from 'react';
import { FormSelector } from './components/FormSelector';
import { FormCatalogue } from './components/FormCatalogue';
import { PDFViewer } from './components/PDFViewer';
import { FieldList } from './components/FieldList';
import { FieldEditor } from './components/FieldEditor';
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
import { loadKitSchema, type CatalogueEntry } from './utils/formKitDirectory';
import { getCompletionStats } from './utils/validation';
import { useSchemaHistory } from './hooks/useSchemaHistory';
import type { FormField, FormConfig, FormSchema } from './types/schema';

// Live review stats for the open kit's catalogue bar (percent + the matching
// complete/total counts, so the bar AND its hover detail both track edits).
function liveStats(schema: FormSchema): { percent: number; complete: number; total: number } {
  const s = getCompletionStats(schema);
  return { percent: s.percentage, complete: s.complete, total: s.total };
}

export const App: React.FC = () => {
  const [selectedForm, setSelectedForm] = React.useState<FormConfig | null>(null);
  // Schema + undo/redo history (bd v3y8). `commit` is a user edit, `load` a
  // fresh load, `markSaved` clears the dirty flag, `clear` drops the schema.
  const {
    schema, isDirty: hasUnsavedChanges, canUndo, canRedo,
    commit: commitSchema, load: loadSchemaState, markSaved, clear: clearSchema,
    undo, redo,
  } = useSchemaHistory();
  const [selectedFieldId, setSelectedFieldId] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
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
    setSelectedFieldId(null);
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
    setSelectedFieldId(null);
    try {
      const loaded = await loadKitSchema(entry);
      if (!loaded) {
        throw new Error(`${entry.label} has no schema yet -- run the extraction first.`);
      }
      // Save target = the kit's own schema.json handle (in-place save).
      fileHandleRef.current = await entry.dirHandle.getFileHandle(entry.schemaFile);
      setSavedFileName(entry.schemaFile);

      // Build a blob URL for the PDF so PDFViewer (which takes a URL) can render
      // it; revoke any prior one to avoid leaking object URLs.
      if (pdfBlobUrlRef.current) URL.revokeObjectURL(pdfBlobUrlRef.current);
      let pdfUrl = '';
      if (entry.hasPdf) {
        const pdfHandle = await entry.dirHandle.getFileHandle(entry.pdfFile);
        const pdfFile = await pdfHandle.getFile();
        pdfUrl = URL.createObjectURL(pdfFile);
        pdfBlobUrlRef.current = pdfUrl;
      } else {
        pdfBlobUrlRef.current = null;
      }

      loadSchemaState(loaded); // fresh baseline -> history cleared
      setSelectedForm({ name: entry.label, pdfPath: pdfUrl, schemaPath: entry.schemaFile });
      setSelectedKitId(entry.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open form');
      console.error('Failed to open kit:', err);
    } finally {
      setLoading(false);
    }
  }, [hasUnsavedChanges, loadSchemaState]);

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

  // Suggested filename for a fresh save (the form's schema basename, *_edited).
  const suggestedFileName = React.useCallback(() => {
    const filename = selectedForm?.schemaPath.split('/').pop() || 'schema.json';
    return filename.replace('.json', '_edited.json');
  }, [selectedForm]);

  // Save schema. With File System Access support: the FIRST save prompts for a
  // destination, every subsequent save writes straight to that same file (the
  // one-step re-save, bd s1e2). Without it: fall back to the download path.
  // `forcePicker` (Save As) always re-prompts for a new destination.
  const handleSave = React.useCallback(async (forcePicker = false) => {
    if (!schema || !selectedForm) return;

    if (!fsAccess) {
      // Fallback: browsers without the API get the original download behavior.
      const name = suggestedFileName();
      saveSchema(schema, name);
      markSaved();
      setError(null);
      return;
    }

    try {
      let handle = fileHandleRef.current;
      if (!handle || forcePicker) {
        handle = await pickSchemaFile(suggestedFileName());
        fileHandleRef.current = handle;
      }
      await writeSchemaToHandle(handle, schema);
      setSavedFileName(handle.name);
      markSaved();
      setError(null);
    } catch (err) {
      if (isUserAbort(err)) return; // human cancelled the picker -- no-op
      setError(err instanceof Error ? err.message : 'Failed to save schema');
      console.error('Failed to save schema:', err);
    }
  }, [schema, selectedForm, fsAccess, suggestedFileName, markSaved]);

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
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reload schema');
      console.error('Failed to reload schema from file:', err);
    }
  }, [hasUnsavedChanges, loadSchemaState]);

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

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold text-gray-900">
              📄 PDF Schema Editor
            </h1>
            {hasUnsavedChanges ? (
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
            {fsAccess && savedFileName && (
              <button
                className="btn btn-secondary"
                onClick={() => void handleReloadFromFile()}
                disabled={!schema}
                title={`Reload the schema from ${savedFileName}`}
              >
                Reload from file
              </button>
            )}
            {fsAccess && (
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
              disabled={!schema || !hasUnsavedChanges}
              title={fsAccess
                ? (fileHandleRef.current
                    ? 'Save to the chosen file (Cmd+S)'
                    : 'Choose a destination and save (Cmd+S)')
                : 'Download edited schema (Cmd+S)'}
            >
              {fsAccess ? 'Save (Cmd+S)' : 'Download (Cmd+S)'}
            </button>
          </div>
        </div>

        {/* The catalogue (directory-based) is the front door (bd b0pe); the
            hardcoded FormSelector remains as a fallback for browsers without the
            directory API (where the catalogue shows its unsupported message). */}
        <FormCatalogue
          onOpenKit={handleOpenKit}
          confirmFolderChange={confirmFolderChange}
          clearOpenKit={clearOpenKit}
          selectedKitId={selectedKitId}
          liveProgress={
            // Keep the open kit's catalogue bar in sync with in-editor edits:
            // the disk-scanned % is stale after an edit/save, so feed the live
            // in-memory stats (same getCompletionStats the ValidationPanel uses).
            selectedKitId && schema
              ? { kitId: selectedKitId, ...liveStats(schema) }
              : null
          }
        />
        {!dirAccess && (
          <FormSelector selectedForm={selectedForm} onSelectForm={handleSelectForm} />
        )}
      </header>

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
              Open your form-kits folder above to see the catalogue, or drop an
              AcroForm PDF to add a new form -- then pick a form to start editing.
            </p>
            <div className="text-left bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h3 className="font-semibold text-blue-900 mb-2">Quick Guide:</h3>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>- Open your form-kits/ folder, or drop a PDF to onboard a new form</li>
                <li>- Pick a form from the catalogue to load it</li>
                <li>- Click fields in the list or PDF viewer; edit in the right panel</li>
                <li>- Undo/redo with Cmd+Z / Cmd+Shift+Z</li>
                <li>- Press Cmd+S to save (Cmd+Shift+S to save to a new file)</li>
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
            <div className="p-3 bg-white border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Fields</h3>
              <p className="text-xs text-gray-500">
                {schema.fields.length} total
              </p>
            </div>
            <div className="flex-1 overflow-hidden">
              <FieldList
                schema={schema}
                selectedFieldId={selectedFieldId}
                onSelectField={setSelectedFieldId}
                onReorderFields={handleReorderFields}
                onMoveOption={handleMoveOption}
              />
            </div>
          </div>

          {/* Right: Field Editor */}
          <div className="w-2/5 flex flex-col">
            <div className="p-3 bg-white border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Field Properties</h3>
            </div>
            <div className="flex-1 overflow-hidden">
              <FieldEditor
                field={selectedField}
                schema={schema}
                onUpdateField={handleUpdateField}
              />
            </div>
          </div>
        </div>
      )}

      {/* Bottom: Validation Panel */}
      {schema && (
        <ValidationPanel schema={schema} />
      )}
    </div>
  );
};
