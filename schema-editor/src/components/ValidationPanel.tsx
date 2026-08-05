import React from 'react';
import type { FormSchema } from '../types/schema';
import { validateSchema } from '../utils/validation';
import { reviewCounts } from '../utils/reviewStatus';
import { bucketFindingsByField } from '../utils/lintFindings';
import {
  AuthError,
  hasBackend,
  isHostedMode,
  lintSchema,
  type LintFinding,
  type LintReport,
} from '../utils/remoteKitStore';

/**
 * The one-truth strip (sprint-18 C1, bd polyglot-pdf-o7y9).
 *
 * The old warnings PANE -- a second copy of per-field truth that drifted from
 * the field statuses ("0 need review" beside "7 to review") -- is gone.
 * Findings now render AT their fields (FieldEditor property anchors, FieldList
 * flagged rows + the pinned Form row); this component keeps the pane's four
 * non-display responsibilities plus the single count line:
 *
 *   1. the lint round-trip (kit-scoped when a kit is open, so the strip lints
 *      with the SAME dump-loaded inputs as the publish gate; monotonic
 *      staleness guard; auth-error surfacing; keep-last-report-on-blip),
 *   2. the onReport mirror App's field list and overlay feed from,
 *   3. the Repair-all button (mechanical bulk action, errors only),
 *   4. the limited-checking / checks-did-not-run notices -- which matter MORE
 *      under status-derived counts (a failed lint must never render as
 *      "reviewed and clean"),
 * and from birth: 5. a refusal/error line where server refusal details
 * (publish gate, translation coverage) render with field links -- so no
 * mid-chain state exists where a refusal has no home (C2 upgrades this line
 * into the guided-flow staging).
 *
 * The counts derive from the PINNED predicate (reviewStatus.isCountedReviewed:
 * reviewed_correct, not demoted by the ack gate or the timeliness rule, no
 * field lint ERROR) -- one definition shared with the field list's jump, so
 * the strip and the rows can never disagree. "M to review" is a CONTROL:
 * click jumps to the next review target; right-click (or the filter toggle)
 * filters the field list to flagged fields -- the overview that used to
 * justify a pane.
 */
interface ValidationPanelProps {
  schema: FormSchema;
  // The open kit's id, when server actions are trusted for it (hosted, or a
  // local folder that passed the same-folder handshake). Present -> the lint
  // round-trip uses the kit-scoped route (dump-loaded, same inputs as the
  // publish gate); absent -> the dump-less route (no kit identity).
  kitId?: string | null;
  // Click-to-focus for the refusal line's field links: selecting a named field
  // jumps the editor to it. Optional so a bare strip still renders.
  onSelectField?: (fieldId: string) => void;
  // "M to review" click: jump to the next review target (App owns the ordered
  // field walk). Optional -- without it the count renders as plain text.
  onJumpToReview?: () => void;
  // Secondary action on the count: filter the field list to flagged fields.
  onToggleReviewFilter?: () => void;
  reviewFilterActive?: boolean;
  // A rotated/expired access code surfaced while linting -- let the host drop
  // back to the access gate, same as every other editorFetch caller.
  onAuthError?: () => void;
  // One-click Repair-all (bd polyglot-pdf-zgln, P5.3b): when provided (author
  // tier on a stored kit), a "Repair all (N)" button runs the server-side repair
  // and the host reloads the repaired schema. Omitted -> no button.
  onRepairAll?: () => Promise<void>;
  // Report escape hatch (bd polyglot-pdf-0x10.6): the strip owns the lint
  // round-trip, but the FIELD LIST and FieldEditor render the findings (at
  // their fields). Fired with each fresh report.
  onReport?: (report: LintReport | null) => void;
  // The latest server refusal (publish gate 409/422, translation coverage) --
  // the strip is its home. Field ids embedded as "(id=x)" render as links.
  refusal?: string | null;
  onDismissRefusal?: () => void;
}

