/**
 * Per-form "Archived versions" disclosure + read-only revision viewer
 * (bd polyglot-pdf-qfyxr).
 *
 * MAINTAINER REQUIREMENT (2026-08-06): one version per form at the top layer;
 * older versions hidden under an "archived versions" menu SPECIFIC TO THAT
 * FORM, chronological by release date. So this renders collapsed by default,
 * fetches lazily on first expand (an all-current catalogue never pays the
 * archive round-trips), and lists newest-first (the backend sorts).
 *
 * The viewer is deliberately READ-ONLY and visually unlike the editor: an
 * archived revision is what old confirmation records name -- there is no
 * write route behind this, and the UI must not look editable (exit criterion
 * 3: cannot be confused with the current revision). Returning to an old
 * revision goes through the normal draft/publish flow, never the archive.
 *
 * Both catalogues (RemoteCatalogue + FormCatalogue) mount this same leaf with
 * injected fetchers -- the catalogues stay deliberate siblings, but a leaf
 * dialog duplicated twice is drift with no compensating benefit.
 */
import React from 'react';
import type { FormSchema } from '../types/schema';
import type { ArchivedRevision } from '../utils/remoteKitStore';

export interface ArchivedVersionsProps {
  kitId: string;
  kitLabel: string;
  listRevisions: (kitId: string) => Promise<ArchivedRevision[]>;
  loadSchema: (kitId: string, marker: string) => Promise<FormSchema | null>;
}

function formatStamp(iso: string | null): string {
  if (!iso) return 'date unknown';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

export function ArchivedVersions({
  kitId, kitLabel, listRevisions, loadSchema,
}: ArchivedVersionsProps) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [revisions, setRevisions] = React.useState<ArchivedRevision[] | null>(null);
  const [viewing, setViewing] = React.useState<{
    marker: string; published_at: string | null; schema: FormSchema | null;
  } | null>(null);
  const [viewError, setViewError] = React.useState<string | null>(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && revisions === null && !loading) {
      setLoading(true);
      setError(null);
      try {
        setRevisions(await listRevisions(kitId));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    }
  };

  const view = async (rev: ArchivedRevision) => {
    setViewError(null);
    try {
      const schema = await loadSchema(kitId, rev.marker);
      setViewing({ marker: rev.marker, published_at: rev.published_at, schema });
    } catch (e) {
      setViewError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="mt-2 border-t border-gray-100 pt-2">
      <button
        type="button"
        onClick={toggle}
        className="text-xs text-gray-500 hover:text-gray-700 underline decoration-dotted"
        aria-expanded={open}
      >
        {open ? 'Hide archived versions' : 'Archived versions'}
      </button>
      {open && (
        <div className="mt-1">
          {loading && <div className="text-xs text-gray-400">Loading…</div>}
          {error && <div className="text-xs text-red-600">{error}</div>}
          {revisions !== null && revisions.length === 0 && !loading && (
            <div className="text-xs text-gray-400">No archived versions.</div>
          )}
          {revisions !== null && revisions.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {revisions.map((rev) => (
                <li key={rev.marker}>
                  <button
                    type="button"
                    onClick={() => view(rev)}
                    className="text-xs text-blue-700 hover:underline"
                  >
                    {rev.marker}
                  </button>
                  <span className="ml-2 text-xs text-gray-400">
                    published {formatStamp(rev.published_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {viewError && <div className="text-xs text-red-600">{viewError}</div>}
        </div>
      )}

      {viewing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="archived-revision-title"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setViewing(null); }}
        >
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg bg-amber-50 p-5 shadow-xl">
            <h2 id="archived-revision-title" className="text-base font-semibold text-amber-900">
              Archived version of {kitLabel} — read only
            </h2>
            <p className="mt-1 text-xs text-amber-800">
              Revision {viewing.marker}, published {formatStamp(viewing.published_at)}.
              This superseded version is kept for the audit record and cannot be
              edited or filled. The current version lives on the form card.
            </p>
            {viewing.schema === null ? (
              <p className="mt-3 text-sm text-amber-900">
                This revision could not be found (it may have been removed).
              </p>
            ) : (
              <div className="mt-3 min-h-0 flex-1 overflow-auto">
                <div className="text-xs text-amber-900">
                  {viewing.schema.form_metadata?.title ?? kitLabel}
                  {' — '}
                  {viewing.schema.sections?.length ?? 0} section(s),{' '}
                  {viewing.schema.fields?.length ?? 0} field(s)
                </div>
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-amber-800">
                    Schema JSON (read-only)
                  </summary>
                  <pre className="mt-1 max-h-96 overflow-auto rounded bg-white p-2 text-[11px] leading-tight text-gray-800">
                    {JSON.stringify(viewing.schema, null, 2)}
                  </pre>
                </details>
              </div>
            )}
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setViewing(null)}
                className="rounded bg-amber-200 px-3 py-1 text-sm text-amber-900 hover:bg-amber-300"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
