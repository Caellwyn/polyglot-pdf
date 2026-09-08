/**
 * ConfigEditorPage (bd polyglot-pdf-b6943): the round-trip test the exit
 * criteria name -- "the config editor round trip against a mocked API".
 *
 * Pins: load renders the channel's current values; Save PUTs exactly ONE key
 * (config_routes.py's ConfigPutRequest contract -- a whole-doc PUT would let
 * a stale value in the form clobber a key someone else just set); after a
 * successful save the page RE-READS the channel (GET) so the screen reflects
 * what the server actually stored, not merely the form's draft; unknown_keys
 * render read-only, never as an editable row a save could target; a
 * mid-session AuthError/ForbiddenError routes to onAuthExpired instead of
 * this page's own generic error banner (fresh-eyes finding: the gate's
 * refused-screen machinery existed but nothing ever called it).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConfigEditorPage } from './ConfigEditorPage';
import { AuthError, ForbiddenError, getChannelConfig, setChannelConfigKey } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  // Keep the REAL error classes -- onAuthExpired branches on instanceof.
  return { ...actual, getChannelConfig: vi.fn(), setChannelConfigKey: vi.fn() };
});

const STAGING_CONFIG = {
  channel: 'staging',
  values: { LINK_MINTING_ENABLED: false, STALE_KEY: 'orphan' },
  known_keys: ['LINK_MINTING_ENABLED'],
  unknown_keys: ['STALE_KEY'],
};

const noAuthExpired = () => false;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getChannelConfig).mockResolvedValue(STAGING_CONFIG);
});

describe('ConfigEditorPage', () => {
  it('loads the default channel and renders its known + unknown keys', async () => {
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledWith('staging'));
    expect(await screen.findByLabelText('LINK_MINTING_ENABLED')).toHaveValue('false');
    expect(screen.getByText('STALE_KEY')).toBeInTheDocument();
    expect(screen.getByText('orphan')).toBeInTheDocument();
    // Unknown keys are read-only: no input rendered for them.
    expect(screen.queryByLabelText('STALE_KEY')).not.toBeInTheDocument();
  });

  it('switching channel re-fetches that channel\'s config', async () => {
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);
    await screen.findByLabelText('LINK_MINTING_ENABLED');

    vi.mocked(getChannelConfig).mockResolvedValue({
      channel: 'demo',
      values: { LINK_MINTING_ENABLED: true },
      known_keys: ['LINK_MINTING_ENABLED'],
      unknown_keys: [],
    });
    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'demo' } });

    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledWith('demo'));
    await waitFor(() =>
      expect(screen.getByLabelText('LINK_MINTING_ENABLED')).toHaveValue('true'));
  });

  it('Save PUTs exactly the one edited key, then re-reads the channel', async () => {
    vi.mocked(setChannelConfigKey).mockResolvedValue({
      channel: 'staging',
      key: 'LINK_MINTING_ENABLED',
      before: false,
      after: true,
      request_id: 'req-1',
    });
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const input = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(input, { target: { value: 'true' } });

    // The re-read after save should reflect the NEW server-stored value.
    vi.mocked(getChannelConfig).mockResolvedValue({
      channel: 'staging',
      values: { LINK_MINTING_ENABLED: true, STALE_KEY: 'orphan' },
      known_keys: ['LINK_MINTING_ENABLED'],
      unknown_keys: ['STALE_KEY'],
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(setChannelConfigKey).toHaveBeenCalledWith('staging', 'LINK_MINTING_ENABLED', 'true'));
    // Exactly one PUT -- never a whole-doc write.
    expect(setChannelConfigKey).toHaveBeenCalledTimes(1);

    // getChannelConfig called again (initial load + post-save re-read).
    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Saved LINK_MINTING_ENABLED.')).toBeInTheDocument();
  });

  it('shows the server error and does not re-read on a failed save', async () => {
    vi.mocked(setChannelConfigKey).mockRejectedValue(
      new Error("'nope' is not a valid value for LINK_MINTING_ENABLED"));
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const input = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(input, { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/not a valid value/)).toBeInTheDocument();
    // Only the initial load read the channel -- a failed write must not
    // trigger the success re-read.
    expect(getChannelConfig).toHaveBeenCalledTimes(1);
  });

  // Fresh-eyes finding on bd polyglot-pdf-b6943: SignInGate's refusedReason
  // prop and its dedicated test existed, but nothing in the app ever
  // constructed it -- a mid-session 401/403 surfaced as this page's generic
  // red error string with no path back to sign-in. Pin the fix: this page
  // routes an AuthError/ForbiddenError to onAuthExpired FIRST, and shows no
  // generic banner of its own when onAuthExpired reports it handled the
  // failure.
  it('routes a 403 on load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(getChannelConfig).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<ConfigEditorPage onAuthExpired={onAuthExpired} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(ForbiddenError);
    expect(screen.queryByText('Access was revoked')).not.toBeInTheDocument();
  });

  it('routes a 401 on save to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(setChannelConfigKey).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<ConfigEditorPage onAuthExpired={onAuthExpired} />);

    const input = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(input, { target: { value: 'true' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(AuthError);
    expect(screen.queryByText(/Could not save/)).not.toBeInTheDocument();
  });
});
