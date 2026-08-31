/**
 * ONE way to name a kit to a human (bd polyglot-pdf-kztlr).
 *
 * A kit has two identities: the `id` -- a folder name, often auto-generated
 * and meaningless (`form`, `form-2`) -- and the `label` a human gave it
 * ("W-7"). The catalogue cards show the label; server refusals used to name
 * only the id, so a message about "form-2" could not be matched to any card
 * on screen. That is the whole bug: not that ids are shown, but that ids are
 * shown WITHOUT the label anywhere near them.
 *
 * The rule here is therefore "label, and the id too when it adds anything":
 * when a kit has been renamed, both identities are real and the human may
 * need either (the delete dialog makes them type the id), so both are shown.
 * When the label is merely a restatement of the id, repeating it is noise.
 *
 * MIRRORED by `_kit_name` in backend/routes/editor_kit_routes.py -- server
 * refusals must name a kit the same way the catalogue does, or the message
 * cannot be matched to the card it is about. The two cannot share code across
 * the language boundary, so they share a CASE TABLE instead: the rows in
 * kitName.test.ts are the same rows as _PARITY_CASES in
 * backend/tests/unit/test_kit_refusals_name_the_label.py. Change one side and
 * the other side's tests are what tell you.
 */

/** The minimum shape a kit needs to be named -- both catalogue entry types
 *  satisfy it, so this works in hosted and local mode alike. */
export interface NameableKit {
  id: string;
  label?: string | null;
}

/**
 * True when `label` tells a human nothing the `id` did not already.
 *
 * Both catalogues derive a fallback label from the id when metadata carries
 * none (`form-2` -> "Form 2"), so an unlabelled kit arrives here with a label
 * that is a re-spelling of its id rather than a name anyone chose. Comparing
 * the raw strings would miss that and render "Form 2 (form-2)", which reads
 * as two facts when it is one.
 */
function labelRestatesId(label: string, id: string): boolean {
  const flatten = (s: string) => s.replace(/[-_\s]+/g, '').toLowerCase();
  return flatten(label) === flatten(id);
}

/**
 * How a kit is named in prose -- notices, errors, confirmations.
 *
 * Returns `"W-7" (form-2)` when the label was chosen by a human, and plain
 * `"form-2"` when it was not. The quotes are included because every existing
 * call site quoted the value it interpolated.
 */
export function kitName(kit: NameableKit): string {
  const label = (kit.label ?? '').trim();
  if (!label || labelRestatesId(label, kit.id)) return `"${kit.id}"`;
  return `"${label}" (${kit.id})`;
}