// LAST-RESORT fallback for a session with NO backend reachable at all: the
// network-free client-side validateSchema, mapped into the same LintFinding
// rows the embedded-finding surfaces render so field-focus and display still
// work (bd polyglot-pdf-h903).
//
// This is NOT the normal local path any more (bd polyglot-pdf-cpiw): local dev
// runs the backend and gets the authoritative Python rules, same as hosted.
// This ruleset is deliberately lighter AND emits rule:'' for every finding, so
// any rule the UI keys on by id (the guidance-staleness ack gate) is invisible
// here. Treat reaching this path as degraded, not equivalent.
// A short, stable discriminator derived from a fallback finding's CONTENT.
//
// The fallback has no backend rule id, so without this every finding on a
// field fingerprints identically (rule + field + path, message excluded) and
// the timeliness demotion silently never fires there (Opus outer review,
// pass 7). A positional ordinal fixed that but introduced two new bugs --
// removing an unrelated finding shifts every later ordinal (false demotion)
// and lets a different finding inherit a retired one (missed demotion; pass
// 8). Hashing the message makes the discriminator move only when the finding
// itself changes, which is precisely what the timeliness rule wants.
//
// Note this is the ONE place a fallback fingerprint tracks message text: on
// the backend path the message is excluded because a copy pass rewrites it,
// but the fallback's messages are authored in-repo (validation.ts) and are
// this ruleset's only distinguishing content.
function localFindingKey(message: string): string {
  let h = 5381;
  for (let i = 0; i < message.length; i++) {
    h = ((h << 5) + h + message.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(36);
}

function localLintReport(schema: FormSchema): LintReport {
  // Occurrence counter per (field, message): two IDENTICAL messages on one
  // field (validateSchema can emit the same complaint for each duplicate of
  // a repeated id) must stay distinguishable, and the counter is scoped to
  // that pair -- so it does not move when an unrelated finding elsewhere is
  // fixed, unlike the global ordinal it replaces.
  const seenCount = new Map<string, number>();
  const findings: LintFinding[] = validateSchema(schema).map((e) => {
    const key = `${e.field_id}#${localFindingKey(e.message)}`;
    const n = seenCount.get(key) ?? 0;
    seenCount.set(key, n + 1);
    return {
    // validateSchema does not carry the backend rule ids; the embedded
    // surfaces render the message as-is (no RULE_LABELS prefix) by tagging it
    // with a sentinel treated as label-less.
    severity: e.type === 'error' ? 'ERROR' : 'WARNING',
    rule: '',
    // Content-keyed, NOT positional -- see localFindingKey.
    path: n === 0 ? key : `${key}~${n}`,
    message: e.message,
    // e.field_id is a field id for field-level errors and a section/_metadata
    // id otherwise; only real field ids focus, but the string is a safe target
    // (App's setSelectedFieldId simply no-ops for a non-field id).
    field_id: e.field_id || null,
    };
  });
  const errorCount = findings.filter((f) => f.severity === 'ERROR').length;
  return { findings, errorCount, warningCount: findings.length - errorCount };
}

// How long an edit must settle before the next lint round-trip fires. Short
// enough that findings feel live; long enough that typing a sentence is one
// request, not fifteen (exported for the debounce test).
export const LINT_DEBOUNCE_MS = 400;

// Ids a server refusal names inline as "(id=x)" (the same token the lint
// paths carry, formatted by the backend's gate message). Raw parse only --
// the strip filters the result against schema.fields before rendering links,
// because the token can name a SECTION (to-review-pending anchors at
// `sections[i] (id=sec_to_review_x)`) and a link to a non-field would
// silently mis-navigate through the selection recovery (Opus outer review,
// pass 6; the same resolves-to-a-field rule formLevelFindings applies). The
// char class is the backend's own `(id=(.*?))` width, not a narrower fork of
// the id grammar (bd h76m.11 centralized that parse in Python).
export function refusalFieldIds(refusal: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const re = /\(id=([^)]+)\)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(refusal)) !== null) {
    if (!seen.has(m[1])) { seen.add(m[1]); out.push(m[1]); }
  }
  return out;
}

