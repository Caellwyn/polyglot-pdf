/**
 * RemoteCatalogue tests (bd polyglot-pdf-92qe.2): the hosted front door lists
 * kits from the editor API (drafts included -- the contractor work list), opens
 * a kit, flips status via the server (surfacing the promote-gate refusal), and
 * routes a 401 to the auth handler instead of a dead error banner.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../utils/remoteKitStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/remoteKitStore')>();
  return {
    ...actual,
    listRemoteKits: vi.fn(),
    loadRemoteSchema: vi.fn(),
    setRemoteStatus: vi.fn(),
  };
});

import { RemoteCatalogue } from './RemoteCatalogue';
import {
  AuthError, listRemoteKits, loadRemoteSchema, setRemoteStatus,
  type RemoteKitEntry,
} from '../utils/remoteKitStore';

const KITS: RemoteKitEntry[] = [
  { id: 'done-kit', label: 'Done Form', status: 'complete', hasSchema: true,
    hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
  { id: 'draft-kit', label: 'Draft Form', status: 'draft', hasSchema: true,
    hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
  { id: 'fresh-kit', label: 'Fresh Form', status: 'draft', hasSchema: false,
    hasPdf: true, schemaFile: 'schema.json', pdfFile: 'form.pdf' },
];

// A minimal schema whose 1 field is incomplete -> a deterministic review %.
const SCHEMA = {
  fields: [{ id: 'f1', name: 'F1', type: 'text', pdf_field_name: 'F1[0]' }],
  sections: [],
} as never;

beforeEach(() => {
  vi.mocked(listRemoteKits).mockResolvedValue([...KITS]);
  vi.mocked(loadRemoteSchema).mockResolvedValue(SCHEMA);
  vi.mocked(setRemoteStatus).mockResolvedValue(undefined);
});

afterEach(() => vi.clearAllMocks());

describe('RemoteCatalogue', () => {
  it('lists every kit from the API, drafts included', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());
    expect(screen.getByText('Done Form')).toBeInTheDocument();
    expect(screen.getByText('Fresh Form')).toBeInTheDocument();
    // Aggregate summary reflects statuses (1 complete, 1 in progress, 1 awaiting).
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('3 forms');
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('1 complete');
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('1 in progress');
    expect(screen.getByTestId('catalogue-summary')).toHaveTextContent('1 awaiting extraction');
  });

  it('opens a schema-bearing kit and disables a schemaless one', async () => {
    const onOpen = vi.fn();
    render(<RemoteCatalogue onOpenKit={onOpen} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Draft Form'));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'draft-kit' }));

    const freshCard = screen.getByText('Fresh Form').closest('button');
    expect(freshCard).toBeDisabled();
  });

  it('computes review progress from each kit schema (shared definition)', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    // The one-field schema is incomplete -> 0% bars on both schema kits.
    await waitFor(() => expect(screen.getAllByText('0%').length).toBe(2));
    expect(vi.mocked(loadRemoteSchema)).toHaveBeenCalledWith('done-kit');
    expect(vi.mocked(loadRemoteSchema)).toHaveBeenCalledWith('draft-kit');
    // The schemaless kit is never fetched.
    expect(vi.mocked(loadRemoteSchema)).not.toHaveBeenCalledWith('fresh-kit');
  });

  it('marks a draft complete via the server and refreshes', async () => {
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() => expect(setRemoteStatus).toHaveBeenCalledWith('draft-kit', 'complete'));
    // Refresh happened (list re-requested).
    await waitFor(() => expect(vi.mocked(listRemoteKits).mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => expect(screen.getByText(/marked complete/)).toBeInTheDocument());
  });

  it('surfaces the promote-gate refusal detail (422) as the error banner', async () => {
    vi.mocked(setRemoteStatus).mockRejectedValue(
      new Error('Schema does not validate against the form contract'),
    );
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() => expect(screen.getByText('Draft Form')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Mark complete'));
    await waitFor(() =>
      expect(screen.getByText(/does not validate/)).toBeInTheDocument());
  });

  it('routes a 401 to onAuthError instead of the error banner', async () => {
    vi.mocked(listRemoteKits).mockRejectedValue(new AuthError());
    const onAuthError = vi.fn();
    render(
      <RemoteCatalogue
        onOpenKit={() => {}} selectedKitId={null} role="editor"
        onAuthError={onAuthError}
      />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
    expect(screen.queryByText(/Invalid or missing/)).not.toBeInTheDocument();
  });

  it('routes a 401 DURING THE PROGRESS SCAN to onAuthError, not a schema error', async () => {
    // The list call succeeds, but the code is revoked before the per-kit
    // schema fetches -- the auth state must reach onAuthError, never masquerade
    // as "schema unreadable" on every card (fresh-eyes gap 1).
    vi.mocked(loadRemoteSchema).mockRejectedValue(new AuthError());
    const onAuthError = vi.fn();
    render(
      <RemoteCatalogue
        onOpenKit={() => {}} selectedKitId={null} role="editor"
        onAuthError={onAuthError}
      />,
    );
    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
    expect(screen.queryByText(/unreadable/)).not.toBeInTheDocument();
  });

  it('a plain per-kit schema failure still shows the unreadable notice (not auth)', async () => {
    vi.mocked(loadRemoteSchema).mockRejectedValue(new Error('boom'));
    const onAuthError = vi.fn();
    render(
      <RemoteCatalogue
        onOpenKit={() => {}} selectedKitId={null} role="editor"
        onAuthError={onAuthError}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByText(/unreadable/).length).toBeGreaterThan(0));
    expect(onAuthError).not.toHaveBeenCalled();
  });

  it('shows the empty-workspace message when the store has no kits', async () => {
    vi.mocked(listRemoteKits).mockResolvedValue([]);
    render(<RemoteCatalogue onOpenKit={() => {}} selectedKitId={null} role="editor" />);
    await waitFor(() =>
      expect(screen.getByText(/workspace is empty/)).toBeInTheDocument());
  });
});
