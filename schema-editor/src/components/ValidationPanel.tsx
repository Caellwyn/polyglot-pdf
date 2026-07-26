import React from 'react';
import type { FormSchema } from '../types/schema';
import { getCompletionStats, validateSchema } from '../utils/validation';
import {
  AuthError,
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
  'unknown-operator': 'Unknown operator',
  'value-arity': 'Wrong value shape',
  'option-value-missing': 'Option has no value',
  'option-value-duplicate': 'Duplicate option value',
  'option-value-comma': 'Comma in option value',
  'option-value-slug': 'Option value not a slug',
  'ref-unresolved-field': 'Unresolved field reference',
  'operator-trigger': 'Operator not valid on trigger',
  'ref-option-value': 'Unknown option reference',
  'condition-malformed': 'Malformed condition',
  'composite-depth': 'Nested condition too deep',
  'show-if-cycle': 'Circular show-if dependency',
  'dump-widget-multiclaim': 'PDF widget claimed twice',
  // Translation verify/rectify gate flags (bd polyglot-pdf-9djc): persisted by
  // the bake into _bakeoff provenance and re-emitted by the backend linter.
  // All WARNING -- the human-review worklist for baked translations.
  'translation-drift-rectified': 'Translation drift (auto-corrected)',
  'translation-drift-unresolved': 'Translation drift (needs human review)',
  'translation-ambiguous-source': 'Ambiguous source text',
  'translation-mechanical': 'Translation mechanical check',
  'translation-coverage': 'Translation coverage gap',
  // Guidance-content rules (bd wsao.3, sprint-16): the instructions/details
  // authoring worklist. All WARNING; the coverage rule is ONE aggregated
  // finding per schema (path $.fields, no field focus by design).
  'help-instructions-missing': 'Guidance coverage gap',
  'help-instructions-too-long': 'Instructions too long (spoken bound)',
  'help-instructions-label-restatement': 'Instructions restate the label',
  'help-instructions-screen-ref': 'Instructions reference the page/screen',
  'help-details-not-contained': 'Details not verbatim from booklet',
  'help-details-no-reference-floor': 'Details without booklet floor',
  'help-details-oversize': 'Details oversize',
  'help-details-headings-missing': 'Details missing headings',
};

// Local (non-hosted) delivery mode has no backend and no access code to reach
// the token-gated /api/editor/lint route, so it falls back to the network-free
// client-side validateSchema -- mapped into the same LintFinding rows the panel
// renders, so field-focus and display are identical to the hosted path (bd
// polyglot-pdf-h903; without this, local mode silently lost all lint feedback).
// The client ruleset is intentionally lighter than the Python one; hosted mode
// is where the authoritative rules run.
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
  const stats = React.useMemo(() => getCompletionStats(schema), [schema]);
  const hosted = React.useMemo(isHostedMode, []);

  const [report, setReport] = React.useState<LintReport | null>(null);
  const [lintError, setLintError] = React.useState<string | null>(null);
  const [linting, setLinting] = React.useState(false);
  const [repairing, setRepairing] = React.useState(false);

  // Re-lint whenever the schema changes. Hosted mode calls the backend's
  // authoritative Python linter (P4.3); local mode -- which has no backend and
  // no access code to reach the token-gated route -- lints synchronously
  // client-side (bd polyglot-pdf-h903). A monotonic token drops a stale
  // in-flight backend result: the schema edits faster than the round trip, so
  // an earlier lint must never overwrite a newer one (same staleness guard the
  // remote-open path uses).
  const seqRef = React.useRef(0);
  React.useEffect(() => {
    if (!hosted) {
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
  }, [schema, hosted, onAuthError]);

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

      {/* Errors and Warnings from the backend linter */}
      {findings.length > 0 && (
        <div className="mt-2 max-h-28 overflow-auto custom-scrollbar space-y-1">
          {findings.map(renderFinding)}
        </div>
      )}
    </div>
  );
};