export const ValidationPanel: React.FC<ValidationPanelProps> = ({
  schema,
  kitId,
  onSelectField,
  onJumpToReview,
  onToggleReviewFilter,
  reviewFilterActive = false,
  onAuthError,
  onRepairAll,
  onReport,
  refusal,
  onDismissRefusal,
}) => {
  const backendAvailable = React.useMemo(hasBackend, []);
  const hosted = React.useMemo(isHostedMode, []);

  const [report, setReport] = React.useState<LintReport | null>(null);
  const [lintError, setLintError] = React.useState<string | null>(null);
  const [linting, setLinting] = React.useState(false);
  const [repairing, setRepairing] = React.useState(false);

  // The counts derive from _review + the current findings ONLY -- both already
  // in hand -- so a confirm/fix moves them in the SAME render pass, no lint
  // round trip in between (C1 exit criterion 1). The SHARED
  // bucketFindingsByField is the one bucketing definition App's mirror also
  // uses, so the strip and the rows can never bucket differently.
  const findingsByField = React.useMemo(
    () => bucketFindingsByField(report?.findings), [report]);
  const counts = React.useMemo(
    () => reviewCounts(schema.fields, findingsByField),
    [schema.fields, findingsByField],
  );

  // Re-lint whenever the schema changes, through the backend's AUTHORITATIVE
  // Python linter whenever one is reachable -- kit-scoped when a kit is open,
  // so the dump-gated rules the publish gate runs are visible here too
  // (sprint-18 C1; the dump-less POST /lint cannot see them). A monotonic
  // token drops a stale in-flight result: the schema edits faster than the
  // round trip, so an earlier lint must never overwrite a newer one.
  //
  // The client-side ruleset below is a genuine FALLBACK (no backend configured
  // at all), not the normal local path. It is lighter than the Python one and
  // drops rule ids, which is why the guidance-staleness gate silently never
  // fired in local mode before bd cpiw: GUIDANCE_STALE_RULE never matched.
  const seqRef = React.useRef(0);
  // First lint per mount fires IMMEDIATELY (the component is keyed per form,
  // so every opened form lints at once); subsequent re-lints are debounced.
  // Without the debounce every keystroke re-fired the round trip -- now a
  // kit-scoped route that also loads the AcroForm dump from the store, i.e.
  // a metered read per keystroke on the hosted path (Opus outer review,
  // pass 1). The monotonic seq guard already discards stale RESULTS; the
  // debounce stops the REQUESTS.
  const firstLintRef = React.useRef(true);
  // A kitId TRANSITION also lints instantly: in local mode the first lint
  // fires dump-less (undefined) before the same-folder handshake resolves,
  // and riding the debounce for the kit-scoped re-lint would leave the strip
  // dump-blind -- confidently clean of the widget-claim rules -- for the
  // debounce window plus a round trip (Opus outer review, pass 2).
  const lastKitIdRef = React.useRef(kitId);
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
    const run = () => lintSchema(schema, kitId ?? undefined)
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
          // banner, green completion -- the exact silent-clean state bd cpiw
          // exists to remove. It is reachable: relaunching the editor mints a
          // FRESH per-run token while an already-open tab still holds the
          // previous one. Fall through to the banner instead.
          if (hosted) return;
          setLintError(
            'the editor was not accepted by its backend (the access token '
            + 'may be from an earlier run -- reload this page)');
          return;
        }
        // A lint failure is non-blocking: the editor stays usable, the strip
        // just notes it could not lint (e.g. the backend is transiently down).
        // Keep the last successful report visible rather than clearing it, so a
        // blip does not wipe the findings.
        setLintError(err instanceof Error ? err.message : 'Could not lint the schema');
      })
      .finally(() => {
        if (seq === seqRef.current) setLinting(false);
      });
    const kitChanged = lastKitIdRef.current !== kitId;
    lastKitIdRef.current = kitId;
    if (firstLintRef.current || kitChanged) {
      firstLintRef.current = false;
      void run();
      return;
    }
    const timer = window.setTimeout(() => void run(), LINT_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [schema, kitId, backendAvailable, hosted, onAuthError]);

  // Mirror each fresh report up to the host (App feeds it to the field list
  // and the field editor -- the surfaces that now RENDER findings). An effect,
  // not a call inside the fetch handlers, so the local-mode synchronous path
  // and the async backend path share one notification point.
  React.useEffect(() => {
    onReport?.(report);
  }, [report, onReport]);

  const errorCount = report?.errorCount ?? 0;

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

  const toReviewTitle = [
    onJumpToReview ? 'Click: jump to the next field needing review.' : null,
    onToggleReviewFilter
      ? 'Right-click: show only the fields needing review in the list.'
      : null,
  ].filter(Boolean).join(' ');

  return (
    // ONE line (sprint-18 C1): progress bar + counts + Repair-all. The
    // degraded-mode notices and the refusal line append as their own compact
    // rows only when their condition holds -- with a healthy lint and no
    // refusal this renders exactly the single line, and never a findings list.
    <div className="border-t border-gray-200 bg-white px-4 py-2" data-testid="review-strip">
      <div className="flex items-center gap-3 text-xs text-gray-600">
        <span className="font-semibold text-gray-900 whitespace-nowrap">Progress</span>
        <div className="flex-1 min-w-[80px] bg-gray-200 rounded-full h-2">
          <div
            className="bg-green-500 h-2 rounded-full transition-all"
            style={{ width: `${counts.percentage}%` }}
          />
        </div>
        <span className="whitespace-nowrap" data-testid="strip-reviewed">
          {counts.reviewed} reviewed
        </span>
        <span aria-hidden="true">&middot;</span>
        {(onJumpToReview || onToggleReviewFilter) ? (
          <button
            type="button"
            data-testid="strip-to-review"
            className={`whitespace-nowrap font-medium rounded px-1.5 py-0.5 border ${
              reviewFilterActive
                ? 'text-amber-900 bg-amber-100 border-amber-300'
                : counts.toReview > 0
                  ? 'text-amber-700 bg-amber-50 border-amber-200 hover:bg-amber-100'
                  : 'text-gray-500 bg-gray-50 border-gray-200'
            }`}
            title={toReviewTitle || undefined}
            onClick={() => onJumpToReview?.()}
            onContextMenu={(e) => {
              if (!onToggleReviewFilter) return;
              e.preventDefault();
              onToggleReviewFilter();
            }}
          >
            {counts.toReview} to review
          </button>
        ) : (
          <span className="whitespace-nowrap" data-testid="strip-to-review">
            {counts.toReview} to review
          </span>
        )}
        <span aria-hidden="true">&middot;</span>
        <span className="whitespace-nowrap" data-testid="strip-total">
          {counts.total} total
        </span>
        {linting && (
          <span className="text-gray-400 whitespace-nowrap" role="status">
            checking...
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
          clean form if we stay quiet:
            - no backend at all  -> the reduced client-side ruleset ran
            - backend present but the lint call FAILED (503 unconfigured, 401,
              server down mid-session) -> NOTHING ran, and the counts derive
              from a stale earlier report or none.
          This matters MORE now that the counts derive from field statuses: a
          failed lint must never let a form read "reviewed and clean". */}
      {(!backendAvailable || lintError) && (
        <div
          className="mt-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1"
          role="status"
        >
          {backendAvailable ? (
            <>
              Checks did not run: the editor could not reach its backend, so
              this form has NOT been fully checked. Issues (including
              out-of-date guidance) may be missing from the fields and the
              counts above.
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

      {/* The refusal/error line (sprint-18 C1, decision 1): server refusal
          details -- the publish gate's 409/422, the translation-coverage
          refusal -- render HERE with field links, so a refusal always has a
          home at the strip the moment it happens. */}
      {refusal && (
        <div
          className="mt-1 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1 flex items-start gap-2"
          role="alert"
          data-testid="strip-refusal"
        >
          <span className="flex-1">
            {refusal}
            {onSelectField && (() => {
              // Only ids that resolve to a REAL field become links: a
              // section-anchored token would mis-navigate (Opus outer
              // review, pass 6 -- the refusalFieldIds doc has the trace).
              const linkable = refusalFieldIds(refusal)
                .filter(fid => schema.fields.some(f => f.id === fid));
              if (linkable.length === 0) return null;
              return (
                <span className="block mt-0.5">
                  Go to:{' '}
                  {linkable.map((fid) => (
                    <button
                      key={fid}
                      type="button"
                      className="font-mono underline mr-2"
                      onClick={() => onSelectField(fid)}
                    >
                      {fid}
                    </button>
                  ))}
                </span>
              );
            })()}
          </span>
          {onDismissRefusal && (
            <button
              type="button"
              aria-label="Dismiss"
              className="text-red-400 hover:text-red-600 shrink-0"
              onClick={onDismissRefusal}
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          )}
        </div>
      )}
    </div>
  );
};
