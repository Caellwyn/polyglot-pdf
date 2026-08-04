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
  'audit-identity-no-edition': 'If this is an official government form, set its edition date (e.g. "12/2024") in the form metadata so confirmation records name the exact edition a client filled. If it is a custom or in-house form with no published edition, ignore this -- records fall back to a content fingerprint automatically.',
  'translation-drift-rectified': 'Review the auto-corrected translation.',
  'translation-drift-unresolved': 'Review and correct this translation by hand.',
  'translation-ambiguous-source': 'Add context or a glossary entry for this source text.',
  'translation-mechanical': 'Fix the translation as described in the message.',
  'translation-coverage': 'Re-run the translation pass to fill the missing strings.',
  'help-instructions-missing': 'Write spoken instructions for this field.',
  'help-instructions-too-long': 'Shorten the instructions and move detail into Details.',
  'help-instructions-label-restatement': 'Rewrite the instructions to add real guidance, or clear them.',
  'help-instructions-screen-ref': 'Rewrite the instructions to say the requirement in words.',
  'help-details-not-contained': 'Replace the details with a verbatim excerpt from the booklet.',
  'help-details-no-reference-floor': 'Add the booklet text for this form.',
  'help-details-oversize': 'Trim the details down to the most important excerpt.',
  'help-details-headings-missing': 'Add headings from the booklet to the details text.',
  'guidance-identity-stale': 'Confirm the guidance still reads correctly, or re-author it.',
  'instructions-rectified': 'Review the auto-corrected guidance.',
  'instructions-ungrounded-dropped': 'Write guidance for this field by hand.',
  'instructions-enrich-unavailable': 'Re-run guidance authoring for this kit.',
};

/** The friendly label for a finding's rule, '' for the label-less local
 * fallback (rule: ''), and the raw id for an unmapped backend rule. */
export function ruleLabel(rule: string): string {
  return rule ? RULE_LABELS[rule] ?? rule : '';
}

// The trailing identity token the guidance-staleness finding carries in its
// path (`fields (id=X).help[identity:<sha1>]`). The hash moves on EVERY
// material edit, so a fingerprint that included it would change constantly --
// the ack gate (guidance_ack_sha1) already owns identity currency, so the
// fingerprint strips it and stays stable per rule+field.
const IDENTITY_SUFFIX_RE = /\[identity:[0-9a-f]+\]$/;

export function stripIdentitySuffix(path: string): string {
  return (path || '').replace(IDENTITY_SUFFIX_RE, '');
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
  return `${f.rule}|${f.field_id ?? ''}|${stripIdentitySuffix(f.path)}`;
}

/**
 * Which FieldEditor property a field-anchored finding is ABOUT, parsed from
 * the finding path's suffix after the `(id=X)` token. Drives both where the
 * finding renders (under that control) and where a click scrolls to.
 *
 *   instructions  fields (id=x).help.instructions / .help[identity:...]
 *   details       fields (id=x).help.details
 *   options       fields (id=x).options[2] (optionIndex carries the 2)
 *   conditions    fields (id=x).show_if / .require_if (any depth)
 *   field         anything else (the field itself: backing, review state...)
 */
export interface FindingAnchor {
  kind: 'instructions' | 'details' | 'options' | 'conditions' | 'field';
  optionIndex?: number;
}

export function propertyAnchor(f: LintFinding): FindingAnchor {
  const path = f.path || '';
  // Only the suffix AFTER the field token names a property; a field id could
  // in principle embed a look-alike substring, so split on the token first.
  const idToken = path.indexOf(')');
  const suffix = idToken >= 0 ? path.slice(idToken + 1) : path;
  if (/\.help\.instructions\b/.test(suffix) || /\.help\[identity:/.test(suffix)) {
    return { kind: 'instructions' };
  }
  if (/\.help\.details\b/.test(suffix)) return { kind: 'details' };
  const opt = /\.options\[(\d+)\]/.exec(suffix);
  if (opt) return { kind: 'options', optionIndex: Number(opt[1]) };
  if (/\.(show_if|require_if)\b/.test(suffix)) return { kind: 'conditions' };
  return { kind: 'field' };
}

/** Schema-level findings: no field anchor, so no field's review can cover
 * them. These render on the pinned Form row at the top of the field list. */
export function formLevelFindings(findings: LintFinding[] | undefined): LintFinding[] {
  return (findings ?? []).filter(f => f && !f.field_id);
}

function dismissedSet(schema: FormSchema): Set<string> {
  const raw = schema._form_review?.dismissed_fingerprints;
  return new Set(Array.isArray(raw) ? raw.filter(x => typeof x === 'string') : []);
}

/** WARNING-severity form-level findings can be standalone-dismissed; an ERROR
 * blocks the publish gate regardless, so hiding it would just recreate the
 * confident-strip-then-409 lie the pane removal exists to end. */
export function isFindingDismissable(f: LintFinding): boolean {
  return f.severity !== 'ERROR';
}

export function isFindingDismissed(schema: FormSchema, f: LintFinding): boolean {
  return dismissedSet(schema).has(findingFingerprint(f));
}

/**
 * Record a standalone dismissal of a form-level WARNING, returning a NEW
 * schema. A non-dismissable (ERROR) or already-dismissed finding returns the
 * schema unchanged. The stored key is the fingerprint, so a reworded message
 * stays dismissed while a rule/path shift re-raises the row.
 */
export function withFormFindingDismissed(
  schema: FormSchema, f: LintFinding,
): FormSchema {
  if (!isFindingDismissable(f)) return schema;
  const fp = findingFingerprint(f);
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

/** The form-level findings the pinned Form row actually shows: schema-level,
 * minus dismissed WARNINGs. ERRORs always show. */
export function visibleFormFindings(
  schema: FormSchema, findings: LintFinding[] | undefined,
): LintFinding[] {
  const dismissed = dismissedSet(schema);
  return formLevelFindings(findings).filter(
    f => f.severity === 'ERROR' || !dismissed.has(findingFingerprint(f)),
  );
}
