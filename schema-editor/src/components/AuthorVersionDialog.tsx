/**
 * Asks the author to name the revision when publishing a form that has NO
 * government edition date (bd polyglot-pdf-xzw5).
 *
 * WHY THIS EXISTS: a confirmation record has to pin WHICH revision of the form
 * the client agreed to. An official form carries the agency's own marker
 * ("12/2024"). A firm's own intake sheet has none, so without this the record
 * falls back to a content fingerprint (`sha256:1a2b...`) -- stable, but
 * meaningless to the human reading it back in the dispute it exists for.
 *
 * WHY IT IS SHOWN AT MARK-COMPLETE: that is the last moment before the schema
 * freezes. Deploy only copies bytes, and the voice session reads the marker out
 * of the schema it was served, so a version supplied later would never reach
 * the records it was meant to identify. (bd polyglot-pdf-hqztg adds an author
 * approval round between the editor's mark-complete and release; this dialog
 * MOVES there when it lands -- naming a revision is an accountability
 * statement, so it belongs with the accountable party rather than a
 * subcontractor editor.)
 *
 * The value is IMMUTABLE once published -- it is what existing confirmation
 * records name -- so this dialog only ever appears for a kit that has none.
 */
import React from 'react';

/** Today as yyyy-mm-dd in the AUTHOR's local timezone. Deliberately not
 * toISOString(), which converts to UTC first and shows "tomorrow" to anyone
 * east of Greenwich after their local afternoon. */
export function todayIsoLocal(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Mirror of the backend's normalization (editor_kit_routes, the publish gate):
 * trim, and strip a leading v/V ONLY when a digit follows -- so "v2" becomes
 * "2" while "version-3" is left alone. Applied here too so the author sees the
 * value that will actually be stored, rather than discovering the difference
 * after publishing. */
export function normalizeAuthorVersion(raw: string): string {
  return raw.trim().replace(/^[vV](?=[0-9])/, '').trim();
}

export interface AuthorVersionDialogProps {
  kitLabel: string;
  /** The version this kit carried before, when there is one -- shown so the
   * next entry is an obvious increment rather than a guess. */
  previousVersion?: string | null;
  onConfirm: (version: string) => void;
  onCancel: () => void;
  busy?: boolean;
}

export function AuthorVersionDialog({
  kitLabel, previousVersion, onConfirm, onCancel, busy = false,
}: AuthorVersionDialogProps) {
  const [value, setValue] = React.useState(todayIsoLocal);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => { inputRef.current?.select(); }, []);

  const normalized = normalizeAuthorVersion(value);
  const valid = normalized.length > 0;

  const submit = () => { if (valid && !busy) onConfirm(normalized); };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="author-version-title"
      // Click the backdrop to cancel, but not a click that started inside the
      // card and drifted out (text selection).
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}
    >
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h2 id="author-version-title" className="text-base font-semibold text-slate-900">
          Name this version of {kitLabel}
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          This form has no government edition date, so nothing identifies which
          revision a client agreed to. Give it a version and every confirmation
          from now on records that instead of an unreadable fingerprint.
        </p>

        <label className="mt-4 block text-xs font-medium text-slate-700" htmlFor="author-version-input">
          Version
        </label>
        <input
          id="author-version-input"
          ref={inputRef}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
          value={value}
          disabled={busy}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); submit(); }
            if (e.key === 'Escape' && !busy) { e.preventDefault(); onCancel(); }
          }}
        />

        {previousVersion ? (
          <p className="mt-1 text-xs text-slate-500">
            Previous version: <span className="font-mono">{previousVersion}</span>
          </p>
        ) : null}
        {normalized && normalized !== value.trim() ? (
          <p className="mt-1 text-xs text-slate-500">
            Will be saved as <span className="font-mono">{normalized}</span>
          </p>
        ) : null}
        {!valid ? (
          <p className="mt-1 text-xs text-amber-700">
            A version is required to publish a form with no edition date.
          </p>
        ) : null}

        <p className="mt-3 text-xs text-slate-500">
          You cannot change this later -- it is what the confirmation records
          will name. A new revision gets a new version.
        </p>

        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-sm" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn-sm btn-primary"
            onClick={submit}
            disabled={!valid || busy}
          >
            {/* 'Save version & publish' rather than 'Publish': the card
                button behind this dialog now also says Publish (bd
                polyglot-pdf-hqztg), and two identical labels on screen at
                once is ambiguous to a person, not only to a test query. */}
            {busy ? 'Publishing...' : 'Save version & publish'}
          </button>
        </div>
      </div>
    </div>
  );
}
