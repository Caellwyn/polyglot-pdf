// SectionManager behavior (bd polyglot-pdf-6cfu.3): each control computes the
// op via sectionOps and hands App ONE atomic patch; destructive ops confirm.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SectionManager } from './SectionManager';
import type { FormField, FormSection } from '../types/schema';

const field = (id: string, section_id: string): FormField =>
  ({ id, name: id, type: 'text', section_id } as unknown as FormField);

const SECTIONS: FormSection[] = [
  { id: 'sec_a', label: 'Alpha', order: 1, fields: ['f1'] },
  { id: 'sec_to_review_p1', label: 'To review', order: 2, fields: ['f2'] },
];
const FIELDS = [field('f1', 'sec_a'), field('f2', 'sec_to_review_p1')];

function renderManager(over: Partial<React.ComponentProps<typeof SectionManager>> = {}) {
  const onApply = vi.fn();
  const onRegenerate = vi.fn();
  const onClose = vi.fn();
  render(
    <SectionManager
      fields={FIELDS}
      sections={SECTIONS}
      parts={[]}
      canRegenerate={false}
      onApply={onApply}
      onRegenerate={onRegenerate}
      onClose={onClose}
      {...over}
    />,
  );
  return { onApply, onRegenerate, onClose };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('SectionManager', () => {
  it('renders every section with a re-file badge on a To-review one', () => {
    renderManager();
    expect(screen.getByDisplayValue('Alpha')).toBeInTheDocument();
    expect(screen.getByDisplayValue('To review')).toBeInTheDocument();
    expect(screen.getByText('re-file required')).toBeInTheDocument();
  });

  it('adds a section from the label input', () => {
    const { onApply } = renderManager();
    fireEvent.change(screen.getByLabelText('New section label'),
      { target: { value: 'Gamma' } });
    fireEvent.click(screen.getByText('Add section'));
    const patch = onApply.mock.calls[0][0];
    expect(patch.sections.map((s: FormSection) => s.id))
      .toEqual(['sec_a', 'sec_to_review_p1', 'sec_gamma']);
  });

  it('renames on blur when the label changed', () => {
    const { onApply } = renderManager();
    const input = screen.getByDisplayValue('Alpha');
    fireEvent.change(input, { target: { value: 'Alpha 2' } });
    fireEvent.blur(input);
    const patch = onApply.mock.calls[0][0];
    expect(patch.sections[0]).toMatchObject({ id: 'sec_a', label: 'Alpha 2' });
  });

  it('does not rename on blur when the label is unchanged', () => {
    const { onApply } = renderManager();
    fireEvent.blur(screen.getByDisplayValue('Alpha'));
    expect(onApply).not.toHaveBeenCalled();
  });

  it('merges behind a confirm; cancel is a no-op', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { onApply } = renderManager();
    fireEvent.change(screen.getByLabelText('Merge To review into'),
      { target: { value: 'sec_a' } });
    expect(confirm).toHaveBeenCalled();
    expect(onApply).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.change(screen.getByLabelText('Merge To review into'),
      { target: { value: 'sec_a' } });
    const patch = onApply.mock.calls[0][0];
    expect(patch.sections.map((s: FormSection) => s.id)).toEqual(['sec_a']);
    expect(patch.sections[0].fields).toEqual(['f1', 'f2']);
    expect(patch.fields.find((f: FormField) => f.id === 'f2')!.section_id)
      .toBe('sec_a');
  });

  it('removes behind a confirm, orphaning the fields', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { onApply } = renderManager();
    fireEvent.click(screen.getByLabelText('Remove Alpha'));
    const patch = onApply.mock.calls[0][0];
    expect(patch.sections.map((s: FormSection) => s.id))
      .toEqual(['sec_to_review_p1']);
    expect(patch.fields.find((f: FormField) => f.id === 'f1')!.section_id)
      .toBe('');
  });

  it('shows Regenerate divisions only when allowed, wired to onRegenerate', () => {
    renderManager();
    expect(screen.queryByText('Regenerate divisions')).toBeNull();
  });

  it('fires onRegenerate when allowed', () => {
    const { onRegenerate } = renderManager({ canRegenerate: true });
    fireEvent.click(screen.getByText('Regenerate divisions'));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it('closes via the Close button', () => {
    const { onClose } = renderManager();
    fireEvent.click(screen.getByText('Close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
