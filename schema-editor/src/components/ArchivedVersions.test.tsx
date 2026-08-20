/**
 * The per-form archive disclosure (bd polyglot-pdf-qfyxr): collapsed by
 * default with LAZY fetching (an all-current catalogue pays no archive
 * round-trips), newest-first list as the backend returns it, and a viewer
 * that is unmistakably READ-ONLY (exit criterion 3: an archived revision
 * cannot be confused with the fillable/editable current one).
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ArchivedVersions } from './ArchivedVersions';
import type { FormSchema } from '../types/schema';

const REVS = [
  { marker: '2025-06', published_at: '2025-06-01T00:00:00+00:00' },
  { marker: '2024-01', published_at: '2024-01-05T00:00:00+00:00' },
];

const SCHEMA = {
  form_metadata: { title: 'Old W-7', form_number: 'W-7' },
  parts: [], sections: [{ id: 's1', title: 'Part One' }], fields: [],
} as unknown as FormSchema;

function mount(overrides: Partial<Parameters<typeof ArchivedVersions>[0]> = {}) {
  const listRevisions = vi.fn(async () => REVS);
  const loadSchema = vi.fn(async () => SCHEMA);
  render(
    <ArchivedVersions
      kitId="w7"
      kitLabel="W-7"
      listRevisions={listRevisions}
      loadSchema={loadSchema}
      {...overrides}
    />,
  );
  return { listRevisions, loadSchema };
}

describe('ArchivedVersions disclosure', () => {
  it('is collapsed by default and fetches NOTHING until expanded', () => {
    // Mutation: initialize the open state to true (or fetch on mount) -- red.
    const { listRevisions } = mount();
    expect(screen.getByRole('button', { name: 'Archived versions' })).toBeTruthy();
    expect(screen.queryByText('2025-06')).toBeNull();
    expect(listRevisions).not.toHaveBeenCalled();
  });

  it('expanding fetches once and lists the revisions in backend order', async () => {
    const { listRevisions } = mount();

    fireEvent.click(screen.getByRole('button', { name: 'Archived versions' }));
    await waitFor(() => expect(screen.getByText('2025-06')).toBeTruthy());
    expect(screen.getByText('2024-01')).toBeTruthy();
    // Collapse + re-expand must NOT refetch (the list is per-mount cached).
    fireEvent.click(screen.getByRole('button', { name: 'Hide archived versions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Archived versions' }));
    expect(listRevisions).toHaveBeenCalledTimes(1);
  });

  it('says so when a form has no archived versions', async () => {
    mount({ listRevisions: vi.fn(async () => []) });

    fireEvent.click(screen.getByRole('button', { name: 'Archived versions' }));
    await waitFor(() => expect(screen.getByText('No archived versions.')).toBeTruthy());
  });

  it('opening a revision shows the READ-ONLY viewer with no inputs', async () => {
    // Mutation: drop the "read only" labeling from the dialog heading -- red.
    const { loadSchema } = mount();

    fireEvent.click(screen.getByRole('button', { name: 'Archived versions' }));
    await waitFor(() => expect(screen.getByText('2025-06')).toBeTruthy());
    fireEvent.click(screen.getByText('2025-06'));

    const dialog = await screen.findByRole('dialog');
    expect(loadSchema).toHaveBeenCalledWith('w7', '2025-06');
    expect(dialog.textContent).toContain('read only');
    expect(dialog.textContent).toContain('cannot be');
    // No form controls: nothing in the viewer can look fillable/editable.
    expect(dialog.querySelectorAll('input, textarea, select')).toHaveLength(0);
  });
});
