/**
 * Lint-finding display + identity helpers (sprint-18 C1, bd polyglot-pdf-o7y9).
 *
 * The warnings pane is gone: findings now render AT the thing they are about
 * (property-anchored in the FieldEditor, flagged rows in the FieldList, one
 * pinned Form row for schema-level findings). This module owns everything
 * those surfaces share:
 *
 *   - RULE_LABELS / RULE_REMEDIES -- the human-facing vocabulary for the
 *     backend's stable rule ids. The backend rule catalogue and RULE_LABELS
 *     are contract-paired: backend/tests/unit/test_lint_rule_parity.py reads
 *     THIS file and fails when a backend rule has no label here (or a label
 *     goes dead). Moved verbatim from ValidationPanel.tsx when the pane was
 *     removed.
 *   - findingFingerprint -- the stable identity of a finding, used by the
 *     review-timeliness rule (a finding NEW since a field's sign-off demotes
 *     it back to needs-review) and by the Form row's standalone dismiss.
 *   - propertyAnchor -- which FieldEditor property a finding path names, so
 *     the editor can render the finding at that control and scroll to it.
 *   - the Form-row helpers -- schema-level (field-less) findings and their
 *     dismissal state on schema._form_review.
 */
import type { FormSchema } from '../types/schema';
import type { LintFinding } from './remoteKitStore';

// Human-readable rule labels: the backend rule ids are stable/terse (bd h76m.5);
// the UI shows a friendlier prefix while keeping the id available for the
// hover title. Unmapped ids fall back to the raw id (forward-compatible with new
// rules the backend adds).
export const RULE_LABELS: Record<string, string> = {
  'hidden-with-show-if': 'Hidden AND conditionally shown',
  'unknown-operator': 'Unrecognized comparison',
  'value-arity': 'Wrong comparison value',
  'option-value-missing': 'Answer choice has no value',
  'option-value-duplicate': 'Duplicate answer value',
  'option-value-comma': 'Comma in answer value',
  'option-value-slug': 'Answer value in wrong format',
  'ref-unresolved-field': 'Points at a missing field',
  'operator-trigger': 'Comparison not valid here',
  'ref-option-value': 'Not a real answer choice',
  'condition-malformed': 'Broken condition',
  'composite-depth': 'Condition nested too deep',
  'show-if-cycle': 'Show/hide rules loop forever',
  'dump-widget-multiclaim': 'PDF box claimed twice',
  // PDF-mapping + review-state rules. These were reaching reviewers as their
  // raw internal ids ("field-claim-unresolvable"), which reads as a system
  // error rather than something to fix -- caught by the rule-label parity test
  // (backend/tests/unit/test_lint_rule_parity.py, bd polyglot-pdf-cpiw).
  'dump-widget-unclaimed': 'PDF box not used by any field',
  'field-claim-unresolvable': 'Field points at a missing PDF box',
  'field-unbacked': 'Field has no PDF box',
  'readonly-conditional-no-unlock': 'Locked field can never be filled',
  'unlock-missing-flag-change': 'Unlock is missing its PDF flag change',
  'required-top-level': 'Required in the wrong place',
  'legacy-trigger-side-logic': 'Old-style trigger logic',
  'to-review-pending': 'Still needs re-filing',
  // Audit-trail identity (bd polyglot-pdf-47r3). Advisory only: a custom form
  // legitimately has no government edition, and the confirmation record falls
  // back to a content fingerprint -- so this reads as a prompt, not a defect.
  'audit-identity-no-edition': 'No form edition date',
  // Translation verify/rectify gate flags (bd polyglot-pdf-9djc): persisted by
  // the bake into _bakeoff provenance and re-emitted by the backend linter.
  // All WARNING -- the human-review worklist for baked translations.
  'translation-drift-rectified': 'Translation auto-corrected',
  'translation-drift-unresolved': 'Translation needs human review',
  'translation-ambiguous-source': 'Ambiguous source text',
  'translation-mechanical': 'Translation check failed',
  'translation-coverage': 'Translation coverage gap',
  // Guidance-content rules (bd wsao.3, sprint-16): the instructions/details
  // authoring worklist. All WARNING; the coverage rule is ONE aggregated
  // finding per schema (path $.fields, no field focus by design).
  'help-instructions-missing': 'No spoken guidance yet',
  'help-instructions-too-long': 'Instructions too long',
  'help-instructions-label-restatement': 'Instructions just repeat the label',
  'help-instructions-screen-ref': 'Instructions refer to the screen',
  'help-details-not-contained': 'Details not a verbatim quote',
  'help-details-no-reference-floor': 'No booklet text to check details against',
  'help-details-oversize': 'Details too long to reach the assistant',
  'help-details-headings-missing': 'Details missing headings',
  // The staleness gate (bd anim): computed FRESH each lint pass by
  // _check_guidance_identity_drift, not re-emitted from the bake report.
  'guidance-identity-stale': 'Guidance may be out of date',
  // KIT-LEVEL collapse of the staleness gate (bd cf6v): every compared field
  // mismatched at once (hash-formula change or bulk pipeline sweep), so one
  // finding at path "$" replaces the N per-field flags.
  'guidance-identity-mass-drift': 'All guidance needs a fresh check',
  // Guidance verify-loop flags (bd wsao.5), re-emitted from the persisted
  // bake report -- the instructions_enrich analog of the translation flags.
  'instructions-rectified': 'Guidance auto-corrected',
  'instructions-ungrounded-dropped': 'Guidance dropped (failed a safety check)',
  'instructions-enrich-unavailable': 'Guidance quality check unavailable',
};

