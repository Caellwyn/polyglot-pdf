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
const { AuthError } = await import('../utils/remoteKitStore');

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
      { id: 'b', name: 'B', type: 'text', spoken_name: 'b',
        _review: { status: 'reviewed_correct',
                   seen_fingerprints: ['field-unbacked|b|fields[1] (id=b)'] } },
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
});

describe('refusalFieldIds', () => {
  it('extracts unique ids from "(id=x)" tokens in order', () => {
    expect(refusalFieldIds(
      'errors: [a] fields[0] (id=alpha): x; [b] fields[1] (id=beta): y; '
      + 'and again (id=alpha)',
    )).toEqual(['alpha', 'beta']);
  });

  it('finds nothing in a refusal with no field tokens', () => {
    expect(refusalFieldIds('translations are not baked yet')).toEqual([]);
  });
});
