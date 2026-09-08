/**
 * ConfigEditorPage (bd polyglot-pdf-b6943): the round-trip test the exit
 * criteria name -- "the config editor round trip against a mocked API".
 *
 * Pins: load renders the channel's current values; Save PUTs exactly ONE key
 * (config_routes.py's ConfigPutRequest contract -- a whole-doc PUT would let
 * a stale value in the form clobber a key someone else just set); after a
 * successful save the page RE-READS the channel (GET) so the screen reflects
 * what the server actually stored, not merely the form's draft; unknown_keys
 * render read-only, never as an editable row a save could target.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConfigEditorPage } from './ConfigEditorPage';
import { getChannelConfig, setChannelConfigKey } from '../utils/adminApi';

vi.mock('../utils/adminApi', () => ({
  getChannelConfig: vi.fn(),
  setChannelConfigKey: vi.fn(),
}));

const STAGING_CONFIG = {
  channel: 'staging',
  values: { LINK_MINTING_ENABLED: false, STALE_KEY: 'orphan' },
  known_keys: ['LINK_MINTING_ENABLED'],
  unknown_keys: ['STALE_KEY'],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getChannelConfig).mockResolvedValue(STAGING_CONFIG);
});

describe('ConfigEditorPage', () => {
  it('loads the default channel and renders its known + unknown keys', async () => {
    render(<ConfigEditorPage />);

    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledWith('staging'));
    expect(await screen.findByLabelText('LINK_MINTING_ENABLED')).toHaveValue('false');
    expect(screen.getByText('STALE_KEY')).toBeInTheDocument();
    expect(screen.getByText('orphan')).toBeInTheDocument();
    // Unknown keys are read-only: no input rendered for them.
    expect(screen.queryByLabelText('STALE_KEY')).not.toBeInTheDocument();
  });

  it('switching channel re-fetches that channel\'s config', async () => {
    render(<ConfigEditorPage />);
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
    render(<ConfigEditorPage />);

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
    render(<ConfigEditorPage />);

    const input = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(input, { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/not a valid value/)).toBeInTheDocument();
    // Only the initial load read the channel -- a failed write must not
    // trigger the success re-read.
    expect(getChannelConfig).toHaveBeenCalledTimes(1);
  });
});
