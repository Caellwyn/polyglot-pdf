/**
 * Confirms permanent deletion of a form kit (bd polyglot-pdf-6x1j).
 *
 * The author must TYPE the kit id. Not a flourish: a Yes/No dialog is answered
 * reflexively, and this action is unrecoverable and takes the revision archive
 * with it. Typing the id forces the author to look at WHICH form they are
 * deleting, which is the mistake that actually happens -- deleting the right
 * thing by accident is rare; deleting the wrong row is not.
 *
 * The dialog does NOT decide whether deletion is allowed. The server does, and
 * it refuses both when confirmation records name the kit and when it cannot
 * verify whether they do. This is the last stop before that call, not the gate.
 */
import React from 'react';

export interface DeleteKitDialogProps {
  kitId: string;
  kitLabel: string;
  /** True while the delete request is in flight. */
  busy?: boolean;
  /** A server refusal to show in place (409 from the guard), if any. */
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteKitDialog({
  kitId, kitLabel, busy = false, error = null, onConfirm, onCancel,
}: DeleteKitDialogProps) {
  const [typed, setTyped] = React.useState('');
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => { inputRef.current?.focus(); }, []);

  // Exact match, trimmed. Deliberately NOT case-insensitive or fuzzy: the
  // point is to make the author read the id, and a forgiving match undoes that.
  const matches = typed.trim() === kitId;
  const confirm = () => { if (matches && !busy) onConfirm(); };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-kit-title"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}
    >
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h2 id="delete-kit-title" className="text-base font-semibold text-red-800">
          Delete {kitLabel} permanently?
        </h2>

        <p className="mt-2 text-sm text-slate-600">
          This removes the form, its PDF, and every archived version of it. It
          cannot be undone. If anyone has already filled this form, deletion
          will be refused -- unpublish it instead, which hides it from clients
          and keeps every file.
        </p>

        <label className="mt-4 block text-xs font-medium text-slate-700" htmlFor="delete-kit-input">
          Type <span className="font-mono font-semibold">{kitId}</span> to confirm
        </label>
        <input
          id="delete-kit-input"
          ref={inputRef}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 font-mono text-sm"
          value={typed}
          disabled={busy}
          autoComplete="off"
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); confirm(); }
            if (e.key === 'Escape' && !busy) { e.preventDefault(); onCancel(); }
          }}
        />

        {error ? (
          // A server refusal renders HERE rather than dismissing the dialog:
          // the 409 explains why this form cannot be deleted, and the author
          // needs to read it next to the thing they were trying to delete.
          <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-800">{error}</p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-sm" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn-sm bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
            onClick={confirm}
            disabled={!matches || busy}
            title={matches ? 'Delete this form permanently' : 'Type the form id to enable'}
          >
            {busy ? 'Deleting...' : 'Delete permanently'}
          </button>
        </div>
      </div>
    </div>
  );
}
