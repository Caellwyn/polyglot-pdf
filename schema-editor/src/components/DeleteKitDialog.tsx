/**
 * Confirms permanent deletion of a form kit (bd polyglot-pdf-6x1j).
 *
 * The author must TYPE the kit id. Not a flourish: a Yes/No dialog is answered
 * reflexively, and this action is unrecoverable and takes the revision archive
 * with it. Typing the id forces the author to look at WHICH form they are
 * deleting, which is the mistake that actually happens -- deleting the right
 * thing by accident is rare; deleting the wrong row is not.
 *
 * The dialog does NOT decide whether deletion is allowed -- the server does,
 * and it also decides how firmly to ask. A risky delete comes back as a WARNING
 * to confirm, never a dead end (bd polyglot-pdf-6zhaf): a form nobody can ever
 * delete is its own bug, and the practical cost is a store filling with junk.
 * The escalated step carries the SERVER's wording, which names what is at risk
 * for this specific kit.
 */
import React from 'react';
import type { DeleteEscalation } from '../utils/remoteKitStore';

export interface DeleteKitDialogProps {
  kitId: string;
  kitLabel: string;
  /** True while the delete request is in flight. */
  busy?: boolean;
  /** A genuine failure to show in place (a 502, a broken store), if any. */
  error?: string | null;
  /** The server asked for confirmation rather than refusing. `text` is its own
   * wording; `escalation` is how hard it wants to be asked. */
  warning?: { text: string; escalation: DeleteEscalation } | null;
  /** Re-issue the delete WITH the acknowledgement. */
  onAcknowledge?: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteKitDialog({
  kitId, kitLabel, busy = false, error = null, warning = null,
  onAcknowledge, onConfirm, onCancel,
}: DeleteKitDialogProps) {
  const [typed, setTyped] = React.useState('');
  // The SECOND confirmation for an ever-live form. Deliberately a separate,
  // unchecked-by-default step rather than a second sentence in the same
  // paragraph: the point is a distinct decision, not more text to skim past.
  const [understood, setUnderstood] = React.useState(false);
  // A fresh warning must not inherit a tick from a previous attempt.
  React.useEffect(() => { setUnderstood(false); }, [warning?.text]);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => { inputRef.current?.focus(); }, []);

  // Exact match, trimmed. Deliberately NOT case-insensitive or fuzzy: the
  // point is to make the author read the id, and a forgiving match undoes that.
  const matches = typed.trim() === kitId;
  const confirm = () => { if (matches && !busy) onConfirm(); };
  // A single-ack warning needs only the (already satisfied) typed id; a
  // double-ack additionally needs the explicit tick. Derived once so the button
  // and its tooltip cannot disagree about when it is allowed.
  const ackReady = warning
    ? (warning.escalation === 'double-ack' ? understood : true)
    : false;

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
          cannot be undone. If anyone has already filled this form -- or if that
          cannot be checked -- you will be asked to confirm again before it goes
          ahead. Unpublishing instead hides it from clients and keeps every
          file.
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
          // A genuine failure renders HERE rather than dismissing the dialog,
          // next to the thing the author was trying to delete.
          <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-800">{error}</p>
        ) : null}

        {warning ? (
          // The server's OWN words. It names what is at risk for this kit --
          // whether records exist, or merely could not be checked -- which a
          // generic client-side warning cannot do.
          <div
            className={`mt-3 rounded p-2 text-xs ${
              warning.escalation === 'double-ack'
                ? 'border border-red-300 bg-red-50 text-red-900'
                : 'bg-amber-50 text-amber-900'
            }`}
            data-testid={`delete-warning-${warning.escalation}`}
            role="alert"
          >
            <p className="font-semibold">
              {warning.escalation === 'double-ack'
                ? 'This form has been published'
                : 'Check before deleting'}
            </p>
            <p className="mt-1">{warning.text}</p>

            {warning.escalation === 'double-ack' ? (
              // A SECOND, separate decision for an ever-live form -- not more
              // prose in the same block. Unticked by default, and the button
              // stays disabled until it is ticked.
              <label className="mt-2 flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={understood}
                  disabled={busy}
                  onChange={(e) => setUnderstood(e.target.checked)}
                  data-testid="delete-understood"
                />
                <span>
                  I understand this permanently destroys the form revision those
                  agreement records point to.
                </span>
              </label>
            ) : null}
          </div>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-sm" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          {warning ? (
            <button
              className="btn-sm bg-red-700 text-white hover:bg-red-800 disabled:opacity-50"
              onClick={() => { if (!busy && ackReady) onAcknowledge?.(); }}
              disabled={!ackReady || busy}
              title={
                ackReady
                  ? 'Delete this form anyway'
                  : 'Tick the box to confirm you understand'
              }
              data-testid="delete-anyway"
            >
              {busy ? 'Deleting...' : 'Delete anyway'}
            </button>
          ) : (
            <button
              className="btn-sm bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
              onClick={confirm}
              disabled={!matches || busy}
              title={matches ? 'Delete this form permanently' : 'Type the form id to enable'}
            >
              {busy ? 'Deleting...' : 'Delete permanently'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
