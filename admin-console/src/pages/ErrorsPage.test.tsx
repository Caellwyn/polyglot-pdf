/**
 * ErrorsPage (bd polyglot-pdf-i6dlb, E3.11b). Pins the exit criterion:
 * "channel tabs over GET /admin/errors showing count, first/last seen,
 * type and top frame; nothing else from the payload is rendered (the
 * allowlist is pinned by a test that feeds an extra `message` key and
 * asserts it never reaches the DOM)" (mocked API, mutation-verified).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ErrorsPage } from './ErrorsPage';
import { AuthError, getChannelErrors } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return { ...actual, getChannelErrors: vi.fn() };
});

const noAuthExpired = () => false;

// This group carries an extra `message` key the real API response would
// never structurally have on the TYPED ErrorGroup shape -- adminApi.ts's
// getChannelErrors return type has no `message` field, so this cast
// simulates a raw payload carrying it anyway (a future accidental echo of
// the FULL Cloud Error Reporting representative), proving the page's own
// render path never reaches it even when the object HAS the key at
// runtime, not just that TypeScript would refuse to type it.
const SENTINEL_MESSAGE = 'SENTINEL_PII_A1234_do_not_render_me';
const GROUP_WITH_EXTRA_KEY = {
  group_id: 'g1', count: 3, first_seen_time: '2026-09-01T00:00:00Z',
  last_seen_time: '2026-09-05T00:00:00Z', error_type: 'ValueError',
  top_frame: { file_path: 'backend/adapters/live_ai_gemini.py', line_number: 3012, function_name: 'do_thing' },
  message: SENTINEL_MESSAGE,
} as unknown as import('../utils/adminApi').ErrorGroup;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ErrorsPage', () => {
  it('loads GET /admin/errors for the demo channel on mount', async () => {
    vi.mocked(getChannelErrors).mockResolvedValue({ channel: 'demo', service: 'polyglot-backend', groups: [] });
    render(<ErrorsPage onAuthExpired={noAuthExpired} />);
    await waitFor(() => expect(getChannelErrors).toHaveBeenCalledWith('demo'));
    expect(getChannelErrors).toHaveBeenCalledTimes(1);
  });

  it('switching the channel tab loads the other channel', async () => {
    vi.mocked(getChannelErrors).mockResolvedValue({ channel: 'demo', service: 'polyglot-backend', groups: [] });
    render(<ErrorsPage onAuthExpired={noAuthExpired} />);
    await waitFor(() => expect(getChannelErrors).toHaveBeenCalledWith('demo'));

    fireEvent.click(screen.getByRole('button', { name: 'staging' }));
    await waitFor(() => expect(getChannelErrors).toHaveBeenCalledWith('staging'));
  });

  it('renders count, first/last seen, type, and top frame for each group', async () => {
    vi.mocked(getChannelErrors).mockResolvedValue({
      channel: 'demo', service: 'polyglot-backend',
      groups: [{
        group_id: 'g1', count: 7, first_seen_time: '2026-09-01T00:00:00Z',
        last_seen_time: '2026-09-05T00:00:00Z', error_type: 'ValueError',
        top_frame: { file_path: 'backend/adapters/live_ai_gemini.py', line_number: 3012, function_name: 'do_thing' },
      }],
    });
    render(<ErrorsPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByText('ValueError')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('2026-09-01T00:00:00Z')).toBeInTheDocument();
    expect(screen.getByText('2026-09-05T00:00:00Z')).toBeInTheDocument();
    expect(screen.getByText(/backend\/adapters\/live_ai_gemini\.py:3012/)).toBeInTheDocument();
  });

  it('an empty groups list shows a "no errors" message, not a blank table', async () => {
    vi.mocked(getChannelErrors).mockResolvedValue({ channel: 'demo', service: 'polyglot-backend', groups: [] });
    render(<ErrorsPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByText('No errors reported for this channel.')).toBeInTheDocument();
  });

  it('a failed load shows the server error message', async () => {
    vi.mocked(getChannelErrors).mockRejectedValueOnce(new Error('error reporting unavailable'));
    render(<ErrorsPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByText('error reporting unavailable')).toBeInTheDocument();
  });

  it('routes an AuthError to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(getChannelErrors).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<ErrorsPage onAuthExpired={onAuthExpired} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Sign-in required')).not.toBeInTheDocument();
  });

  it('an extra `message` key on the payload never reaches the DOM (allowlist pin)', async () => {
    vi.mocked(getChannelErrors).mockResolvedValue({
      channel: 'demo', service: 'polyglot-backend', groups: [GROUP_WITH_EXTRA_KEY],
    });
    render(<ErrorsPage onAuthExpired={noAuthExpired} />);

    // The row itself renders fine (using only the allowlisted fields)...
    expect(await screen.findByText('ValueError')).toBeInTheDocument();
    // ...but the sentinel value from the extra `message` key is nowhere in
    // the rendered page, not even truncated or partially matched.
    expect(document.body.textContent).not.toContain(SENTINEL_MESSAGE);
    expect(screen.queryByText(SENTINEL_MESSAGE)).not.toBeInTheDocument();
  });
});
