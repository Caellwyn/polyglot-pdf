/**
 * AuditLogPage (bd polyglot-pdf-b6943, fresh-eyes round-2 gap): pins the
 * auth-eviction routing wired at the same time as ConfigEditorPage's (same
 * commit, same pattern -- CLAUDE.md scar #8: fix the whole set, not one
 * member), plus the filter/cursor pagination logic and row rendering that
 * had no coverage at all.
 *
 * Mirrors ConfigEditorPage.test.tsx's mocking approach: keep the real
 * AuthError/ForbiddenError classes (onAuthExpired branches on instanceof),
 * mock only the network calls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AuditLogPage } from './AuditLogPage';
import { AuthError, ForbiddenError, listAuditRows } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return { ...actual, listAuditRows: vi.fn() };
});

const noAuthExpired = () => false;

const PAGE_1 = {
  rows: [
    { doc_id: 'a1', ts: 1700000000, action: 'config.set', actor_email: 'a@example.com', channel: 'staging', target: 'LINK_MINTING_ENABLED', state: 'ok' },
  ],
  next_cursor: 'cursor-2',
};

const PAGE_2 = {
  rows: [
    { doc_id: 'a2', ts: 1700000100, action: 'config.set', actor_email: 'b@example.com', channel: 'demo', target: 'STALE_KEY', state: 'ok' },
  ],
  next_cursor: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listAuditRows).mockResolvedValue(PAGE_1);
});

describe('AuditLogPage', () => {
  it('loads the first page on mount and renders its rows', async () => {
    render(<AuditLogPage onAuthExpired={noAuthExpired} />);

    await waitFor(() => expect(listAuditRows).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('config.set')).toBeInTheDocument();
    expect(screen.getByText('a@example.com')).toBeInTheDocument();
    expect(screen.getByText('LINK_MINTING_ENABLED')).toBeInTheDocument();
  });

  it('shows a "Load more" button only while next_cursor is non-null, and appends rows on click', async () => {
    render(<AuditLogPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('config.set');

    const loadMore = screen.getByRole('button', { name: 'Load more' });
    vi.mocked(listAuditRows).mockResolvedValueOnce(PAGE_2);
    fireEvent.click(loadMore);

    // Second call carries the first page's cursor.
    await waitFor(() => expect(listAuditRows).toHaveBeenCalledTimes(2));
    expect(vi.mocked(listAuditRows).mock.calls[1][0]).toMatchObject({ cursor: 'cursor-2' });

    // Rows APPEND (page 1's row is still present alongside page 2's).
    expect(await screen.findByText('b@example.com')).toBeInTheDocument();
    expect(screen.getByText('a@example.com')).toBeInTheDocument();

    // next_cursor is now null -- "Load more" must disappear.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument());
  });

  it('does not render "Load more" when the first page already has no next_cursor', async () => {
    vi.mocked(listAuditRows).mockResolvedValue(PAGE_2);
    render(<AuditLogPage onAuthExpired={noAuthExpired} />);

    await screen.findByText('b@example.com');
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('Apply resets the list to a fresh first page rather than appending', async () => {
    render(<AuditLogPage onAuthExpired={noAuthExpired} />);
    await screen.findByText('config.set');

    vi.mocked(listAuditRows).mockResolvedValueOnce(PAGE_2);
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'config.get' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(listAuditRows).toHaveBeenCalledTimes(2));
    expect(vi.mocked(listAuditRows).mock.calls[1][0]).toMatchObject({ action: 'config.get' });

    // The Apply re-query REPLACES rows -- page 1's row must be gone, not
    // appended alongside page 2's.
    await waitFor(() => expect(screen.getByText('b@example.com')).toBeInTheDocument());
    expect(screen.queryByText('a@example.com')).not.toBeInTheDocument();
  });

  it('routes a 403 on the initial load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(listAuditRows).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<AuditLogPage onAuthExpired={onAuthExpired} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(ForbiddenError);
    expect(screen.queryByText('Access was revoked')).not.toBeInTheDocument();
  });

  it('routes a 401 on "Load more" to onAuthExpired instead of the generic error banner', async () => {
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<AuditLogPage onAuthExpired={onAuthExpired} />);
    await screen.findByText('config.set');

    vi.mocked(listAuditRows).mockRejectedValueOnce(new AuthError('Sign-in required'));
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(AuthError);
    expect(screen.queryByText(/Could not load more rows/)).not.toBeInTheDocument();
  });

  it('shows the generic error banner when the failure is not an auth error', async () => {
    vi.mocked(listAuditRows).mockRejectedValueOnce(new Error('Firestore is unavailable'));
    render(<AuditLogPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByText('Firestore is unavailable')).toBeInTheDocument();
  });

  it('renders a "No audit rows" placeholder when the page is empty', async () => {
    vi.mocked(listAuditRows).mockResolvedValue({ rows: [], next_cursor: null });
    render(<AuditLogPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByText('No audit rows.')).toBeInTheDocument();
  });
});
