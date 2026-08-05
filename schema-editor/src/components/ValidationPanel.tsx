import React from 'react';
import type { FormSchema } from '../types/schema';
import { getCompletionStats, validateSchema } from '../utils/validation';
import { needsAckFieldIds } from '../utils/guidanceStaleness';
import {
  AuthError,
  hasBackend,
  isHostedMode,
  lintSchema,
  type LintFinding,
  type LintReport,
} from '../utils/remoteKitStore';

interface ValidationPanelProps {
  schema: FormSchema;
  // Click-to-focus: selecting a finding's field jumps the editor to it (P4.3
  // "findings with field focus"). Optional so a bare panel still renders.
  onSelectField?: (fieldId: string) => void;
  // A rotated/expired access code surfaced while linting -- let the host drop
  // back to the access gate, same as every other editorFetch caller.
  onAuthError?: () => void;
  // One-click Repair-all (bd polyglot-pdf-zgln, P5.3b): when provided (author
  // tier on a stored kit), a "Repair all (N)" button runs the server-side repair
  // and the host reloads the repaired schema. Omitted -> no button (the panel is
  // read-only for the editor tier / local mode / an unsaved schema).
  onRepairAll?: () => Promise<void>;
  // Report escape hatch (bd polyglot-pdf-0x10.6): the panel owns the lint
  // round-trip, but the FIELD LIST also wants the findings (to explain a red
  // row where the author is looking). Fired with each fresh report.
  onReport?: (report: LintReport | null) => void;
}

