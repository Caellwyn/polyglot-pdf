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
    expect(screen.getByText(/unpublish it instead/i)).toBeTruthy();
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