// One imperative-sentence remedy per rule -- the action a reviewer takes,
// independent of the (already-plain) message text. Rendered beside each
// embedded finding (the "do this" line; the message carries the "what
// happened" / "why it matters" explanation). Keep every entry a single
// imperative sentence.
export const RULE_REMEDIES: Record<string, string> = {
  'hidden-with-show-if': 'Pick one: untick Hidden to show it only when the condition matches, or delete the condition to never show it.',
  'unknown-operator': 'Change the comparison to one of the allowed types.',
  'value-arity': 'Fix the comparison value to match what this comparison type expects.',
  'option-value-missing': 'Set a stored value for this answer choice.',
  'option-value-duplicate': 'Give each answer choice its own unique value.',
  'option-value-comma': 'Remove the comma from the answer value.',
  'option-value-slug': 'Regenerate the value from the label.',
  'ref-unresolved-field': 'Point this rule at a real field, or delete the rule.',
  'operator-trigger': 'Pick a comparison type that is valid for this field.',
  'ref-option-value': 'Pick one of the trigger field\'s real answer choices.',
  'condition-malformed': 'Rebuild this condition under the Conditional Logic section of the field.',
  'composite-depth': 'Flatten the nested condition to one level.',
  'show-if-cycle': 'Remove or change one of the rules to break the loop.',
  'dump-widget-multiclaim': 'Unclaim the PDF box from all but one field or choice.',
  'dump-widget-unclaimed': 'Add a field for this PDF box, or map it onto an existing field.',
  'field-claim-unresolvable': 'Reconnect this field to a real PDF box.',
  'field-unbacked': 'Connect this field to a PDF box, or mark it ignored.',
  'readonly-conditional-no-unlock': 'Set the unlock method to flip_readonly_bit.',
  'unlock-missing-flag-change': 'Add a pdf_field_flag_change next to the unlock method.',
  'required-top-level': 'Move the required setting into the field\'s validation rules.',
  'legacy-trigger-side-logic': 'Rebuild this as a show_if / require_if rule on the target field.',
  'to-review-pending': 'File the field into a real section; if the holding section lists leftover ids no field uses, delete those ids.',
  // Kept in step with schema_lint.py's audit-identity-no-edition message
  // (bd polyglot-pdf-xzw5). "Ignore this" was true when the fingerprint
  // fallback was automatic; it is now the one case the publish gate HARD
  // REFUSES, so the old text pointed the author away from the only action
  // that clears it.
  'audit-identity-no-edition': 'If this is an official government form, set its edition date (e.g. "12/2024") in the form metadata so confirmation records name the exact edition a client filled. If it is a custom or in-house form with no published edition, you will be asked for a version when you publish it -- that names the revision instead.',
  'translation-drift-rectified': 'Review the auto-corrected translation.',
  'translation-drift-unresolved': 'Review and correct this translation by hand.',
  'translation-ambiguous-source': 'Add context or a glossary entry for this source text.',
  'translation-mechanical': 'Fix the translation as described in the message.',
  'translation-coverage': 'Re-run the translation pass to fill the missing strings.',
  // AGGREGATE rule: schema_lint emits it once per schema at path "$.fields"
  // with no field anchor, so it renders on the pinned Form row and its
  // remedy must address the listed fields, not "this field" (Opus outer
  // review, pass 7).
  'help-instructions-missing': 'Write spoken instructions for each of the fields listed.',
  'help-instructions-too-long': 'Shorten the instructions and move detail into Details.',
  'help-instructions-label-restatement': 'Rewrite the instructions to add real guidance, or clear them.',
  'help-instructions-screen-ref': 'Rewrite the instructions to say the requirement in words.',
  'help-details-not-contained': 'Replace the details with a verbatim excerpt from the booklet.',
  'help-details-no-reference-floor': 'Add the booklet text for this form.',
  'help-details-oversize': 'Trim the details down to the most important excerpt.',
  'help-details-headings-missing': 'Add headings from the booklet to the details text.',
  'guidance-identity-stale': 'Confirm the guidance still reads correctly, or re-author it.',
  'guidance-identity-mass-drift': 'Re-run guidance authoring for this kit, or re-verify every field\'s guidance by hand.',
  'instructions-rectified': 'Review the auto-corrected guidance.',
  'instructions-ungrounded-dropped': 'Write guidance for this field by hand.',
  'instructions-enrich-unavailable': 'Re-run guidance authoring for this kit.',
};

