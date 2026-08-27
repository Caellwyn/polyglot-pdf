/**
 * The CLIENT-side per-form "Archived versions" disclosure
 * (bd polyglot-pdf-qfyxr).
 *
 * Lives in the post-selection header -- NOT in the onboarding modal: that
 * flow exists to pick a form to FILL, and surfacing superseded revisions
 * mid-selection is exactly the current-vs-archived confusion the bead's
 * exit criterion 3 forbids. Here, a firm user already on a form can open
 * its history (organized by form, then chronological -- the maintainer's
 * requirement), and the viewer is unmistakably read-only: amber, labeled,
 * no inputs, no fill affordances.
 *
 * Fetches through the authenticated backend routes
 * (/api/form-kits/{id}/archive...) with the Firebase Bearer token -- the
 * archive is deliberately absent from the static bundle, and a private
 * kit's history carries the kit's own firm-visibility gates server-side.
 */
import { resolveSessionToken } from "../../shared/sessionCredential";
import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { resolveKitAssetUrl } from "../utils/pdfFiller";
import type { FormSchema } from "../types/schema";

export interface ArchivedRevisionEntry {
  marker: string;
  published_at: string | null;
}

function formatStamp(iso: string | null): string {
  if (!iso) return "date unknown";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

export function ArchivedVersionsLink({ kitId, kitLabel }: { kitId: string; kitLabel: string }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<ArchivedRevisionEntry[] | null>(null);
  const [viewing, setViewing] = useState<{
    marker: string;
    published_at: string | null;
    schema: FormSchema | null;
  } | null>(null);

  const authedGet = async (path: string) => {
    const token = await resolveSessionToken(user);
    return fetch(resolveKitAssetUrl(path), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  };

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && revisions === null && !loading) {
      setLoading(true);
      setError(null);
      try {
        const resp = await authedGet(`/api/form-kits/${encodeURIComponent(kitId)}/archive`);
        if (!resp.ok) throw new Error(`Could not load archived versions (${resp.status})`);
        const body = (await resp.json()) as { revisions?: ArchivedRevisionEntry[] };
        setRevisions(Array.isArray(body.revisions) ? body.revisions : []);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    }
  };

  const view = async (rev: ArchivedRevisionEntry) => {
    setError(null);
    try {
      const resp = await authedGet(
        `/api/form-kits/${encodeURIComponent(kitId)}/archive/${encodeURIComponent(rev.marker)}/schema`,
      );
      if (resp.status === 404) {
        // Same register as the editor sibling: an explicit in-viewer
        // message, not a banner -- the revision was listed a moment ago
        // and has since gone (qfyxr fresh-eyes: the two viewers diverged).
        setViewing({ marker: rev.marker, published_at: rev.published_at, schema: null });
        return;
      }
      if (!resp.ok) throw new Error(`Could not load that archived version (${resp.status})`);
      const schema = (await resp.json()) as FormSchema;
      setViewing({ marker: rev.marker, published_at: rev.published_at, schema });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <span style={{ marginLeft: 12 }}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        style={{
          background: "none",
          border: "none",
          color: "#666",
          textDecoration: "underline dotted",
          cursor: "pointer",
          fontSize: 12,
        }}
      >
        {open ? "Hide archived versions" : "Archived versions"}
      </button>
      {open && (
        <span style={{ marginLeft: 8, fontSize: 12 }}>
          {loading && <span style={{ color: "#999" }}>Loading…</span>}
          {error && <span style={{ color: "#b00" }}>{error}</span>}
          {revisions !== null && revisions.length === 0 && !loading && (
            <span style={{ color: "#999" }}>No archived versions.</span>
          )}
          {revisions !== null && revisions.length > 0 &&
            revisions.map((rev) => (
              <button
                key={rev.marker}
                type="button"
                onClick={() => view(rev)}
                style={{
                  background: "none",
                  border: "none",
                  color: "#1d4ed8",
                  cursor: "pointer",
                  fontSize: 12,
                  marginRight: 8,
                  textDecoration: "underline",
                }}
              >
                {rev.marker} ({formatStamp(rev.published_at)})
              </button>
            ))}
        </span>
      )}
      {viewing && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Archived version of ${kitLabel} — read only`}
          onMouseDown={(e) => { if (e.target === e.currentTarget) setViewing(null); }}
          style={{
            position: "fixed", inset: 0, zIndex: 50,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(0,0,0,0.4)", padding: 16,
          }}
        >
          <div
            style={{
              maxHeight: "85vh", width: "100%", maxWidth: 640,
              display: "flex", flexDirection: "column",
              background: "#fffbeb", borderRadius: 8, padding: 20,
              boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
            }}
          >
            <h2 style={{ margin: 0, fontSize: 16, color: "#78350f" }}>
              Archived version of {kitLabel} — read only
            </h2>
            <p style={{ fontSize: 12, color: "#92400e" }}>
              Revision {viewing.marker}, published {formatStamp(viewing.published_at)}.
              This older version is kept for the record. It cannot be filled or
              edited — the current version is the form behind this window.
            </p>
            {viewing.schema === null && (
              <p style={{ fontSize: 13, color: "#78350f" }}>
                This archived version could not be found (it may have been removed).
              </p>
            )}
            {viewing.schema && (
              <div style={{ minHeight: 0, flex: 1, overflow: "auto", fontSize: 12, color: "#78350f" }}>
                <div>
                  {viewing.schema.form_metadata?.title ?? kitLabel}
                  {" — "}
                  {viewing.schema.sections?.length ?? 0} section(s),{" "}
                  {viewing.schema.fields?.length ?? 0} field(s)
                </div>
                <ul style={{ marginTop: 8, paddingLeft: 18 }}>
                  {(viewing.schema.sections ?? []).map((s: any) => (
                    <li key={s.id ?? s.title}>{s.title ?? s.id}</li>
                  ))}
                </ul>
              </div>
            )}
            <div style={{ marginTop: 12, textAlign: "right" }}>
              <button
                type="button"
                onClick={() => setViewing(null)}
                style={{
                  background: "#fde68a", border: "none", borderRadius: 4,
                  padding: "6px 14px", cursor: "pointer", color: "#78350f",
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </span>
  );
}
