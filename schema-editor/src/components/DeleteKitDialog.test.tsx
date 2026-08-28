/**
 * The delete confirmation (bd polyglot-pdf-6x1j).
 *
 * Deletion is unrecoverable and takes the revision archive with it, so the
 * dialog's job is to make the author look at WHICH form they are deleting --
 * the mistake that actually happens is deleting the wrong row, not deleting
 * the right one by accident.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DeleteKitDialog } from './DeleteKitDialog';

const props = {
  kitId: 'acme-intake',
  kitLabel: 'Acme Intake',
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
};

describe('DeleteKitDialog escalation (bd polyglot-pdf-6zhaf)', () => {
  // The whole point of the bead: a refusal the human cannot get past is not a
  // safeguard, it is a form that can never be cleaned up. The server grades the
  // risk; the dialog offers the matching confirmation.
  const warned = (escalation: 'ack' | 'double-ack') => ({
    ...props,
    warning: { text: 'Records for this form cannot be checked right now.', escalation },
  });

  it('a single-ack warning offers Delete anyway, enabled immediately', () => {
    const onAcknowledge = vi.fn();
    render(<DeleteKitDialog {...warned('ack')} onAcknowledge={onAcknowledge} />);

    expect(screen.getByTestId('delete-warning-ack')).toBeInTheDocument();
    // No second tick for a never-published form: the risk does not warrant it.
    expect(screen.queryByTestId('delete-understood')).not.toBeInTheDocument();

    const anyway = screen.getByTestId('delete-anyway');
    expect(anyway).not.toBeDisabled();
    fireEvent.click(anyway);
    expect(onAcknowledge).toHaveBeenCalled();
  });

  it('a DOUBLE-ack warning stays disabled until the box is ticked', () => {
    const onAcknowledge = vi.fn();
    render(<DeleteKitDialog {...warned('double-ack')} onAcknowledge={onAcknowledge} />);

    const anyway = screen.getByTestId('delete-anyway');
    expect(anyway).toBeDisabled();
    fireEvent.click(anyway);
    expect(onAcknowledge).not.toHaveBeenCalled();   // clicking through is not enough

    fireEvent.click(screen.getByTestId('delete-understood'));
    expect(anyway).not.toBeDisabled();
    fireEvent.click(anyway);
    expect(onAcknowledge).toHaveBeenCalledTimes(1);
  });

  it('shows the SERVER wording, which names what is at risk for this kit', () => {
    render(<DeleteKitDialog {...warned('double-ack')} />);
    expect(screen.getByText(/cannot be checked right now/)).toBeInTheDocument();
  });

  // A fresh warning must not inherit a tick from a previous attempt, or the
  // second confirmation silently stops being a decision.
  it('re-arms the tick when a NEW warning arrives', () => {
    const { rerender } = render(<DeleteKitDialog {...warned('double-ack')} />);
    fireEvent.click(screen.getByTestId('delete-understood'));
    expect(screen.getByTestId('delete-anyway')).not.toBeDisabled();

    rerender(<DeleteKitDialog {...props}
      warning={{ text: 'A different warning entirely.', escalation: 'double-ack' }} />);
    expect(screen.getByTestId('delete-anyway')).toBeDisabled();
  });

  it('with no warning, the ordinary type-to-confirm path is untouched', () => {
    render(<DeleteKitDialog {...props} />);
    expect(screen.queryByTestId('delete-anyway')).not.toBeInTheDocument();
    expect(screen.getByText('Delete permanently')).toBeInTheDocument();
  });
});

describe('DeleteKitDialog', () => {
  it('keeps Delete disabled until the kit id is typed exactly', () => {
    const onConfirm = vi.fn();
    render(<DeleteKitDialog {...props} onConfirm={onConfirm} />);
    const button = screen.getByText('Delete permanently') as HTMLButtonElement;

    expect(button.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'acme' } });
    expect(button.disabled).toBe(true);          // a prefix is not enough

    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'acme-intake' } });
    expect(button.disabled).toBe(false);

    fireEvent.click(button);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does not accept a near-miss', () => {
    // Deliberately strict. A forgiving match (case-insensitive, fuzzy) would
    // undo the only thing this input is for: making the author read the id.
    render(<DeleteKitDialog {...props} />);
    const button = screen.getByText('Delete permanently') as HTMLButtonElement;

    for (const near of ['ACME-INTAKE', 'acme_intake', 'acme-intakes', 'acme intake']) {
      fireEvent.change(screen.getByLabelText(/Type/), { target: { value: near } });
      expect(button.disabled).toBe(true);
    }
  });

  it('tolerates surrounding whitespace (a paste artifact, not a near-miss)', () => {
    render(<DeleteKitDialog {...props} />);
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: '  acme-intake  ' } });
    expect((screen.getByText('Delete permanently') as HTMLButtonElement).disabled).toBe(false);
  });

  it('names what is destroyed and offers the safe alternative', () => {
    render(<DeleteKitDialog {...props} />);
    // Archives are the non-obvious part -- an author who thinks this only
    // removes the live form would be wrong.
    expect(screen.getByText(/every archived version/)).toBeTruthy();
    expect(screen.getByText(/cannot be undone/)).toBeTruthy();
    // Matched on the WORD, not the phrasing: the copy was reworded when
    // deletion became graduated (bd 6zhaf), and what this pins is that the safe
    // alternative is still offered -- not one particular sentence.
    expect(screen.getByText(/unpublish/i)).toBeTruthy();
  });

  it('renders a server refusal IN PLACE, keeping the dialog open', () => {
    // The 409 explains why this form cannot be deleted; it has to be read next
    // to the form it names, not on a page-level error line after dismissal.
    render(
      <DeleteKitDialog
        {...props}
        error={'"acme-intake" has confirmation records: clients have agreed to this form.'}
      />,
    );
    expect(screen.getByText(/has confirmation records/)).toBeTruthy();
    expect(screen.getByText('Delete permanently')).toBeTruthy();  // still open
  });

  it('cancels on Escape and on the Cancel button', () => {
    const onCancel = vi.fn();
    render(<DeleteKitDialog {...props} onCancel={onCancel} />);

    fireEvent.keyDown(screen.getByLabelText(/Type/), { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it('does not fire while a delete is already in flight', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <DeleteKitDialog {...props} onConfirm={onConfirm} onCancel={onCancel} busy />,
    );
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'acme-intake' } });

    fireEvent.keyDown(screen.getByLabelText(/Type/), { key: 'Enter' });
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('submits on Enter once the id matches', () => {
    const onConfirm = vi.fn();
    render(<DeleteKitDialog {...props} onConfirm={onConfirm} />);
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'acme-intake' } });
    fireEvent.keyDown(screen.getByLabelText(/Type/), { key: 'Enter' });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
