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

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  return { ...actual, lintSchema: (schema: FormSchema) => lintSchema(schema) };
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
    // The completion stats (client-side) still render.
    expect(screen.getByText('Total Fields')).toBeInTheDocument();
  });

  it('reports a rotated access code to the host so it can re-prompt', async () => {
    const onAuthError = vi.fn();
    lintSchema.mockRejectedValue(new AuthError());
    render(
      <ValidationPanel schema={SCHEMA} onSelectField={() => {}} onAuthError={onAuthError} />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
  });
});
