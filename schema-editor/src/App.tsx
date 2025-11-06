import React from 'react';
import { FormSelector } from './components/FormSelector';
import { PDFViewer } from './components/PDFViewer';
import { FieldList } from './components/FieldList';
import { FieldEditor } from './components/FieldEditor';
import { ValidationPanel } from './components/ValidationPanel';
import { loadSchema, saveSchema } from './utils/schemaLoader';
import type { FormSchema, FormField, FormConfig } from './types/schema';

export const App: React.FC = () => {
  const [selectedForm, setSelectedForm] = React.useState<FormConfig | null>(null);
  const [schema, setSchema] = React.useState<FormSchema | null>(null);
  const [selectedFieldId, setSelectedFieldId] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = React.useState(false);

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

    try {
      const loadedSchema = await loadSchema(form.schemaPath);
      setSchema(loadedSchema);
      setSelectedForm(form);
      setHasUnsavedChanges(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schema');
      console.error('Failed to load schema:', err);
    } finally {
      setLoading(false);
    }
  }, [hasUnsavedChanges]);

  // Update a field in the schema
  const handleUpdateField = React.useCallback((updatedField: FormField) => {
    if (!schema) return;

    const newSchema = {
      ...schema,
      fields: schema.fields.map(f => (f.id === updatedField.id ? updatedField : f)),
    };

    setSchema(newSchema);
    setHasUnsavedChanges(true);
  }, [schema]);

  // Reorder fields within a section
  const handleReorderFields = React.useCallback((sectionId: string, fieldIds: string[]) => {
    if (!schema) return;

    const newSections = schema.sections.map(section => {
      if (section.id === sectionId) {
        return { ...section, fields: fieldIds };
      }
      return section;
    });

    setSchema({ ...schema, sections: newSections });
    setHasUnsavedChanges(true);
  }, [schema]);

  // Save schema
  const handleSave = React.useCallback(() => {
    if (!schema || !selectedForm) return;

    const filename = selectedForm.schemaPath.split('/').pop() || 'schema.json';
    const newFilename = filename.replace('.json', '_edited.json');

    saveSchema(schema, newFilename);
    setHasUnsavedChanges(false);

    alert(`Schema saved as ${newFilename}`);
  }, [schema, selectedForm]);

  // Get selected field
  const selectedField = React.useMemo(() => {
    if (!schema || !selectedFieldId) return null;
    return schema.fields.find(f => f.id === selectedFieldId) || null;
  }, [schema, selectedFieldId]);

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + S to save
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSave]);

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
            {hasUnsavedChanges && (
              <span className="text-sm text-yellow-600 font-medium">
                • Unsaved changes
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              className="btn btn-secondary"
              onClick={() => window.location.reload()}
              disabled={!schema}
            >
              Reset
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={!schema || !hasUnsavedChanges}
            >
              Save Schema (Cmd+S)
            </button>
          </div>
        </div>

        <FormSelector selectedForm={selectedForm} onSelectForm={handleSelectForm} />
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
                setSchema(null);
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
              Select a form from the dropdown above to start editing its schema
            </p>
            <div className="text-left bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h3 className="font-semibold text-blue-900 mb-2">Quick Guide:</h3>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>• Select a PDF form to load</li>
                <li>• Click fields in the list or PDF viewer</li>
                <li>• Edit properties in the right panel</li>
                <li>• Changes save automatically</li>
                <li>• Press Cmd+S to download edited schema</li>
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
