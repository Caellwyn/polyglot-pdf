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
// Default to hosted mode: most tests exercise the backend /lint path. The
// local-mode test flips this to false to hit the client-side fallback.
let hostedMode = true;

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  return {
    ...actual,
    lintSchema: (schema: FormSchema) => lintSchema(schema),
    isHostedMode: () => hostedMode,
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

  it('lints client-side in local mode (no backend call) -- bd h903', async () => {
    hostedMode = false;
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
