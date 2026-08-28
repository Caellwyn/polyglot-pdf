/**
 * One-truth strip tests (sprint-18 C1, bd polyglot-pdf-o7y9; formerly the
 * ValidationPanel warnings-pane tests, bd h76m.11).
 *
 * The strip owns the lint round-trip (kit-scoped when a kit is open), the
 * onReport mirror, Repair-all, the degraded-mode notices, and the
 * refusal/error line -- and renders ONE line of counts derived from the
 * pinned predicate. It never renders a findings list: findings live at their
 * fields now.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import type { FormSchema } from '../types/schema';
import type { LintReport } from '../utils/remoteKitStore';
import { findingFingerprint } from '../utils/lintFindings';

const lintSchema = vi.fn(
  (_schema: FormSchema, _kitId?: string): Promise<LintReport> =>
    Promise.resolve({ findings: [], errorCount: 0, warningCount: 0 }),
);
// Default to "a backend is reachable": most tests exercise the backend /lint
// path. The no-backend test flips this to false to hit the client-side
// fallback. NOTE this is hasBackend(), not isHostedMode() -- the strip keys on
// backend REACHABILITY, which local dev now also has (bd polyglot-pdf-cpiw).
let hostedMode = true;
let backendReachable = true;

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  return {
    ...actual,
    lintSchema: (schema: FormSchema, kitId?: string) => lintSchema(schema, kitId),
    isHostedMode: () => hostedMode,
    hasBackend: () => backendReachable,
  };
});

// Imported AFTER the mock so the component picks up the mocked lintSchema.
const { ValidationPanel, refusalFieldIds } = await import('./ValidationPanel');
const { AuthError, ForbiddenError } = await import('../utils/remoteKitStore');

const SCHEMA: FormSchema = {
  form_metadata: { title: 'T', version: '1', form_number: 'X' },
  sections: [],
  fields: [
    { id: 'picker', name: 'Picker', type: 'select', spoken_name: 'picker' },
    { id: 'dep', name: 'Dep', type: 'text', spoken_name: 'dep' },
  ],
} as unknown as FormSchema;

function report(findings: LintReport['findings']): LintReport {
  const errorCount = findings.filter((f) => f.severity === 'ERROR').length;
  return { findings, errorCount, warningCount: findings.length - errorCount };
}

beforeEach(() => {
  lintSchema.mockReset();
  lintSchema.mockResolvedValue({ findings: [], errorCount: 0, warningCount: 0 });
  hostedMode = true;
  backendReachable = true;
});
afterEach(cleanup);

describe('the strip is ONE line of status-derived counts (s18 C1)', () => {
  it('never renders a findings list, even when findings exist', async () => {
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'unknown-operator',
          path: 'fields[1] (id=dep).show_if', field_id: 'dep',
          message: "operator 'is_selected' is not in the v2 registry",
        },
      ]),
    );
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    // The finding's message never appears in the strip -- it renders at the
    // field (FieldEditor / FieldList), not here.
    expect(screen.queryByText(/is not in the v2 registry/)).toBeNull();
    expect(screen.queryByText('Unrecognized comparison')).toBeNull();
    // The counts line is there.
    expect(screen.getByTestId('strip-reviewed')).toHaveTextContent('0 reviewed');
    expect(screen.getByTestId('strip-total')).toHaveTextContent('2 total');
  });

  it('counts derive from the pinned predicate and match a hand tally', async () => {
    // Fixture: 3 fields -- one currently signed off, one signed off but
    // carrying a lint ERROR (excluded), one unreviewed. b's sign-off SAW the
    // ERROR (its fingerprint is stamped), so the ERROR clause alone -- not
    // the timeliness rule -- is what keeps b out of the reviewed count.
    const fields = [
      { id: 'a', name: 'A', type: 'text', spoken_name: 'a',
        _review: { status: 'reviewed_correct', seen_fingerprints: [] } },
      // The stamp must be what findingFingerprint ACTUALLY produces for b's
      // ERROR (container indices are normalized away), or the timeliness
      // clause fires too and the test stops isolating the ERROR clause it
      // claims to pin (bd polyglot-pdf-d0vy, second confirming review).
      { id: 'b', name: 'B', type: 'text', spoken_name: 'b',
        _review: { status: 'reviewed_correct',
                   seen_fingerprints: [findingFingerprint({
                     severity: 'ERROR', rule: 'field-unbacked',
                     path: 'fields[1] (id=b)', field_id: 'b',
                     message: 'no PDF box',
                   })] } },
      { id: 'c', name: 'C', type: 'text', spoken_name: 'c' },
    ];
    const schema = { ...SCHEMA, fields } as unknown as FormSchema;
    lintSchema.mockResolvedValue(report([
      { severity: 'ERROR', rule: 'field-unbacked',
        path: 'fields[1] (id=b)', field_id: 'b', message: 'no PDF box' },
    ]));
    render(<ValidationPanel schema={schema} onSelectField={() => {}} />);
    // Hand tally: a reviewed (1); b demoted by its lint ERROR; c unreviewed.
    await waitFor(() => {
      expect(screen.getByTestId('strip-reviewed')).toHaveTextContent('1 reviewed');
      expect(screen.getByTestId('strip-to-review')).toHaveTextContent('2 to review');
      expect(screen.getByTestId('strip-total')).toHaveTextContent('3 total');
    });
  });

  it('a review flip moves the counts in the SAME render pass (no lint round trip)', async () => {
    // The lint call never resolves: the counts must move purely from the
    // schema prop change (confirm/fix responds instantly -- C1 criterion 1).
    lintSchema.mockReturnValue(new Promise(() => {}));
    const unreviewed = { ...SCHEMA } as unknown as FormSchema;
    const { rerender } = render(
      <ValidationPanel schema={unreviewed} onSelectField={() => {}} />);
    expect(screen.getByTestId('strip-reviewed')).toHaveTextContent('0 reviewed');
    const reviewed = {
      ...SCHEMA,
      fields: SCHEMA.fields.map(f => f.id === 'dep'
        ? { ...f, _review: { status: 'reviewed_correct', seen_fingerprints: [] } }
        : f),
    } as unknown as FormSchema;
    rerender(<ValidationPanel schema={reviewed} onSelectField={() => {}} />);
    // Synchronous: no waitFor -- the very next render carries the new count.
    expect(screen.getByTestId('strip-reviewed')).toHaveTextContent('1 reviewed');
    expect(screen.getByTestId('strip-to-review')).toHaveTextContent('1 to review');
  });

  it('"to review" is a control: click jumps, right-click toggles the filter', async () => {
    const onJumpToReview = vi.fn();
    const onToggleReviewFilter = vi.fn();
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}}
        onJumpToReview={onJumpToReview}
        onToggleReviewFilter={onToggleReviewFilter} />,
    );
    const control = screen.getByTestId('strip-to-review');
    fireEvent.click(control);
    expect(onJumpToReview).toHaveBeenCalledTimes(1);
    fireEvent.contextMenu(control);
    expect(onToggleReviewFilter).toHaveBeenCalledTimes(1);
  });

  it('the filter is reachable by ordinary CLICK, not only right-click (Opus outer r9)', () => {
    // Right-click is unreachable by keyboard (Enter/Space fire click) and
    // never fires on touch, so the filter -- the overview that replaced the
    // pane -- needs a real button.
    const onToggleReviewFilter = vi.fn();
    const { rerender } = render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}}
        onToggleReviewFilter={onToggleReviewFilter} />,
    );
    const toggle = screen.getByTestId('strip-filter-toggle');
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(toggle);
    expect(onToggleReviewFilter).toHaveBeenCalledTimes(1);
    rerender(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}}
        onToggleReviewFilter={onToggleReviewFilter} reviewFilterActive />,
    );
    expect(screen.getByTestId('strip-filter-toggle'))
      .toHaveAttribute('aria-pressed', 'true');
  });
});

describe('the kit-scoped lint round-trip (s18 C1)', () => {
  it('passes the open kit id so the lint runs dump-loaded like the gate', async () => {
    render(
      <ValidationPanel schema={SCHEMA} kitId="i-90" onSelectField={() => {}} />,
    );
    await waitFor(() =>
      expect(lintSchema).toHaveBeenCalledWith(SCHEMA, 'i-90'));
  });

  it('omits the kit id when no kit identity exists', async () => {
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() =>
      expect(lintSchema).toHaveBeenCalledWith(SCHEMA, undefined));
  });

  it('debounces re-lints: rapid edits do not fire a request per keystroke', async () => {
    // The kit-scoped route loads the AcroForm dump from the store, so a
    // round trip per keystroke is metered read amplification on the hosted
    // path (Opus outer review, pass 1). The FIRST lint per mount fires
    // instantly; subsequent schema changes coalesce behind the debounce.
    const { rerender } = render(
      <ValidationPanel schema={SCHEMA} kitId="i-90" onSelectField={() => {}} />,
    );
    expect(lintSchema).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 5; i++) {
      rerender(
        <ValidationPanel schema={{ ...SCHEMA }} kitId="i-90"
          onSelectField={() => {}} />,
      );
    }
    // Five rapid edits, zero additional synchronous calls.
    expect(lintSchema).toHaveBeenCalledTimes(1);
    // The trailing debounced lint eventually fires exactly once for the batch.
    await waitFor(() => expect(lintSchema).toHaveBeenCalledTimes(2),
      { timeout: 2000 });
  });

  it('a kitId transition lints INSTANTLY (no dump-blind debounce window)', () => {
    // Local mode: the first lint fires dump-less before the same-folder
    // handshake resolves; when the kit id arrives, the kit-scoped re-lint
    // must not ride the debounce -- the strip would sit confidently blind to
    // the dump-gated rules for the window (Opus outer review, pass 2).
    const { rerender } = render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} />,
    );
    expect(lintSchema).toHaveBeenCalledTimes(1);
    expect(lintSchema).toHaveBeenLastCalledWith(SCHEMA, undefined);
    rerender(
      <ValidationPanel schema={SCHEMA} kitId="i-90" onSelectField={() => {}} />,
    );
    // Synchronous: the kit-scoped lint fired immediately, not after 400ms.
    expect(lintSchema).toHaveBeenCalledTimes(2);
    expect(lintSchema).toHaveBeenLastCalledWith(SCHEMA, 'i-90');
  });
});

describe('degraded-mode notices + auth (carried from the pane)', () => {
  it('keeps the editor usable when the lint call fails (non-blocking)', async () => {
    lintSchema.mockRejectedValue(new Error('backend down'));
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/Could not check for issues/)).toBeInTheDocument(),
    );
    // The strip's counts still render.
    expect(screen.getByTestId('strip-total')).toBeInTheDocument();
  });

  it('reports a rotated access code to the host so it can re-prompt', async () => {
    const onAuthError = vi.fn();
    lintSchema.mockRejectedValue(new AuthError());
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onAuthError={onAuthError} />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
  });

  it('lints client-side when NO backend is reachable (no backend call) -- bd h903', async () => {
    hostedMode = false;
    backendReachable = false;
    const onReport = vi.fn();
    const local = {
      form_metadata: { title: 'T', version: '1', form_number: 'X' },
      sections: [],
      fields: [
        {
          id: 'dep', name: 'Dep', type: 'text', spoken_name: 'dep',
          show_if: { field: 'ghost', operator: 'equals', value: 'x' },
        },
      ],
    } as unknown as FormSchema;
    render(<ValidationPanel schema={local} onSelectField={() => {}} onReport={onReport} />);
    // The client-side findings reach the host through the mirror (they render
    // at the fields, not in the strip).
    await waitFor(() => {
      expect(onReport).toHaveBeenCalledWith(
        expect.objectContaining({
          findings: expect.arrayContaining([
            expect.objectContaining({
              message: expect.stringContaining('non-existent field: ghost'),
            }),
          ]),
        }),
      );
    });
    expect(lintSchema).not.toHaveBeenCalled();
    expect(screen.queryByText(/Could not check for issues/)).toBeNull();
  });

  // bd polyglot-pdf-cpiw exit criterion 2: a reduced ruleset must SAY it is
  // reduced -- and this matters MORE now that the counts derive from field
  // statuses (a failed lint must never read as "reviewed and clean").
  it('keys each fallback finding by CONTENT, so an unrelated fix does not move it', async () => {
    // A positional ordinal made an unrelated finding's disappearance shift
    // every later one (false demotion) and let a different finding inherit a
    // retired ordinal (missed demotion -- the original bug, still reachable).
    // Content keying moves a fingerprint only when the finding changes
    // (Opus outer review, pass 8).
    hostedMode = false;
    backendReachable = false;
    const onReport = vi.fn();
    // Two fields, each with a bad section reference. Field 'a' additionally
    // duplicates an id, so it owns an EARLIER finding than 'b'.
    const twoFields = {
      form_metadata: { title: 'T', version: '1', form_number: 'X' },
      sections: [],
      fields: [
        { id: 'a', name: 'A', type: 'text', section_id: 'ghost' },
        { id: 'a', name: 'A', type: 'text', section_id: 'ghost' },
        { id: 'b', name: 'B', type: 'text', section_id: 'ghost' },
      ],
    } as unknown as FormSchema;
    const { rerender } = render(
      <ValidationPanel schema={twoFields} onSelectField={() => {}} onReport={onReport} />);
    await waitFor(() => expect(onReport).toHaveBeenCalled());
    const first = onReport.mock.calls[onReport.mock.calls.length - 1][0] as LintReport;
    const bBefore = first.findings.filter(x => x.field_id === 'b').map(findingFingerprint);
    expect(bBefore.length).toBeGreaterThan(0);

    // Fix field a's duplicate id -- nothing about b changed.
    onReport.mockClear();
    const fixed = {
      ...twoFields,
      fields: [
        { id: 'a', name: 'A', type: 'text', section_id: 'ghost' },
        { id: 'b', name: 'B', type: 'text', section_id: 'ghost' },
      ],
    } as unknown as FormSchema;
    rerender(
      <ValidationPanel schema={fixed} onSelectField={() => {}} onReport={onReport} />);
    await waitFor(() => expect(onReport).toHaveBeenCalled());
    const second = onReport.mock.calls[onReport.mock.calls.length - 1][0] as LintReport;
    const bAfter = second.findings.filter(x => x.field_id === 'b').map(findingFingerprint);
    // b's fingerprints are UNCHANGED -> a field signed off on b stays reviewed.
    expect(bAfter).toEqual(bBefore);
    // ...and 'a' keeps ONE fingerprint per distinct finding across the edit
    // (a discriminator that collapses them would satisfy the equality above
    // vacuously -- the missed-demotion half of the same bug).
    const aBefore = first.findings.filter(x => x.field_id === 'a');
    expect(new Set(aBefore.map(findingFingerprint)).size).toBe(aBefore.length);
  });

  it('gives each fallback finding a DISTINCT fingerprint path (timeliness still works)', async () => {
    // The fingerprint excludes the message, so a bare field-id path made
    // every local finding on a field collapse to one key: fix error A, get
    // error B, and the field stayed signed-off green (Opus outer review,
    // pass 7). The ordinal keeps them distinct.
    hostedMode = false;
    backendReachable = false;
    const onReport = vi.fn();
    // Two errors on the SAME field: a duplicate id and a bad section ref.
    const local = {
      form_metadata: { title: 'T', version: '1', form_number: 'X' },
      sections: [],
      fields: [
        { id: 'dup', name: 'D', type: 'text', section_id: 'ghost_section' },
        { id: 'dup', name: 'D', type: 'text', section_id: 'ghost_section' },
      ],
    } as unknown as FormSchema;
    render(<ValidationPanel schema={local} onSelectField={() => {}} onReport={onReport} />);
    await waitFor(() => expect(onReport).toHaveBeenCalled());
    const calls = onReport.mock.calls;
    const report = calls[calls.length - 1][0] as LintReport;
    const onDup = report.findings.filter(f => f.field_id === 'dup');
    expect(onDup.length).toBeGreaterThan(1);
    expect(new Set(onDup.map(f => f.path)).size).toBe(onDup.length);
  });

  it('says so visibly when only the reduced client-side rules ran', async () => {
    hostedMode = false;
    backendReachable = false;
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/Limited checking/)).toBeInTheDocument());
    expect(screen.getByText(/out-of-date guidance/)).toBeInTheDocument();
  });

  it('shows no limited-checking notice once a backend is reachable', async () => {
    lintSchema.mockResolvedValue(report([]));
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByText(/Limited checking/)).toBeNull();
  });

  it('says the checks did NOT run when a reachable backend fails', async () => {
    lintSchema.mockRejectedValue(new Error('boom'));
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    expect(await screen.findByText(/Checks did not run/)).toBeInTheDocument();
    expect(screen.queryByText(/Limited checking/)).toBeNull();
  });

  it('surfaces a 401 in LOCAL mode instead of rendering nothing', async () => {
    hostedMode = false;          // backendReachable stays true
    lintSchema.mockRejectedValue(new AuthError());
    const onAuthError = vi.fn();
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}}
        onAuthError={onAuthError} />,
    );
    expect(await screen.findByText(/Checks did not run/)).toBeInTheDocument();
    expect(screen.getByText(/from an earlier run/)).toBeInTheDocument();
    expect(onAuthError).toHaveBeenCalled(); // host still told, as before
  });

  // lintSchema is the highest-frequency remote call in the editor (every kit
  // open, and debounced after essentially every edit), so a mid-session role
  // revocation usually surfaces HERE first. The error must be FORWARDED, not
  // just reported: App tells 403 (refused screen) from 401 (sign in again) by
  // its type, and a bare onAuthError() would silently route every 403 to the
  // sign-in form -- a dead end, since retrying cannot restore a revoked role.
  it('forwards a 403 as a ForbiddenError so App can route it', async () => {
    hostedMode = true;
    const refusal = new ForbiddenError('This account does not have schema editor access');
    lintSchema.mockRejectedValue(refusal);
    const onAuthError = vi.fn();
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}}
        onAuthError={onAuthError} />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalledWith(refusal));
  });

  it('a 401 in HOSTED mode still defers to the access-code gate', async () => {
    hostedMode = true;
    lintSchema.mockRejectedValue(new AuthError());
    const onAuthError = vi.fn();
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}}
        onAuthError={onAuthError} />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
    expect(screen.queryByText(/Checks did not run/)).toBeNull();
  });
});

describe('Repair-all (bd zgln, carried from the pane)', () => {
  const ERROR_REPORT = () =>
    report([
      {
        severity: 'ERROR', rule: 'option-value-duplicate',
        path: 'fields[0] (id=picker)', field_id: 'picker',
        message: "option value 'dup' appears 2 times",
      },
    ]);

  it('shows "Repair all (N)" and runs the handler when there are errors', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(ERROR_REPORT());
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  it('hides the button when there are no errors (warnings only)', async () => {
    const onRepairAll = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'WARNING', rule: 'show-if-cycle',
          path: 'fields (id=a)', field_id: 'a', message: 'cycle',
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  it('shows no button when onRepairAll is not provided (editor tier)', async () => {
    lintSchema.mockResolvedValue(ERROR_REPORT());
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  // bd polyglot-pdf-9g698: a select's option-value-missing is DELIBERATELY
  // unrepairable (backend/services/schema_repair.py's hold-aside, bd ot284
  // -- only the author can supply the PDF export code). The button must not
  // count it, or offer itself for a kit whose only defect is one.
  it('hides the button when the ONLY error is a select option-value-missing (unrepairable)', async () => {
    const onRepairAll = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'option-value-missing',
          path: 'fields[0] (id=picker)', field_id: 'picker',
          message: "Answer choice has no value",
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  it('subtracts ONLY the select option-value-missing errors from the count, keeping others', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'option-value-missing',
          path: 'fields[0] (id=picker)', field_id: 'picker',
          message: "Answer choice has no value",
        },
        {
          severity: 'ERROR', rule: 'option-value-duplicate',
          path: 'fields[0] (id=picker)~1', field_id: 'picker',
          message: "option value 'dup' appears 2 times",
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    // 2 errors reported, 1 unrepairable -> "Repair all (1)", not (2).
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  it('still counts option-value-missing on a RADIO field (still minted, unlike select)', async () => {
    const radioSchema: FormSchema = {
      ...SCHEMA,
      fields: [
        { id: 'r', name: 'R', type: 'radio', spoken_name: 'r' },
        ...SCHEMA.fields.slice(1),
      ],
    } as unknown as FormSchema;
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'option-value-missing',
          path: 'fields[0] (id=r)', field_id: 'r',
          message: "Answer choice has no value",
        },
      ]),
    );
    render(
      <ValidationPanel schema={radioSchema} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  // bd polyglot-pdf-9g698, Opus cross-surface review: the fix's initial cut
  // only excluded option-value-missing on select. Empirically running EVERY
  // ERROR-severity rule schema_lint.py can emit through schema_repair.py's
  // repair() (dumpless -- the common frontend lint path) found more rules
  // repair() never touches at all: hidden-with-show-if, ref-unresolved-field,
  // to-review-pending, dump-widget-multiclaim (dump-present). Each pinned
  // here the same way. (value-arity is scoped to a specific sub-shape below,
  // not excluded wholesale -- see the message-matched tests further down.)
  it.each([
    ['hidden-with-show-if', 'Field is both hidden and conditionally shown'],
    ['ref-unresolved-field', 'Condition references a field that does not exist'],
    ['to-review-pending', 'Field is still in the to-review holding section'],
    ['dump-widget-multiclaim', 'widget "Widget1" claimed by more than one field'],
  ])('hides the button when the ONLY error is %s (confirmed unrepairable by direct execution)', async (rule, message) => {
    const onRepairAll = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        { severity: 'ERROR', rule, path: 'fields[0] (id=dep)', field_id: 'dep', message },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  // condition-malformed carries six sub-shapes reachable through the
  // editor's normal flow (a 7th, non-dict top-level payload, is excluded
  // for a different reason -- see ValidationPanel.tsx's comment), with no
  // signal but message TEXT to tell them apart -- direct execution found
  // only two of the six survive repair() unchanged. The other four (a
  // non-list bucket, a non-dict bucket member, an empty bucket, a missing
  // operator) ARE minted/dropped, so excluding the whole rule id would
  // hide four working repairs -- the matching is scoped to the exact prose
  // these two sub-shapes emit.
  it.each([
    ['not a set of rules', 'this condition is a str, not a set of rules -- rebuild it under the field\'s Conditional Logic section'],
    ['does not say which field triggers it', 'this rule does not say which field triggers it -- open it under Conditional Logic and pick a field'],
  ])('hides the button when the ONLY error is a condition-malformed "%s" sub-shape', async (_label, message) => {
    const onRepairAll = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        { severity: 'ERROR', rule: 'condition-malformed', path: 'fields[0] (id=dep).show_if', field_id: 'dep', message },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  it('still counts a condition-malformed sub-shape repair() DOES clear (an empty condition group)', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'condition-malformed',
          path: 'fields[0] (id=dep).show_if', field_id: 'dep',
          message: "this group of rules is empty -- add at least one rule, or remove the group",
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  // value-arity, rounds 4-5 (Opus cross-surface review): the SAME
  // multi-shape problem as condition-malformed, but it took two attempts
  // to isolate correctly. Round 4 tested all three sub-shapes but drew a
  // wrong "wholesale exclusion" conclusion from results that were not
  // fully isolated from each other; round 5 re-tested each sub-shape
  // completely alone (one schema, one finding) against the REAL operators
  // (backend/models/conditional_vocabulary.py's OPERATORS, not a made-up
  // name) and found only TWO of the three survive repair() unchanged: a
  // list-arity operator (in/not_in) missing its list, and a scalar-arity
  // operator given a list or nothing. The third -- a stray value left on a
  // no-value operator (is_empty/is_not_empty/is_checked) -- IS silently
  // cleared by repair()'s _rewrite_atom (unconditionally drops the stray
  // value for any no-value operator), so it must be excluded from
  // UNREPAIRABLE, not included.
  it.each([
    ['list-arity operator missing its list', "'in' needs a list of one or more values to compare against -- add at least one"],
    ['scalar-arity operator given a list', "'equals' needs a single comparison value, not a list or nothing -- set exactly one"],
  ])('hides the button when the ONLY error is the value-arity "%s" sub-shape', async (_label, message) => {
    const onRepairAll = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'value-arity',
          path: 'fields[0] (id=dep).show_if', field_id: 'dep',
          message,
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  it('still counts the value-arity "stray value on a no-value operator" sub-shape (repair() DOES fix it)', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'value-arity',
          path: 'fields[0] (id=dep).show_if', field_id: 'dep',
          message: "'is_empty' does not take a comparison value, but one is set -- remove it",
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  // legacy-trigger-side-logic, round 6 (Opus cross-surface review): a
  // controls_fields entry carries an ACTION KEY (shows/hides/unlocks/
  // locks/makes_required/makes_optional) -- repair() mirrors 4 of the 6
  // onto a target's show_if/require_if/conditional_behavior, clearing the
  // finding; `locks`/`makes_optional` have NO v2 target-side encoding at
  // all and are explicitly RETAINED (schema_repair.py's own comment: needs
  // human review). The finding's message is IDENTICAL regardless of which
  // action triggered it, so this is scoped by inspecting the TRIGGER
  // field's own controls_fields array for locks/makes_optional, the same
  // cross-reference approach as option-value-missing's select carve-out.
  const controlsFieldsSchema = (control: Record<string, unknown>): FormSchema => ({
    ...SCHEMA,
    fields: [
      { id: 'trig', name: 'Trig', type: 'checkbox', spoken_name: 'trig', controls_fields: [control] },
      ...SCHEMA.fields.slice(1),
    ],
  } as unknown as FormSchema);

  it.each([
    ['locks', { operator: 'is_checked', locks: ['dep'] }],
    ['makes_optional', { operator: 'is_checked', makes_optional: ['dep'] }],
  ])('hides the button when the ONLY error is legacy-trigger-side-logic with an unconvertible "%s" action', async (_label, control) => {
    const onRepairAll = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'legacy-trigger-side-logic',
          path: 'fields[0] (id=trig).controls_fields', field_id: 'trig',
          message: "this field still uses the old controls_fields way of showing/requiring other fields",
        },
      ]),
    );
    render(
      <ValidationPanel schema={controlsFieldsSchema(control)} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  it.each([
    ['shows', { operator: 'is_checked', shows: ['dep'] }],
    ['makes_required', { operator: 'is_checked', makes_required: ['dep'] }],
  ])('still counts legacy-trigger-side-logic when the trigger field only carries a convertible "%s" action', async (_label, control) => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'legacy-trigger-side-logic',
          path: 'fields[0] (id=trig).controls_fields', field_id: 'trig',
          message: "this field still uses the old controls_fields way of showing/requiring other fields",
        },
      ]),
    );
    render(
      <ValidationPanel schema={controlsFieldsSchema(control)} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  // Round 7, Opus cross-surface review: a field can carry BOTH
  // controls_fields (unconvertible) AND conditional_fields at once, which
  // lint reports as TWO findings sharing one field_id but distinguished
  // only by `path` (".controls_fields" vs ".conditional_fields").
  // conditional_fields is ALWAYS unconditionally dropped by repair() (a
  // plain legacy id list, nothing to convert into) -- excluding both
  // findings just because the field_id has SOME unconvertible
  // controls_fields would wrongly hide the conditional_fields repair too.
  it('still counts the conditional_fields sibling finding even when the SAME field also has an unconvertible controls_fields', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'legacy-trigger-side-logic',
          path: 'fields[0] (id=trig).controls_fields', field_id: 'trig',
          message: "this field still uses the old controls_fields way of showing/requiring other fields",
        },
        {
          severity: 'ERROR', rule: 'legacy-trigger-side-logic',
          path: 'fields[0] (id=trig).conditional_fields', field_id: 'trig',
          message: "this field still uses the old conditional_fields way of showing/requiring other fields",
        },
      ]),
    );
    render(
      <ValidationPanel schema={controlsFieldsSchema({ operator: 'is_checked', locks: ['dep'] })} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    // 2 findings reported, 1 unrepairable (controls_fields/locks) -> "Repair all (1)", not (2) and not hidden.
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  // bd polyglot-pdf-jri5i, round 8 (Opus cross-surface review): the
  // unconvertible-action check must test TRUTHINESS, not mere key
  // PRESENCE -- schema_repair.py's rump-retention keys on `control.get(k)`,
  // so an explicitly-present-but-EMPTY locks/makes_optional array is falsy
  // there and repair() clears the whole entry (the field's controls_fields
  // gets popped entirely, same as any other fully-convertible field).
  it('still counts legacy-trigger-side-logic when locks/makes_optional is present but EMPTY (repair() clears it)', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'legacy-trigger-side-logic',
          path: 'fields[0] (id=trig).controls_fields', field_id: 'trig',
          message: "this field still uses the old controls_fields way of showing/requiring other fields",
        },
      ]),
    );
    render(
      <ValidationPanel schema={controlsFieldsSchema({ operator: 'is_checked', locks: [] })} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  // operator-trigger, round 7 (Opus cross-surface review): TWO distinct
  // sub-shapes under one rule id, like condition-malformed/value-arity. A
  // trigger field whose TYPE can never trigger any condition (e.g.
  // signature/table) has no rewrite repair() can apply and stays
  // standing; an operator merely invalid for an otherwise-legal trigger
  // type (e.g. is_checked on a text field) IS aliased by repair().
  it('hides the button when the ONLY error is the operator-trigger "field cannot trigger a condition" sub-shape', async () => {
    const onRepairAll = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'operator-trigger',
          path: 'fields[0] (id=dep).show_if', field_id: 'dep',
          message: "a 'signature' field cannot trigger a condition -- pick a different trigger field, or remove this rule",
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    await waitFor(() => expect(lintSchema).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  it('still counts the operator-trigger "operator not valid on this trigger type" sub-shape (repair() DOES fix it)', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'operator-trigger',
          path: 'fields[0] (id=dep).show_if', field_id: 'dep',
          message: "'is_checked' cannot be used on a 'text' field -- this comparison only works when the trigger field is one of: checkbox",
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });

  // Deliberately NOT excluded, unlike option-value-missing: a select's
  // option-value-slug repairability is DUMP-CONDITIONAL (pdf_choice_values
  // treats a missing dump as "no evidence", so a dumpless repair mints it
  // the same as radio/checkbox_group -- confirmed empirically). Excluding
  // it here would under-count a repair that genuinely works.
  it('still counts option-value-slug on a SELECT field (dump-conditional, not type-conditional like option-value-missing)', async () => {
    const onRepairAll = vi.fn().mockResolvedValue(undefined);
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'option-value-slug',
          path: 'fields[0] (id=picker)', field_id: 'picker',
          message: "value not in the required format",
        },
      ]),
    );
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onRepairAll={onRepairAll} />,
    );
    const btn = await screen.findByRole('button', { name: /Repair all \(1\)/ });
    fireEvent.click(btn);
    await waitFor(() => expect(onRepairAll).toHaveBeenCalledTimes(1));
  });
});

// Report mirror (bd polyglot-pdf-0x10.6): the strip owns the lint round-trip,
// but App renders the findings (field list rows, field editor anchors), so
// each fresh report is mirrored up through onReport.
describe('onReport mirror (bd 0x10.6, carried from the pane)', () => {
  it('mirrors the backend report up to the host once it lands', async () => {
    const onReport = vi.fn();
    lintSchema.mockResolvedValue(report([
      { severity: 'ERROR', rule: 'required-top-level', path: 'fields.picker', message: 'move it into validation', field_id: 'picker' },
    ]));
    render(<ValidationPanel schema={SCHEMA} onReport={onReport} />);
    await waitFor(() => {
      expect(onReport).toHaveBeenCalledWith(
        expect.objectContaining({
          errorCount: 1,
          findings: [expect.objectContaining({ field_id: 'picker' })],
        }),
      );
    });
  });

  it('mirrors the no-backend synchronous report too', async () => {
    hostedMode = false;
    backendReachable = false;
    const onReport = vi.fn();
    render(<ValidationPanel schema={SCHEMA} onReport={onReport} />);
    await waitFor(() => {
      expect(onReport).toHaveBeenCalledWith(
        expect.objectContaining({ findings: expect.any(Array) }),
      );
    });
    expect(lintSchema).not.toHaveBeenCalled();
  });
});

describe('the counts honour the guidance-ack gate (bd anim, re-pinned on the strip)', () => {
  const gatedField = {
    id: 'gated', name: 'G', type: 'text', spoken_name: 'g',
    pdf_field_name: 'G[0]', section_id: 's1',
    help: { instructions: 'x' },
  };
  const staleFinding = {
    severity: 'WARNING' as const, rule: 'guidance-identity-stale',
    path: 'fields (id=gated).help[identity:abc123]', field_id: 'gated',
    message: 'guidance may be out of date',
  };
  const schemaWithReview = (review: object) => ({
    ...SCHEMA,
    fields: [{ ...gatedField, _review: review }],
  } as unknown as FormSchema);

  it('a reviewed_correct field with un-acked drift is NOT counted reviewed', async () => {
    lintSchema.mockResolvedValue(report([staleFinding]));
    render(<ValidationPanel schema={schemaWithReview({ status: 'reviewed_correct' })}
      onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByTestId('strip-reviewed')).toHaveTextContent('0 reviewed'),
    );
  });

  it('the SAME field counts reviewed once acked for the current identity', async () => {
    lintSchema.mockResolvedValue(report([staleFinding]));
    render(<ValidationPanel
      schema={schemaWithReview({
        status: 'reviewed_correct', guidance_ack_sha1: 'abc123',
      })}
      onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByTestId('strip-reviewed')).toHaveTextContent('1 reviewed'),
    );
  });
});

describe('the refusal/error line (s18 C1, decision 1)', () => {
  it('renders a server refusal with click-to-focus field links', () => {
    const onSelectField = vi.fn();
    const refusal =
      'Schema has 1 lint error(s), so it cannot be marked complete: '
      + '[unknown-operator] fields[1] (id=dep).show_if: bad comparison';
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={onSelectField}
        refusal={refusal} onDismissRefusal={() => {}} />,
    );
    const line = screen.getByTestId('strip-refusal');
    expect(line).toHaveTextContent(/cannot be marked complete/);
    fireEvent.click(screen.getByRole('button', { name: 'dep' }));
    expect(onSelectField).toHaveBeenCalledWith('dep');
  });

  it('dismisses through the host callback', () => {
    const onDismissRefusal = vi.fn();
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}}
        refusal="translations are not baked yet" onDismissRefusal={onDismissRefusal} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onDismissRefusal).toHaveBeenCalled();
  });

  it('no refusal -> no line', async () => {
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    expect(screen.queryByTestId('strip-refusal')).toBeNull();
  });

  it('a token naming a NON-field (a section) renders no Go-to link', () => {
    // to-review-pending anchors at `sections[i] (id=sec_to_review_x)`, and
    // its raw path lands in the 409 detail; a link to a section id would
    // silently re-select an unrelated field through the vanish-recovery
    // (Opus outer review, pass 6). Only ids resolving to a real field link.
    const onSelectField = vi.fn();
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={onSelectField}
        refusal={'Schema has 2 lint error(s): [to-review-pending] sections[0] '
          + '(id=sec_to_review_misc): re-file these; [x] fields[1] (id=dep): y'}
        onDismissRefusal={() => {}} />,
    );
    // The real field links; the section id does not.
    expect(screen.getByRole('button', { name: 'dep' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'sec_to_review_misc' })).toBeNull();
  });
});

describe('refusalFieldIds', () => {
  it('extracts unique ids from "(id=x)" tokens in order', () => {
    expect(refusalFieldIds(
      'errors: [a] fields[0] (id=alpha): x; [b] fields[1] (id=beta): y; '
      + 'and again (id=alpha)',
    )).toEqual(['alpha', 'beta']);
  });

  it('parses with the backend\'s own token width, not a narrower id grammar', () => {
    // The raw parse mirrors schema_lint's `\(id=(.*?)\)`; the STRIP filters
    // against real fields before rendering, so width here is safe and a
    // future exotic id cannot silently lose its link (Opus outer r6).
    expect(refusalFieldIds('a (id=my.field) b')).toEqual(['my.field']);
  });

  it('finds nothing in a refusal with no field tokens', () => {
    expect(refusalFieldIds('translations are not baked yet')).toEqual([]);
  });
});