/** The friendly label for a finding's rule, '' for the label-less local
 * fallback (rule: ''), and the raw id for an unmapped backend rule. */
export function ruleLabel(rule: string): string {
  return rule ? RULE_LABELS[rule] ?? rule : '';
}

// The identity token the guidance-staleness finding carries in its path
// (`fields (id=X).help[identity:<sha1>]`). The hash moves on EVERY material
// edit, so a fingerprint that included it would change constantly -- the ack
// gate (guidance_ack_sha1) already owns identity currency, so the fingerprint
// strips it and stays stable per rule+field. Deliberately NOT end-anchored:
// an end-anchored marker stops working the moment the backend appends a
// segment after the token, and its failure is silent (every guidance
// fingerprint would churn per edit, re-demoting reviewed fields) -- this repo
// has shipped that exact shape of regression before (Opus outer review,
// pass 8).
const IDENTITY_TOKEN_RE = /\[identity:[0-9a-f]+\]/g;

export function stripIdentitySuffix(path: string): string {
  return (path || '').replace(IDENTITY_TOKEN_RE, '');
}

// POSITIONAL array indices in a finding path (`fields[3] (id=x)`,
// `sections[0] (id=y)`). They are NOT identity: the `(id=X)` token beside
// them is. Removing or reordering an earlier field shifts every later index,
// so a fingerprint carrying them made one "Ignore" click falsely demote an
// arbitrary number of correctly-reviewed fields -- the mass re-review wave
// the message-exclusion rule exists to prevent, re-entering through the path
// (Opus outer review, pass 8). The `options[i]` index is NOT stripped: it has
// no id token beside it, so it is the only thing identifying which choice a
// finding is about.
const CONTAINER_INDEX_RE = /\b(fields|sections|parts)\[\d+\]/g;

