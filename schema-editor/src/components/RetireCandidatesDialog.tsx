import { useState } from 'react';
import type { RetireCandidate } from '../utils/remoteKitStore';

/**
 * Offers the older revisions this publish might replace (bd polyglot-pdf-bdedm).
 *
 * MAINTAINER DECISION, 2026-08-07: "The publish modal lists other live kits it
 * thinks are the same form and asks the author to tick which to retire. System
 * does the finding; the human makes the call." Auto-retire was explicitly NOT
 * chosen, because the only available same-form signals are unreliable --
 * form_number is not unique (a standard W-7 and a firm's own W-7 variant share
 * it) and the label is free text. A wrong guess would retire another firm's
 * live form.
 *
 * Two rules follow from that and are not negotiable:
 *
 *  1. NOTHING IS PRE-CHECKED. A pre-checked destructive default is an
 *     auto-retire wearing a confirmation's clothes.
 *  2. Publishing WITHOUT ticking anything is a first-class outcome, not a
 *     cancel -- the author may simply be adding a form, and the suggestion may
 *     be wrong.
 *
 * Single-select, because the backend contract takes ONE replaces_kit_id (bd
 * polyglot-pdf-6dz0). Radio-style rather than checkboxes: offering several
 * boxes and sending one would silently drop the others.
 */
export function RetireCandidatesDialog({
  kitLabel,
  candidates,
  busy,
  onPublish,
  onCancel,
}: {
  kitLabel: string;
  candidates: RetireCandidate[];
  busy?: boolean;
  /** `replaces` is undefined when the author ticked nothing. */
  onPublish: (replaces?: string) => void;
  onCancel: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  return (
    // The SAME classes DeleteKitDialog and AuthorVersionDialog use. My first
    // version invented `modal-backdrop`/`modal-card`, which exist in no
    // stylesheet -- so this rendered as an unstyled inline block with no
    // overlay, no centring and no card. Every test passed because JSDOM
    // applies no CSS at all (Opus fresh-eyes round 3).
    //
    // The overlay is not decoration: it is what stops the catalogue's Publish
    // buttons being clickable while this destructive confirmation is open.
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Retire an older version"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}
    >
      <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <h2 className="text-base font-semibold">Publish "{kitLabel}"</h2>

        <p className="mt-2 text-sm text-slate-700">
          {candidates.length === 1
            ? 'This form looks like a newer version of one that is already live:'
            : 'This form looks like a newer version of ones that are already live:'}
        </p>

        <ul className="mt-3 space-y-2">
          {candidates.map((c) => (
            <li key={c.kitId}>
              <label className="flex items-start gap-2 rounded border border-slate-200 p-2 hover:bg-slate-50">
                <input
                  type="radio"
                  name="retire-candidate"
                  className="mt-1"
                  checked={selected === c.kitId}
                  onChange={() => setSelected(c.kitId)}
                  disabled={busy}
                />
                {/* Label AND id, which is kitName()'s rule (bd nsz2d) spelled
                    out in JSX rather than a string -- these are separate
                    elements so the id can be styled as secondary. Two kits
                    can share a label, and this list exists precisely to pick
                    ONE of several revisions of the same form, so the id is
                    what distinguishes the rows. */}
                <span className="text-sm">
                  <span className="font-medium">{c.label}</span>
                  <span className="text-slate-500"> ({c.kitId})</span>
                  {c.edition && (
                    <span className="block text-xs text-slate-600">
                      {c.editionKind === 'edition_date' ? 'Edition ' : ''}
                      {c.editionKind === 'author_version' ? 'Version ' : ''}
                      {c.editionKind === 'published' ? 'Published ' : ''}
                      {c.edition}
                    </span>
                  )}
                  {/* Say WHY it was suggested. A label match is a guess; a form
                      number is a declaration. The author is the one who knows
                      which forms are actually the same. */}
                  <span className="block text-xs text-slate-500">
                    {c.matchedOn === 'form_number'
                      ? `Same form number${c.formNumber ? ` (${c.formNumber})` : ''}`
                      : 'Similar name'}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>

        {selected && (
          <p className="mt-3 rounded bg-amber-50 p-2 text-xs text-amber-900">
            Publishing will retire that form: clients stop seeing it, its files
            are kept, and it can be published again later.
          </p>
        )}

        <div className="mt-4 flex items-center justify-between gap-2">
          <button className="btn-sm text-xs" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <div className="flex items-center gap-2">
            {/* Clearing a mis-click matters: without this the only way out of a
                selection is Cancel, which loses the publish too. */}
            {selected && (
              <button className="btn-sm text-xs" onClick={() => setSelected(null)}
                      disabled={busy}>
                Clear selection
              </button>
            )}
            <button
              className="btn-sm btn-primary text-xs"
              onClick={() => onPublish(selected ?? undefined)}
              disabled={busy}
            >
              {busy
                ? 'Publishing...'
                : selected
                  ? 'Publish and retire the old one'
                  : 'Publish, keep both'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
