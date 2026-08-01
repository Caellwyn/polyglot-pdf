/**
 * ValidationPanel tests (bd polyglot-pdf-h76m.11, P4.3): the panel renders the
 * backend linter's findings at load time and focuses a field on click. The
 * remote store's lintSchema is mocked at the module level so the component's
 * fetch->render->focus flow is what runs.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import type { FormSchema } from '../types/schema';
import type { LintReport } from '../utils/remoteKitStore';

const lintSchema = vi.fn((_schema: FormSchema): Promise<LintReport> =>
  Promise.resolve({ findings: [], errorCount: 0, warningCount: 0 }),
);
// Default to "a backend is reachable": most tests exercise the backend /lint
// path. The no-backend test flips this to false to hit the client-side
// fallback. NOTE this is hasBackend(), not isHostedMode() -- the panel keys on
// backend REACHABILITY, which local dev now also has (bd polyglot-pdf-cpiw).
let hostedMode = true;
let backendReachable = true;

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  return {
    ...actual,
    lintSchema: (schema: FormSchema) => lintSchema(schema),
    isHostedMode: () => hostedMode,
    hasBackend: () => backendReachable,
  };
});

// Imported AFTER the mock so the component picks up the mocked lintSchema.
const { ValidationPanel } = await import('./ValidationPanel');
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
  hostedMode = true;
  backendReachable = true;
});
afterEach(cleanup);

describe('ValidationPanel load-time lint display', () => {
  it('lists the backend findings with their field ids', async () => {
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

    await waitFor(() =>
      expect(screen.getByText(/is not in the v2 registry/)).toBeInTheDocument(),
    );
    expect(screen.getByText('1 error')).toBeInTheDocument();
    // The human rule label and the field id both render.
    expect(screen.getByText('Unknown operator')).toBeInTheDocument();
    expect(screen.getByText('dep')).toBeInTheDocument();
  });

  it('focuses the field when a finding is clicked', async () => {
    const onSelectField = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'ref-unresolved-field',
          path: 'fields[1] (id=dep).show_if', field_id: 'dep',
          message: "references non-existent field 'ghost'",
        },
      ]),
    );
    render(<ValidationPanel schema={SCHEMA} onSelectField={onSelectField} />);

    const row = await screen.findByRole('button', { name: /references non-existent field/ });
    fireEvent.click(row);
    expect(onSelectField).toHaveBeenCalledWith('dep');
  });

  it('renders an unfocusable finding (no field_id) as non-clickable', async () => {
    const onSelectField = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'ERROR', rule: 'dump-widget-multiclaim',
          path: "widget 'topmost.f1'", field_id: null,
          message: 'claimed by more than one field: a, b',
        },
      ]),
    );
    render(<ValidationPanel schema={SCHEMA} onSelectField={onSelectField} />);

    await waitFor(() =>
      expect(screen.getByText(/claimed by more than one field/)).toBeInTheDocument(),
    );
    // No button role for a finding with nothing to focus.
    expect(screen.queryByRole('button', { name: /claimed by/ })).toBeNull();
  });

  it('renders translation verify flags as focusable warnings (bd 9djc)', async () => {
    // The backend linter re-emits the bake's persisted verify/rectify flags
    // (rule translation-*, WARNING) from _bakeoff provenance; the panel must
    // show the friendly label, count them as warnings, and focus the field.
    const onSelectField = vi.fn();
    lintSchema.mockResolvedValue(
      report([
        {
          severity: 'WARNING', rule: 'translation-drift-unresolved',
          path: 'fields[0] (id=picker).options[m].label_translations.spanish',
          field_id: 'picker',
          message: 'judge: meaning drift; kept the original',
        },
      ]),
    );
    render(<ValidationPanel schema={SCHEMA} onSelectField={onSelectField} />);

    await waitFor(() =>
      expect(screen.getByText(/kept the original/)).toBeInTheDocument(),
    );
    expect(screen.getByText('1 warning')).toBeInTheDocument();
    expect(
      screen.getByText('Translation drift (needs human review)'),
    ).toBeInTheDocument();
    const row = await screen.findByRole('button', { name: /kept the original/ });
    fireEvent.click(row);
    expect(onSelectField).toHaveBeenCalledWith('picker');
  });

  it('shows the clean state when there are no findings', async () => {
    lintSchema.mockResolvedValue(report([]));
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText('No validation errors')).toBeInTheDocument(),
    );
  });

  it('keeps the editor usable when the lint call fails (non-blocking)', async () => {
    lintSchema.mockRejectedValue(new Error('backend down'));
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/Could not check for issues/)).toBeInTheDocument(),
    );
    // The completion stats (client-side) still render -- as the slim one-line
    // strip (bd tynm replaced the big stat cards).
    expect(screen.getByText(/total/)).toBeInTheDocument();
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
    // A schema with a bad conditional reference: validateSchema flags it as a
    // warning, and the panel must show it WITHOUT ever calling the backend.
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
    render(<ValidationPanel schema={local} onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/non-existent field: ghost/)).toBeInTheDocument(),
    );
    // The backend linter was never called in local mode.
    expect(lintSchema).not.toHaveBeenCalled();
    // No "could not check" note -- the client-side lint succeeded.
    expect(screen.queryByText(/Could not check for issues/)).toBeNull();
  });

  // bd polyglot-pdf-cpiw exit criterion 2: a reduced ruleset must SAY it is
  // reduced. A short finding list from the lighter client rules is otherwise
  // indistinguishable from a clean form -- which is exactly how the
  // guidance-staleness gate went unnoticed in local mode for so long.
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
});

describe('ValidationPanel Repair-all (bd zgln, P5.3b)', () => {
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
    await waitFor(() => expect(screen.getByText('1 warning')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });

  it('shows no button when onRepairAll is not provided (editor tier)', async () => {
    lintSchema.mockResolvedValue(ERROR_REPORT());
    render(<ValidationPanel schema={SCHEMA} onSelectField={() => {}} />);
    await waitFor(() => expect(screen.getByText('1 error')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /Repair all/ })).toBeNull();
  });
});

// Report mirror (bd polyglot-pdf-0x10.6): the panel owns the lint round-trip,
// but App needs the findings too (the field list explains red rows in place),
// so each fresh report is mirrored up through onReport.
describe('ValidationPanel onReport mirror (bd 0x10.6)', () => {
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
    // SCHEMA's two fields lack pdf_field_name etc., but validateSchema flags
    // schema-level problems only; whatever it produces, the report shape must
    // arrive. Assert on the call, not the specific findings.
    render(<ValidationPanel schema={SCHEMA} onReport={onReport} />);
    await waitFor(() => {
      expect(onReport).toHaveBeenCalledWith(
        expect.objectContaining({ findings: expect.any(Array) }),
      );
    });
    expect(lintSchema).not.toHaveBeenCalled();
  });
});

describe('the completion stats honour the guidance-ack gate (bd anim)', () => {
  // Pins the PANEL-level wiring (stats memo consumes the lint report): before
  // this, reverting the memo to gate-blind getCompletionStats(schema) kept
  // the whole suite green (Opus round 4).
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

  it('a reviewed_correct field with un-acked drift is NOT counted complete', async () => {
    lintSchema.mockResolvedValue(report([staleFinding]));
    render(<ValidationPanel schema={schemaWithReview({ status: 'reviewed_correct' })}
      onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/0 complete, 1 need review/)).toBeInTheDocument(),
    );
  });

  it('the SAME field counts complete once acked for the current identity', async () => {
    lintSchema.mockResolvedValue(report([staleFinding]));
    render(<ValidationPanel
      schema={schemaWithReview({
        status: 'reviewed_correct', guidance_ack_sha1: 'abc123',
      })}
      onSelectField={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/1 complete, 0 need review/)).toBeInTheDocument(),
    );
  });
});