export function stripContainerIndices(path: string): string {
  const p = path || '';
  // A `widget '<name>'` path carries a raw AcroForm NAME, not path structure
  // -- and PDF widget names legitimately contain `fields[0]`-shaped segments
  // (form1[0].fields[0].x[0]). Rewriting those would collapse two distinct
  // widgets into one fingerprint, so dismissing one form-level finding would
  // silently hide the other (Opus outer review, pass 9). Latent today (no
  // shipped kit has such a name) -- guarded because the input is
  // PDF-controlled data, not our own path grammar.
  if (p.startsWith('widget ')) return p;
  return p.replace(CONTAINER_INDEX_RE, '$1[]');
}

// Rules whose PATH does not localize the defect: the offending value lives
// only in the MESSAGE, so two genuinely different defects on one field share
// a path (schema_lint emits option-value-duplicate at the bare field path
// with the duplicated value in the message). For these, and ONLY these, the
// fingerprint folds in a bounded content hash -- otherwise fixing duplicate
// "a" and introducing duplicate "b" inherits the old sign-off and never
// demotes (Opus outer review, pass 9). Every other rule keeps the
// message-independent fingerprint the C12 copy pass depends on.
const MESSAGE_LOCALIZED_RULES = new Set(['option-value-duplicate']);

function contentDiscriminator(message: string): string {
  let h = 5381;
  for (let i = 0; i < message.length; i++) {
    h = ((h << 5) + h + message.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(36);
}

/**
 * The stable identity of a finding (sprint-18 C1): rule + field anchor +
 * path-sans-identity-suffix, message EXCLUDED.
 *
 * Excluding the message is load-bearing: messages are prose a copy pass
 * deliberately rewrites (bd xfdb), and a message-keyed fingerprint would
 * demote every reviewed field on every kit the moment the wording changes --
 * the exact mass re-review wave this epic exists to end. Accepted residual: a
 * message-ONLY content change does not re-raise (rule+path shifts cover the
 * real cases).
 */
export function findingFingerprint(f: LintFinding): string {
  const path = stripContainerIndices(stripIdentitySuffix(f.path));
  const extra = MESSAGE_LOCALIZED_RULES.has(f.rule)
    ? `|${contentDiscriminator(f.message)}`
    : '';
  return `${f.rule}|${f.field_id ?? ''}|${path}${extra}`;
}

/**
 * Which FieldEditor property a field-anchored finding is ABOUT, parsed from
 * the finding path's suffix after the `(id=X)` token. Drives both where the
 * finding renders (under that control) and where a click scrolls to.
 *
 *   instructions  fields (id=x).help.instructions / .help[identity:...]
 *   details       fields (id=x).help.details
 *   options       fields (id=x).options[<token>] -- see resolveOptionIndex
 *   conditions    fields (id=x).show_if / .require_if (any depth)
 *   field         anything else (the field itself: backing, review state...)
 *
 * The options token is carried RAW (a string), never pre-parsed as an index:
 * the backend has TWO producers with different conventions -- schema_lint's
 * option rules write the option's INDEX (`options[2]`), while the
 * translation-flag writers put the option's VALUE there
 * (option_translation.py: `options[<value>].label_translations.<lang>`), and
 * real kits have numeric option VALUES ('2'..'8' on i-90's height field), so
 * a digits-mean-index assumption anchored those flags at the wrong option
 * row (Opus fresh-eyes round 2). resolveOptionIndex disambiguates per rule.
 */
export interface FindingAnchor {
  kind: 'instructions' | 'details' | 'options' | 'conditions' | 'field';
  optionToken?: string;
}

export function propertyAnchor(f: LintFinding): FindingAnchor {
  const path = f.path || '';
  // Only the suffix AFTER the field token names a property; a field id could
  // in principle embed a look-alike substring, so split on the token first.
  const idToken = path.indexOf(')');
  const suffix = idToken >= 0 ? path.slice(idToken + 1) : path;
  // A BARE `.help` (no sub-key) is the guidance verify-loop flags' path
  // (enrich_instructions.py writes instructions-rectified /
  // -ungrounded-dropped / -enrich-unavailable at `fields (id=X).help`); their
  // remedies all point at the Instructions box, so that is their anchor
  // (Opus outer review, pass 4; bd z9u7 tracks the writers emitting precise
  // paths). The lookahead keeps `.help.details` falling through to its own
  // branch below.
  if (/\.help\.instructions\b/.test(suffix) || /\.help\[identity:/.test(suffix)
      || /\.help(?![.[])/.test(suffix)) {
    return { kind: 'instructions' };
  }
  if (/\.help\.details\b/.test(suffix)) return { kind: 'details' };
  // Two producer spellings: `.options[<token>]` (the option rules + the
  // translation flags) AND ` option[<j>]` -- space-separated, singular -- from
  // the widget-claim rule (schema_lint's field-claim-unresolvable emits
  // `fields[i] (id=X) option[j]`). Both anchor at the option row; matching
  // only the dotted plural sent the per-option mapping ERROR to the generic
  // banner with no hint of WHICH option is broken (Opus outer review, pass 1).
  const opt = /[. ]options?\[([^\]]+)\]/.exec(suffix);
  if (opt) return { kind: 'options', optionToken: opt[1] };
  if (/\.(show_if|require_if)\b/.test(suffix)) return { kind: 'conditions' };
  return { kind: 'field' };
}

/**
 * Resolve an options[<token>] anchor token to the option INDEX it names, or
 * undefined when it resolves to no option (the caller falls back to the
 * field bucket rather than pointing at a wrong row).
 *
 * Two producer conventions exist (see propertyAnchor): the translation-flag
 * family keys on the option VALUE; schema_lint's option rules key on the
 * INDEX. Rule-aware resolution, with a value match as the tiebreak for an
 * index-convention token that is out of range -- pointing a reviewer at the
 * WRONG option row is the failure mode this exists to end, so ambiguity
 * resolves toward "no anchor" over a guess.
 */
export function resolveOptionIndex(
  optionValues: Array<string | undefined>,
  finding: LintFinding,
  token: string,
): number | undefined {
  const byValue = optionValues.findIndex(v => v !== undefined && String(v) === token);
  if (finding.rule.startsWith('translation-')) {
    return byValue >= 0 ? byValue : undefined;
  }
  if (/^\d+$/.test(token)) {
    const idx = Number(token);
    if (idx < optionValues.length) return idx;
  }
  return byValue >= 0 ? byValue : undefined;
}

/**
 * Bucket findings by the field they anchor to (field-less findings are
 * skipped -- they are the Form row's, via formLevelFindings). THE one
 * definition: App's mirror and the strip's counts both consume this, so the
 * two can never bucket differently (Opus outer review, pass 1: two
 * hand-copies of this loop were the same duplicate-definition seam gateFlags
 * closed one layer down).
 */
export function bucketFindingsByField(
  findings: LintFinding[] | undefined,
): Map<string, LintFinding[]> {
  const map = new Map<string, LintFinding[]>();
  for (const f of findings ?? []) {
    if (!f.field_id) continue;
    const bucket = map.get(f.field_id);
    if (bucket) bucket.push(f);
    else map.set(f.field_id, [f]);
  }
  return map;
}

/** Schema-level findings: everything no FIELD row can carry, so no field's
 * review can cover them. These render on the pinned Form row at the top of
 * the field list.
 *
 * Keys on "resolves to no field in fields[]", NOT "has no field_id string"
 * (Opus fresh-eyes round 2): the backend's field_id extraction parses ANY
 * `(id=...)` token, so a section-anchored finding -- the publish-blocking
 * to-review-pending ERROR carries `sections[i] (id=sec_to_review_x)` -- and
 * a finding pinned to a quarantined (ignored) field both arrive with a
 * field_id that matches no rendered row. Under the removed pane they were
 * still listed; keying on the raw string made them render NOWHERE, the
 * confident-strip-then-409 failure relocated. The Form row is their home. */
export function formLevelFindings(
  findings: LintFinding[] | undefined,
  fields: Array<{ id: string }> | undefined,
): LintFinding[] {
  const ids = new Set((fields ?? []).map(f => f.id));
  return (findings ?? []).filter(f => f && (!f.field_id || !ids.has(f.field_id)));
}

function dismissedSet(schema: FormSchema): Set<string> {
  const raw = schema._form_review?.dismissed_fingerprints;
  return new Set(Array.isArray(raw) ? raw.filter(x => typeof x === 'string') : []);
}

/**
 * The key a form-level DISMISSAL is stored under -- always content-bearing,
 * unlike the timeliness fingerprint.
 *
 * The two paths need different widths (second confirming review). Timeliness
 * excludes the message so a copy-pass rewording cannot mass-demote reviewed
 * fields. But a DISMISSAL is a permanent, human-made "I have seen this and
 * accept it", and several form-level rules carry their entire content in the
 * message at ONE fixed path:
 *   - help-instructions-missing ($.fields): "12 of 40 fields have no spoken
 *     guidance yet (a, b, c)" -- dismissing at 12 would hide it at 300;
 *   - translation-coverage (coverage.<lang>): the same shape per language;
 *   - help-details-not-contained ($.form_metadata.details): emitted once PER
 *     PARAGRAPH, all sharing rule+path+null field_id -- so one dismissal hid
 *     every sibling, including ones the human never saw.
 * Keying the dismissal on the content means a dismissal covers exactly the
 * finding that was actually read, and a changed/grown problem re-raises.
 */
function dismissalKey(f: LintFinding): string {
  return `${findingFingerprint(f)}|${contentDiscriminator(f.message)}`;
}

/** Form-level WARNINGs that must NOT be dismissable despite their severity.
 * guidance-identity-mass-drift is the wave collapse's ONLY surviving signal:
 * it replaces the per-field stale flags AND disarms the per-field ack gate
 * (publish_readiness's GUIDANCE_STALE_RULE rationale), so one dismiss click
 * would let a kit read fully reviewed with every guidance_ack_sha1 stale and
 * nothing on any surface saying so -- the confident-strip-then-surprise class
 * again. It clears only the honest way: a re-bake/re-verify that re-stamps
 * (bd polyglot-pdf-cf6v, Opus cross-surface finding 2). */
const UNDISMISSABLE_WARNING_RULES = new Set(['guidance-identity-mass-drift']);

/** WARNING-severity form-level findings can be standalone-dismissed; an ERROR
 * blocks the publish gate regardless, so hiding it would just recreate the
 * confident-strip-then-409 lie the pane removal exists to end. Sole-signal
 * WARNINGs (above) are excepted for the same reason. */
export function isFindingDismissable(f: LintFinding): boolean {
  return f.severity !== 'ERROR' && !UNDISMISSABLE_WARNING_RULES.has(f.rule);
}

export function isFindingDismissed(schema: FormSchema, f: LintFinding): boolean {
  return dismissedSet(schema).has(dismissalKey(f));
}

/**
 * Record a standalone dismissal of a form-level WARNING, returning a NEW
 * schema. A non-dismissable (ERROR) or already-dismissed finding returns the
 * schema unchanged. The stored key is the CONTENT-bearing dismissalKey (see
 * its doc): a dismissal covers exactly the finding the human read, so a
 * grown or changed problem re-raises rather than staying hidden forever.
 */
export function withFormFindingDismissed(
  schema: FormSchema, f: LintFinding,
): FormSchema {
  if (!isFindingDismissable(f)) return schema;
  const fp = dismissalKey(f);
  const current = dismissedSet(schema);
  if (current.has(fp)) return schema;
  return {
    ...schema,
    _form_review: {
      ...schema._form_review,
      dismissed_fingerprints: [...current, fp],
    },
  };
}

/** The form-level findings the pinned Form row actually shows: schema-level
 * (nothing in fields[] can carry them), minus dismissed WARNINGs. ERRORs
 * always show. */
export function visibleFormFindings(
  schema: FormSchema, findings: LintFinding[] | undefined,
): LintFinding[] {
  const dismissed = dismissedSet(schema);
  return formLevelFindings(findings, schema.fields).filter(
    f => f.severity === 'ERROR' || !dismissed.has(dismissalKey(f)),
  );
}
