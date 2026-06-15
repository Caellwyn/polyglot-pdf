import React from 'react';
import {
  isDirectoryAccessSupported, pickDirectory, isUserAbort,
  type FsDirectoryHandle,
} from '../utils/fileSystemAccess';
import { listKits, onboardPdf, type CatalogueEntry } from '../utils/formKitDirectory';

interface FormCatalogueProps {
  /** Called when the human opens a kit for editing. */
  onOpenKit: (entry: CatalogueEntry) => void;
  /** The currently-open kit id (to highlight it in the list). */
  selectedKitId: string | null;
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
  onOpenKit, selectedKitId,
}) => {
  const supported = React.useMemo(isDirectoryAccessSupported, []);
  const [root, setRoot] = React.useState<FsDirectoryHandle | null>(null);
  const [kits, setKits] = React.useState<CatalogueEntry[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [dragOver, setDragOver] = React.useState(false);

  const refresh = React.useCallback(async (dir: FsDirectoryHandle) => {
    setBusy(true);
    setError(null);
    try {
      setKits(await listKits(dir));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read folder');
    } finally {
      setBusy(false);
    }
  }, []);

  const handlePickFolder = React.useCallback(async () => {
    try {
      const dir = await pickDirectory();
      setRoot(dir);
      await refresh(dir);
    } catch (err) {
      if (isUserAbort(err)) return;
      setError(err instanceof Error ? err.message : 'Failed to open folder');
    }
  }, [refresh]);

  const handleDrop = React.useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
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
    setNotice(null);
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

      {root && kits.length > 0 && (
        <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {kits.map((kit) => (
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
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
