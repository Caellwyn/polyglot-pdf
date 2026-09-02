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
/**
 * Whitespace, ENUMERATED rather than borrowed from the language
 * (bd polyglot-pdf-th60w).
 *
 * This class and `_KIT_NAME_SPACE` in backend/routes/editor_kit_routes.py must
 * agree character for character, and `\s` does NOT. Measured by scanning the
 * whole code space on both runtimes -- not read off a spec -- Python and
 * JavaScript disagree on SIX characters, in BOTH directions:
 *
 *   Python strips, JS does not:  U+001C U+001D U+001E U+001F U+0085
 *   JS strips, Python does not:  U+FEFF
 *
 * Only U+0085 and U+FEFF are reachable (the backend's `_safe_label` already
 * rejects ord < 32), and a BOM is an ordinary paste artifact from a
 * spreadsheet or a UTF-8-BOM file -- which is how labels get typed. The
 * consequence is not a crash: the server refusal and the client notice would
 * name the SAME kit two different ways, which is the "message cannot be
 * matched to the card" failure this whole module exists to prevent,
 * reintroduced through the mirror rather than a missed call site.
 *
 * The class is the UNION -- every character either language would strip -- so
 * neither side does less than its own language would, and both do the same
 * thing. Enumerating fixes the CLASS: patching the two known characters would
 * leave every future disagreement, and every runtime's Unicode-version drift,
 * open with no way to notice from inside either language.
 */
const KIT_NAME_SPACE = '\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff';
const KIT_NAME_TRIM = new RegExp(
  `^[${KIT_NAME_SPACE}]+|[${KIT_NAME_SPACE}]+$`, 'g');
const KIT_NAME_FLAT = new RegExp(`[-_${KIT_NAME_SPACE}]+`, 'g');

/** `.trim()` over the shared class, rather than the language's own. */
function kitNameTrim(text: string): string {
  return text.replace(KIT_NAME_TRIM, '');
}

function labelRestatesId(label: string, id: string): boolean {
  const flatten = (s: string) => s.replace(KIT_NAME_FLAT, '').toLowerCase();
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
  const label = kitNameTrim(kit.label ?? '');
  if (!label || labelRestatesId(label, kit.id)) return `"${kit.id}"`;
  return `"${label}" (${kit.id})`;
}

/**
 * How a kit is named INSIDE a control -- the catalogue-switcher <option> text
 * (bd polyglot-pdf-5ivqx).
 *
 * Same identity rule as `kitName`, different typography. Prose quotes the name
 * because it sits inside a sentence; an <option> is not a sentence, and the
 * strip already appends `-- status, 42%` after this, so quotes there would
 * read as part of the label.
 *
 * The ambiguity is real: nothing enforces label uniqueness, so two kits can
 * both read "W-7" in the dropdown. `value={k.id}` disambiguates what the
 * SELECT submits, but not what the human reads before choosing -- and choosing
 * the wrong form is how you edit the wrong form.
 *
 * Deliberately shares `labelRestatesId` with kitName rather than re-deriving
 * it: two copies of one rule is how the pair silently drifts apart.
 *
 * WHERE IT DIVERGES FROM kitName, and why. On a restatement kitName falls back
 * to the ID (`"i-90"`); this keeps the LABEL (`I-90`). Both are correct for
 * their surface. A refusal quotes an identifier, so the id is the honest thing
 * to quote. A dropdown shows a NAME, and `i-90` is a folder; substituting it
 * for the `I-90` the human typed silently downgrades their capitalisation and
 * punctuation for no gain -- the two are the same string bar spelling, so
 * neither disambiguates better, and only one is what they wrote. Caught by an
 * existing strip test going red on exactly that kit.
 */
export function kitOptionName(kit: NameableKit): string {
  const label = kitNameTrim(kit.label ?? '');
  if (!label) return kit.id;
  if (labelRestatesId(label, kit.id)) return label;
  return `${label} (${kit.id})`;
}
