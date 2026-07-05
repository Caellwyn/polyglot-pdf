import React from 'react';
import type { FormSchema } from '../types/schema';
import { getCompletionStats } from '../utils/validation';
import {
  AuthError,
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
};

export const ValidationPanel: React.FC<ValidationPanelProps> = ({
  schema,
  onSelectField,
  onAuthError,
}) => {
  const stats = React.useMemo(() => getCompletionStats(schema), [schema]);

  const [report, setReport] = React.useState<LintReport | null>(null);
  const [lintError, setLintError] = React.useState<string | null>(null);
  const [linting, setLinting] = React.useState(false);

  // Re-lint whenever the schema changes, over the authoritative backend rules
  // (P4.3). A monotonic token drops a stale in-flight result: the schema edits
  // faster than the round trip, so an earlier lint must never overwrite a newer
  // one (same staleness guard the remote-open path uses).
  const seqRef = React.useRef(0);
  React.useEffect(() => {
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
        // just notes it could not lint (e.g. no backend in a pure-local file
        // session). Keep the last successful report visible rather than
        // clearing it, so a transient blip does not wipe the findings.
        setLintError(err instanceof Error ? err.message : 'Could not lint the schema');
      })
      .finally(() => {
        if (seq === seqRef.current) setLinting(false);
      });
  }, [schema, onAuthError]);

  const findings = report?.findings ?? [];
  const errorCount = report?.errorCount ?? 0;
  const warningCount = report?.warningCount ?? 0;

  const renderFinding = (finding: LintFinding, idx: number) => {
    const isError = finding.severity === 'ERROR';
    const label = RULE_LABELS[finding.rule] ?? finding.rule;
    const canFocus = Boolean(finding.field_id && onSelectField);
    const body = (
      <>
        <span className="font-medium">{label}</span>
        {finding.field_id && (
          <>
            {' '}
            <span className="font-mono">{finding.field_id}</span>
          </>
        )}
        : {finding.message}
      </>
    );
    const className = `w-full text-left text-xs p-2 rounded ${
      isError ? 'bg-red-50 text-red-700' : 'bg-yellow-50 text-yellow-700'
    } ${canFocus ? 'hover:ring-1 hover:ring-current cursor-pointer' : ''}`;
    // Field-anchored findings are buttons (click focuses the field); the rest
    // are plain divs -- there is nothing to jump to.
    return canFocus ? (
      <button
        key={idx}
        type="button"
        className={className}
        title={`${finding.rule} -- click to focus ${finding.field_id}`}
        onClick={() => onSelectField?.(finding.field_id as string)}
      >
        {body}
      </button>
    ) : (
      <div key={idx} className={className} title={finding.rule}>
        {body}
      </div>
    );
  };

  return (
    <div className="h-48 border-t border-gray-200 bg-white p-4 overflow-auto custom-scrollbar">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">
        Validation &amp; Progress
      </h3>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-600 mb-1">
          <span>Completion: {stats.percentage}%</span>
          <span>
            {stats.complete} complete, {stats.needsReview} need review, {stats.total} total
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-green-500 h-2 rounded-full transition-all"
            style={{ width: `${stats.percentage}%` }}
          />
        </div>
      </div>

      {/* Status Summary */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="p-3 bg-green-50 rounded-md">
          <div className="text-2xl font-bold text-green-600">{stats.complete}</div>
          <div className="text-xs text-gray-600">Complete</div>
        </div>
        <div className="p-3 bg-yellow-50 rounded-md">
          <div className="text-2xl font-bold text-yellow-600">{stats.needsReview}</div>
          <div className="text-xs text-gray-600">Needs Review</div>
        </div>
        <div className="p-3 bg-blue-50 rounded-md">
          <div className="text-2xl font-bold text-blue-600">{stats.total}</div>
          <div className="text-xs text-gray-600">Total Fields</div>
        </div>
      </div>

      {/* A lint call that could not reach the backend: non-blocking note (the
          editor and its work stay fully alive). */}
      {lintError && (
        <div className="mb-3 text-xs text-gray-500" role="status">
          Could not check for issues ({lintError}).
        </div>
      )}

      {/* Errors and Warnings from the backend linter */}
      {findings.length > 0 && (
        <div className="space-y-2">
          <div className="flex gap-4 text-sm">
            {errorCount > 0 && (
              <span className="text-red-600 font-medium">
                {errorCount} error{errorCount !== 1 ? 's' : ''}
              </span>
            )}
            {warningCount > 0 && (
              <span className="text-yellow-600 font-medium">
                {warningCount} warning{warningCount !== 1 ? 's' : ''}
              </span>
            )}
          </div>
          <div className="max-h-32 overflow-auto custom-scrollbar space-y-1">
            {findings.map(renderFinding)}
          </div>
        </div>
      )}

      {findings.length === 0 && !lintError && (
        <div className="text-sm text-green-600 flex items-center gap-2">
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          {linting ? 'Checking for issues...' : 'No validation errors'}
        </div>
      )}
    </div>
  );
};
