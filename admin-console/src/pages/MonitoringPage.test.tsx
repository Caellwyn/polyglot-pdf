/**
 * MonitoringPage (bd polyglot-pdf-i6dlb, E3.11b). Pins the exit criterion:
 * "per-channel cards from GET /admin/health showing reachable/version SHA
 * for the demo and staging backends plus the admin service itself; an
 * unreachable or unconfigured channel renders a distinct state, never a
 * blank card" (mocked API, mutation-verified).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MonitoringPage } from './MonitoringPage';
import { AuthError, getChannelHealth } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return { ...actual, getChannelHealth: vi.fn() };
});

const noAuthExpired = () => false;

function reachableHealth(channel: 'demo' | 'staging') {
  return {
    channel,
    backend: {
      configured: true,
      reachable: true,
      health: { status: 'ok' },
      version: { git_sha: 'abc123' },
    },
    admin_service: { version: '1.0.0', git_sha: 'def456', app_module: 'admin_backend.main' },
  };
}

function unconfiguredHealth(channel: 'demo' | 'staging') {
  return {
    channel,
    backend: { configured: false, reachable: false, health: null, version: null },
    admin_service: { version: '1.0.0', git_sha: 'def456', app_module: 'admin_backend.main' },
  };
}

function unreachableHealth(channel: 'demo' | 'staging') {
  return {
    channel,
    backend: { configured: true, reachable: false, health: null, version: null },
    admin_service: { version: '1.0.0', git_sha: 'def456', app_module: 'admin_backend.main' },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('MonitoringPage', () => {
  it('calls GET /admin/health for both channels on mount', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) => reachableHealth(channel));
    render(<MonitoringPage onAuthExpired={noAuthExpired} />);

    await waitFor(() => expect(getChannelHealth).toHaveBeenCalledWith('demo'));
    await waitFor(() => expect(getChannelHealth).toHaveBeenCalledWith('staging'));
    expect(getChannelHealth).toHaveBeenCalledTimes(2);
  });

  it('a reachable channel shows Reachable and the backend version sha', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) => reachableHealth(channel));
    render(<MonitoringPage onAuthExpired={noAuthExpired} />);

    const demoCard = await screen.findByTestId('health-card-demo-reachable');
    expect(demoCard).toHaveTextContent('abc123');
    expect(screen.getByTestId('health-card-demo')).toHaveTextContent('def456');
  });

  it('an unconfigured channel renders a distinct "not configured" state, never blank', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) =>
      channel === 'demo' ? unconfiguredHealth(channel) : reachableHealth(channel));
    render(<MonitoringPage onAuthExpired={noAuthExpired} />);

    const demoCard = await screen.findByTestId('health-card-demo-unconfigured');
    expect(demoCard).toHaveTextContent('Not configured');
    // Never collapsed into the same rendering as unreachable.
    expect(screen.queryByTestId('health-card-demo-unreachable')).not.toBeInTheDocument();
  });

  it('an unreachable (but configured) channel renders a distinct state from unconfigured', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) =>
      channel === 'staging' ? unreachableHealth(channel) : reachableHealth(channel));
    render(<MonitoringPage onAuthExpired={noAuthExpired} />);

    const stagingCard = await screen.findByTestId('health-card-staging-unreachable');
    expect(stagingCard).toHaveTextContent('Unreachable');
    expect(screen.queryByTestId('health-card-staging-unconfigured')).not.toBeInTheDocument();
  });

  it('one channel throwing does not blank the other channel\'s card (never a blank card)', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) => {
      if (channel === 'demo') throw new Error('admin service unavailable');
      return reachableHealth(channel);
    });
    render(<MonitoringPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByTestId('health-card-demo-error')).toHaveTextContent(
      'admin service unavailable',
    );
    expect(await screen.findByTestId('health-card-staging-reachable')).toBeInTheDocument();
  });

  it('routes an AuthError to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(getChannelHealth).mockRejectedValue(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<MonitoringPage onAuthExpired={onAuthExpired} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalled());
    expect(screen.queryByText('Sign-in required')).not.toBeInTheDocument();
  });

  it('refresh calls getChannelHealth again for that channel only', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) => reachableHealth(channel));
    render(<MonitoringPage onAuthExpired={noAuthExpired} />);
    await screen.findByTestId('health-card-demo-reachable');
    vi.mocked(getChannelHealth).mockClear();

    const demoCard = screen.getByTestId('health-card-demo');
    const refreshButton = demoCard.querySelector('button')!;
    fireEvent.click(refreshButton);

    await waitFor(() => expect(getChannelHealth).toHaveBeenCalledTimes(1));
    expect(getChannelHealth).toHaveBeenCalledWith('demo');
  });
});