// Human-readable rule labels: the backend rule ids are stable/terse (bd h76m.5);
// the panel shows a friendlier prefix while keeping the id available for the
// hover title. Unmapped ids fall back to the raw id (forward-compatible with new
// rules the backend adds).
const RULE_LABELS: Record<string, string> = {
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
// independent of the (already-plain) message text. NOT rendered anywhere
// yet (bd polyglot-pdf-xfdb, sprint-18 C12); a later bead (C1's embedded
// findings) consumes this to show "what to do" beside each finding. Keep
// every entry a single imperative sentence -- this is the "do this" line,
// the message above already carries the "what happened" / "why it
// matters" explanation.
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

// LAST-RESORT fallback for a session with NO backend reachable at all: the
// network-free client-side validateSchema, mapped into the same LintFinding
// rows the panel renders so field-focus and display still work (bd
// polyglot-pdf-h903).
//
// This is NOT the normal local path any more (bd polyglot-pdf-cpiw): local dev
// runs the backend and gets the authoritative Python rules, same as hosted.
// This ruleset is deliberately lighter AND emits rule:'' for every finding, so
// any rule the UI keys on by id (the guidance-staleness ack gate) is invisible
// here. Treat reaching this path as degraded, not equivalent.
function localLintReport(schema: FormSchema): LintReport {
  const findings: LintFinding[] = validateSchema(schema).map((e) => ({
    // validateSchema does not carry the backend rule ids; render the message
    // as-is (no RULE_LABELS prefix) by tagging it with a sentinel the renderer
    // treats as label-less.
    severity: e.type === 'error' ? 'ERROR' : 'WARNING',
    rule: '',
    path: e.field_id,
    message: e.message,
    // e.field_id is a field id for field-level errors and a section/_metadata
    // id otherwise; only real field ids focus, but the string is a safe target
    // (App's setSelectedFieldId simply no-ops for a non-field id).
    field_id: e.field_id || null,
  }));
  const errorCount = findings.filter((f) => f.severity === 'ERROR').length;
  return { findings, errorCount, warningCount: findings.length - errorCount };
}

export const ValidationPanel: React.FC<ValidationPanelProps> = ({
  schema,
  onSelectField,
  onAuthError,
  onRepairAll,
  onReport,
}) => {
  const backendAvailable = React.useMemo(hasBackend, []);
  const hosted = React.useMemo(isHostedMode, []);

  const [report, setReport] = React.useState<LintReport | null>(null);
  // The completion figure honours the guidance-ack gate (bd anim): a
  // reviewed_correct field whose guidance drifted un-acknowledged renders
  // amber in the FieldList, so it must not count complete here either --
  // before the (async, hosted) report lands the figure is gate-blind for that
  // one render cycle, same as every other lint-fed surface.
  const stats = React.useMemo(
    () => getCompletionStats(
      schema, needsAckFieldIds(schema.fields, report?.findings)),
    [schema, report],
  );
  const [lintError, setLintError] = React.useState<string | null>(null);
  const [linting, setLinting] = React.useState(false);
  const [repairing, setRepairing] = React.useState(false);

  // Re-lint whenever the schema changes, through the backend's AUTHORITATIVE
  // Python linter (P4.3) whenever one is reachable -- which is now local dev
  // too, not just hosted (bd polyglot-pdf-cpiw). A monotonic token drops a
  // stale in-flight result: the schema edits faster than the round trip, so an
  // earlier lint must never overwrite a newer one (same staleness guard the
  // remote-open path uses).
  //
  // The client-side ruleset below is a genuine FALLBACK now (no backend
  // configured at all), not the normal local path. It is lighter than the
  // Python one and drops rule ids, which is why the guidance-staleness gate
  // silently never fired in local mode: GUIDANCE_STALE_RULE never matched, so
  // the acknowledgment checkbox never rendered and edited fields read green.
  const seqRef = React.useRef(0);
  React.useEffect(() => {
    if (!backendAvailable) {
      // Synchronous, network-free: no staleness window, no failure path.
      setReport(localLintReport(schema));
      setLintError(null);
      setLinting(false);
      return;
    }
    const seq = ++seqRef.current;
    setLinting(true);
    lintSchema(schema)
      .then((r) => {
        if (seq !== seqRef.current) return;
        setReport(r);
        setLintError(null);
      })
      .catch((err) => {
        if (seq !== seqRef.current) return;
        if (err instanceof AuthError) {
          onAuthError?.();
          // HOSTED re-prompts with the access-code gate, so returning here is
          // enough. LOCAL has no gate screen (App renders it on `hosted &&
          // !role`), so a 401 would otherwise render NOTHING: no findings, no
          // banner, green completion -- the exact silent-clean state this bead
          // exists to remove. It is reachable: relaunching the editor mints a
          // FRESH per-run token while an already-open tab still holds the
          // previous one. Fall through to the banner instead.
          if (hosted) return;
          setLintError(
            'the editor was not accepted by its backend (the access token '
            + 'may be from an earlier run -- reload this page)');
          return;
        }
        // A lint failure is non-blocking: the editor stays usable, the panel
        // just notes it could not lint (e.g. the backend is transiently down).
        // Keep the last successful report visible rather than clearing it, so a
        // blip does not wipe the findings.
        setLintError(err instanceof Error ? err.message : 'Could not lint the schema');
      })
      .finally(() => {
        if (seq === seqRef.current) setLinting(false);
      });
  }, [schema, backendAvailable, hosted, onAuthError]);

  // Mirror each fresh report up to the host (App feeds it to the field list).
  // An effect, not a call inside the fetch handlers, so the local-mode
  // synchronous path and the async backend path share one notification point.
  React.useEffect(() => {
    onReport?.(report);
  }, [report, onReport]);

  const findings = report?.findings ?? [];
  const errorCount = report?.errorCount ?? 0;
  const warningCount = report?.warningCount ?? 0;

  const handleRepairAll = React.useCallback(async () => {
    if (!onRepairAll || repairing) return;
    setRepairing(true);
    try {
      await onRepairAll();
      // The host reloads the repaired schema, which re-runs the lint effect via
      // the [schema] dependency -- no manual re-lint needed here.
    } finally {
      setRepairing(false);
    }
  }, [onRepairAll, repairing]);

  const renderFinding = (finding: LintFinding, idx: number) => {
    const isError = finding.severity === 'ERROR';
    // Backend findings carry a rule id (mapped to a friendly label); the local
    // fallback leaves it empty, so the message stands alone with no label span.
    const label = finding.rule ? RULE_LABELS[finding.rule] ?? finding.rule : '';
    const canFocus = Boolean(finding.field_id && onSelectField);
    const body = (
      <>
        {label && <span className="font-medium">{label} </span>}
        {finding.field_id && (
          <span className="font-mono">{finding.field_id}</span>
        )}
        {(label || finding.field_id) ? ': ' : ''}
        {finding.message}
      </>
    );
    const className = `w-full text-left text-xs p-2 rounded ${
      isError ? 'bg-red-50 text-red-700' : 'bg-yellow-50 text-yellow-700'
    } ${canFocus ? 'hover:ring-1 hover:ring-current cursor-pointer' : ''}`;
    const title = finding.rule
      ? (canFocus ? `${finding.rule} -- click to focus ${finding.field_id}` : finding.rule)
      : undefined;
    // Field-anchored findings are buttons (click focuses the field); the rest
    // are plain divs -- there is nothing to jump to.
    return canFocus ? (
      <button
        key={idx}
        type="button"
        className={className}
        title={title}
        onClick={() => onSelectField?.(finding.field_id as string)}
      >
        {body}
      </button>
    ) : (
      <div key={idx} className={className} title={title}>
        {body}
      </div>
    );
  };

  return (
    // A SLIM strip (bd tynm): auto height instead of the old fixed h-48 + big
    // stat cards -- every pixel saved here goes straight to the editing area.
    // One line carries the progress bar + counts + lint summary + Repair-all;
    // the findings list (when any) expands below in its own capped scroller.
    <div className="border-t border-gray-200 bg-white px-4 py-2">
      <div className="flex items-center gap-3 text-xs text-gray-600">
        <span className="font-semibold text-gray-900 whitespace-nowrap">Progress</span>
        <div className="flex-1 min-w-[80px] bg-gray-200 rounded-full h-2">
          <div
            className="bg-green-500 h-2 rounded-full transition-all"
            style={{ width: `${stats.percentage}%` }}
          />
        </div>
        <span className="whitespace-nowrap">
          {stats.percentage}% &middot; {stats.complete} complete, {stats.needsReview} need review, {stats.total} total
        </span>
        {errorCount > 0 && (
          <span className="text-red-600 font-medium whitespace-nowrap">
            {errorCount} error{errorCount !== 1 ? 's' : ''}
          </span>
        )}
        {warningCount > 0 && (
          <span className="text-yellow-600 font-medium whitespace-nowrap">
            {warningCount} warning{warningCount !== 1 ? 's' : ''}
          </span>
        )}
        {findings.length === 0 && !lintError && (
          <span className="text-green-600 flex items-center gap-1 whitespace-nowrap">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
            {linting ? 'Checking for issues...' : 'No validation errors'}
          </span>
        )}
        {/* One-click Repair-all (bd zgln): author tier on a stored kit, only
            when there are ERROR-class defects the deterministic repair pass
            targets. */}
        {onRepairAll && errorCount > 0 && (
          <button
            type="button"
            className="btn-sm btn-primary ml-auto"
            onClick={() => void handleRepairAll()}
            disabled={repairing}
            title="Automatically repair the fixable errors (mint option slugs, rewrite invented operators, drop dead conditions)"
          >
            {repairing ? 'Repairing...' : `Repair all (${errorCount})`}
          </button>
        )}
      </div>

      {/* A lint call that could not reach the backend: non-blocking note (the
          editor and its work stay fully alive). */}
      {lintError && (
        <div className="mt-1 text-xs text-gray-500" role="status">
          Could not check for issues ({lintError}).
        </div>
      )}

      {/* The checks did NOT fully run -- say so LOUDLY (bd polyglot-pdf-cpiw
          exit criterion 2). Two ways to get here, and both look identical to a
          clean form if we stay quiet, which is exactly how the staleness gate
          went unnoticed in local mode for so long:
            - no backend at all  -> the reduced client-side ruleset ran
            - backend present but the lint call FAILED (503 unconfigured, 401,
              server down mid-session) -> NOTHING ran, and `findings` is empty
              or a stale earlier report.
          The small gray "could not check" line above is not enough on its own:
          an empty finding list next to a green completion figure reads as
          "this form is fine". */}
      {(!backendAvailable || lintError) && (
        <div
          className="mt-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1"
          role="status"
        >
          {backendAvailable ? (
            <>
              Checks did not run: the editor could not reach its backend, so
              this form has NOT been fully checked. Issues (including
              out-of-date guidance) may be missing from the list above.
            </>
          ) : (
            <>
              Limited checking: no backend connected, so only basic checks ran.
              Some issues (including out-of-date guidance) cannot be detected.
              Start the editor with <code>scripts/run-schema-editor.sh</code>{' '}
              for the full checks.
            </>
          )}
        </div>
      )}

      {/* Errors and Warnings from the backend linter */}
      {findings.length > 0 && (
        <div className="mt-2 max-h-28 overflow-auto custom-scrollbar space-y-1">
          {findings.map(renderFinding)}
        </div>
      )}
    </div>
  );
};
