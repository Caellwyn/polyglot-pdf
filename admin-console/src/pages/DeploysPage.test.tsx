/**
 * DeploysPage (bd polyglot-pdf-ryx86, E4.7). Pins the bead's three exit
 * criteria (mocked adminApi, mutation-verified):
 *
 *   1. Deploy disabled/enabled by GET /admin/deploys/promotable for a
 *      gated target; the confirm dialog shows the FULL 40-char sha; POST
 *      fires exactly once per confirm even under a double-click.
 *   2. The table re-polls every 15s while a row is queued/working and
 *      stops once every row in the latest batch is terminal.
 *   3. The live-SHA panel renders an unreachable/unconfigured channel
 *      distinctly, never blank.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DeploysPage } from './DeploysPage';
import {
  AuthError, getDeployTargets, getPromotable, listDeploys, triggerDeploy,
  getChannelHealth, DEPLOY_STATUSES, DEPLOY_CHANNELS,
  type DeployTargetRow, type DeploymentRow, type ChannelHealth, type ListDeploysFilters,
} from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return {
    ...actual,
    getChannelHealth: vi.fn(),
    getDeployTargets: vi.fn(),
    getPromotable: vi.fn(),
    listDeploys: vi.fn(),
    triggerDeploy: vi.fn(),
  };
});

const noAuthExpired = () => false;

const SHA_A = 'a1'.repeat(20); // 40 chars, distinctive enough to catch truncation
const SHA_B = 'b2'.repeat(20);
const SHA_C = 'c3'.repeat(20);

const EDITOR_TARGET: DeployTargetRow = {
  target: 'editor', target_family: 'editor', channel: 'demo', gated: false,
};
const GATED_TARGET: DeployTargetRow = {
  target: 'backend-demo', target_family: 'backend', channel: 'demo', gated: true,
};
const TARGETS_FIXTURE = [EDITOR_TARGET, GATED_TARGET];

const HEALTHY: ChannelHealth = {
  channel: 'demo',
  backend: { configured: true, reachable: true, health: {}, version: { git_sha: 'demoSha123' } },
  admin_service: { version: '1.0.0', git_sha: 'adminSha', app_module: 'admin_backend.main' },
};

function baseRow(overrides: Partial<DeploymentRow>): DeploymentRow {
  return {
    id: 'd1', target: 'editor', target_family: 'editor', channel: 'demo',
    sha: SHA_A, ref: null, triggered_by: 'op-1', build_id: 'build-1',
    status: 'success', log_url: 'https://example.com/log', ts: 1_700_000_000,
    finished_at: 1_700_000_100,
    ...overrides,
  };
}

/** listDeploys is called for TWO different purposes on this page: the
 * unfiltered "latest successful per family" panel read (always passes
 * `limit`) and the table's own filtered read (never passes `limit`). Tests
 * that only care about one of the two mock this dispatcher rather than a
 * bare mockResolvedValue, so the other caller gets an inert empty list
 * instead of accidentally reusing rows meant for the other panel. */
function mockListDeploys(opts: {
  table?: (filters: ListDeploysFilters) => DeploymentRow[] | Promise<DeploymentRow[]>;
  panel?: DeploymentRow[];
}) {
  vi.mocked(listDeploys).mockImplementation(async (filters: ListDeploysFilters = {}) => {
    if (filters.limit) return opts.panel ?? [];
    return opts.table ? opts.table(filters) : [];
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getDeployTargets).mockResolvedValue(TARGETS_FIXTURE);
  vi.mocked(getChannelHealth).mockResolvedValue(HEALTHY);
  mockListDeploys({ table: () => [], panel: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

async function selectTargetAndSha(target: string, sha: string) {
  await screen.findByTestId('deploy-target-select');
  fireEvent.change(screen.getByLabelText('Deploy target'), { target: { value: target } });
  fireEvent.change(screen.getByLabelText('Commit sha'), { target: { value: sha } });
}

describe('DeploysPage -- exit criterion 1: gated trigger + confirm dialog', () => {
  it('disables Deploy for a gated target when the server says it is not promotable, with the plan wording shown', async () => {
    vi.mocked(getPromotable).mockResolvedValue({
      target: 'backend-demo', sha: SHA_A, target_family: 'backend',
      gated: true, promotable: false,
    });
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await selectTargetAndSha('backend-demo', SHA_A);

    await waitFor(() => expect(getPromotable).toHaveBeenCalledWith('backend-demo', SHA_A));
    expect(await screen.findByText(/deploy to staging first/)).toBeInTheDocument();
    expect(screen.getByTestId('deploy-button')).toBeDisabled();
  });

  it('enables Deploy for a gated target once the server says it is promotable', async () => {
    vi.mocked(getPromotable).mockResolvedValue({
      target: 'backend-demo', sha: SHA_A, target_family: 'backend',
      gated: true, promotable: true,
    });
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await selectTargetAndSha('backend-demo', SHA_A);

    await waitFor(() => expect(getPromotable).toHaveBeenCalledWith('backend-demo', SHA_A));
    expect(await screen.findByText(/Staging-verified/)).toBeInTheDocument();
    expect(screen.getByTestId('deploy-button')).not.toBeDisabled();
  });

  it('never calls promotable for a non-gated target, and Deploy is enabled once the sha is valid', async () => {
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await selectTargetAndSha('editor', SHA_A);

    await waitFor(() => expect(screen.getByTestId('deploy-button')).not.toBeDisabled());
    expect(getPromotable).not.toHaveBeenCalled();
  });

  it('the confirm dialog shows the FULL 40-character sha, never truncated', async () => {
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await selectTargetAndSha('editor', SHA_A);
    await waitFor(() => expect(screen.getByTestId('deploy-button')).not.toBeDisabled());

    fireEvent.click(screen.getByTestId('deploy-button'));

    const shown = await screen.findByTestId('deploy-confirm-sha');
    expect(shown.textContent).toBe(SHA_A);
    expect(shown.textContent).toHaveLength(40);
  });

  it('POST fires exactly once per confirm, even if Confirm is clicked twice before it resolves', async () => {
    let resolveTrigger!: (v: DeploymentRow & { request_id: string }) => void;
    vi.mocked(triggerDeploy).mockImplementation(() => new Promise((resolve) => {
      resolveTrigger = resolve;
    }));
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await selectTargetAndSha('editor', SHA_A);
    await waitFor(() => expect(screen.getByTestId('deploy-button')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('deploy-button'));
    await screen.findByTestId('deploy-confirm-dialog');

    const confirmButton = screen.getByTestId('deploy-confirm-button');
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);

    expect(triggerDeploy).toHaveBeenCalledTimes(1);
    expect(triggerDeploy).toHaveBeenCalledWith('editor', SHA_A);

    resolveTrigger({ ...baseRow({}), request_id: 'req-1' });
    await waitFor(() => expect(screen.queryByTestId('deploy-confirm-dialog')).not.toBeInTheDocument());
  });

  it('Cancel closes the dialog without ever calling triggerDeploy', async () => {
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await selectTargetAndSha('editor', SHA_A);
    await waitFor(() => expect(screen.getByTestId('deploy-button')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('deploy-button'));
    await screen.findByTestId('deploy-confirm-dialog');

    fireEvent.click(screen.getByTestId('deploy-cancel-button'));

    expect(screen.queryByTestId('deploy-confirm-dialog')).not.toBeInTheDocument();
    expect(triggerDeploy).not.toHaveBeenCalled();
  });

  it('re-validates the gated/promotable gate before POSTing if the target changes while the confirm dialog is still open', async () => {
    // The confirm panel is a sibling <div>, not a modal -- the target/sha
    // controls stay interactive while it is open. Open the dialog for a
    // valid NON-gated target, then switch to a GATED target the server has
    // not (yet) said is promotable, without closing the dialog first.
    vi.mocked(getPromotable).mockResolvedValue({
      target: 'backend-demo', sha: SHA_A, target_family: 'backend',
      gated: true, promotable: false,
    });
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await selectTargetAndSha('editor', SHA_A);
    await waitFor(() => expect(screen.getByTestId('deploy-button')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('deploy-button'));
    await screen.findByTestId('deploy-confirm-dialog');

    fireEvent.change(screen.getByLabelText('Deploy target'), { target: { value: 'backend-demo' } });
    await waitFor(() => expect(getPromotable).toHaveBeenCalledWith('backend-demo', SHA_A));

    const confirmButton = await screen.findByTestId('deploy-confirm-button');
    expect(confirmButton).toBeDisabled();
    fireEvent.click(confirmButton);

    expect(triggerDeploy).not.toHaveBeenCalled();
  });

  it('routes an AuthError on trigger to onAuthExpired instead of a generic error banner', async () => {
    vi.mocked(triggerDeploy).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<DeploysPage onAuthExpired={onAuthExpired} />);
    await selectTargetAndSha('editor', SHA_A);
    await waitFor(() => expect(screen.getByTestId('deploy-button')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('deploy-button'));
    await screen.findByTestId('deploy-confirm-dialog');
    fireEvent.click(screen.getByTestId('deploy-confirm-button'));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Sign-in required')).not.toBeInTheDocument();
  });
});

describe('DeploysPage -- exit criterion 2: polling table + status chips', () => {
  it('re-polls every 15s while a row is in flight, and stops once every row is terminal', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let tableCalls = 0;
    mockListDeploys({
      table: () => {
        tableCalls += 1;
        return [baseRow({ id: 'd1', status: tableCalls === 1 ? 'working' : 'success' })];
      },
    });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await screen.findByTestId('status-chip-working');
    expect(tableCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(15_000);
    await screen.findByTestId('status-chip-success');
    expect(tableCalls).toBe(2);

    // Every row in the latest batch is now terminal -- no third fetch is
    // ever scheduled, however long we wait.
    await vi.advanceTimersByTimeAsync(60_000);
    expect(tableCalls).toBe(2);
  });

  it('never polls at all when the initial batch is already all terminal', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let tableCalls = 0;
    mockListDeploys({
      table: () => {
        tableCalls += 1;
        return [baseRow({ id: 'd1', status: 'success' })];
      },
    });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await screen.findByTestId('status-chip-success');
    expect(tableCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(30_000);
    expect(tableCalls).toBe(1);
  });

  it('renders a distinct status chip for every status in the server closed set (derived from DEPLOY_STATUSES, not a hand list)', async () => {
    const rows = DEPLOY_STATUSES.map((status, i) => baseRow({ id: `d${i}`, status }));
    mockListDeploys({ table: () => rows });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await screen.findByTestId('deploys-table');

    for (const status of DEPLOY_STATUSES) {
      expect(await screen.findByTestId(`status-chip-${status}`)).toBeInTheDocument();
    }
  });

  it('the channel filter options are derived from DEPLOY_CHANNELS, not a hand-copied list', async () => {
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await screen.findByTestId('deploys-table');

    const select = screen.getByLabelText('Channel') as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    // '' is the "All channels" option this page adds on top of the closed set.
    expect(optionValues).toEqual(['', ...DEPLOY_CHANNELS]);
  });

  it('the channel/target filter submit re-queries with the chosen filters', async () => {
    mockListDeploys({ table: () => [] });
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    await screen.findByTestId('deploys-table');
    vi.mocked(listDeploys).mockClear();

    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'demo' } });
    fireEvent.change(screen.getByLabelText('Target'), { target: { value: 'editor' } });
    fireEvent.click(screen.getByRole('button', { name: 'Filter' }));

    await waitFor(() => expect(listDeploys).toHaveBeenCalledWith(
      expect.objectContaining({ channel: 'demo', target: 'editor' }),
    ));
  });

  it('renders "--" for a table row with a null sha (a foreign Cloud Build row) instead of throwing', async () => {
    mockListDeploys({
      table: () => [baseRow({ id: 'd-foreign', sha: null, target: null, channel: null, triggered_by: null, ts: null })],
    });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);

    const row = await screen.findByTestId('deploy-row-d-foreign');
    expect(row).toHaveTextContent('--');
  });
});

describe('DeploysPage -- exit criterion 3: live-SHA panel', () => {
  it('renders an unreachable channel distinctly, and an unconfigured one distinctly, never blank', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) => {
      if (channel === 'demo') {
        return {
          channel: 'demo',
          backend: { configured: true, reachable: false, health: null, version: null },
          admin_service: { version: '1.0.0', git_sha: 'adminSha', app_module: 'admin_backend.main' },
        };
      }
      return {
        channel: 'staging',
        backend: { configured: false, reachable: false, health: null, version: null },
        admin_service: { version: '1.0.0', git_sha: 'adminSha', app_module: 'admin_backend.main' },
      };
    });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByTestId('live-panel-demo-unreachable')).toBeInTheDocument();
    expect(await screen.findByTestId('live-panel-staging-unconfigured')).toBeInTheDocument();
    // Never blank: neither card is left in its permanent-loading state.
    expect(screen.queryByTestId('live-panel-demo-loading')).not.toBeInTheDocument();
    expect(screen.queryByTestId('live-panel-staging-loading')).not.toBeInTheDocument();
  });

  it('a card-level health fetch failure renders that card its own error, never blank', async () => {
    vi.mocked(getChannelHealth).mockImplementation(async (channel) => {
      if (channel === 'demo') throw new Error('admin service unavailable');
      return HEALTHY;
    });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);

    expect(await screen.findByTestId('live-panel-demo-error')).toHaveTextContent('admin service unavailable');
    expect(await screen.findByTestId('live-panel-staging-reachable')).toBeInTheDocument();
  });

  it('shows the NEWEST successful deploy per target family (rows arrive newest-first), beside the health cards', async () => {
    mockListDeploys({
      panel: [
        // Newest-first, as the real route documents. Two successes for
        // "backend" -- the OLDER one (d4) must never win, which is what
        // catches a dedup that keeps the LAST-seen row instead of the
        // FIRST (newest) one for a family.
        baseRow({ id: 'd1', target_family: 'backend', channel: 'demo', sha: SHA_A, status: 'success', ts: 200 }),
        baseRow({ id: 'd2', target_family: 'editor', channel: 'demo', sha: SHA_B, status: 'success', ts: 100 }),
        baseRow({ id: 'd3', target_family: 'backend', channel: 'staging', sha: SHA_B, status: 'failure', ts: 300 }),
        baseRow({ id: 'd4', target_family: 'backend', channel: 'demo', sha: SHA_C, status: 'success', ts: 50 }),
      ],
    });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);

    const backendEntry = await screen.findByTestId('latest-family-backend');
    expect(backendEntry).toHaveTextContent(SHA_A.slice(0, 12));
    expect(backendEntry).not.toHaveTextContent(SHA_C.slice(0, 12));
    const editorEntry = await screen.findByTestId('latest-family-editor');
    expect(editorEntry).toHaveTextContent(SHA_B.slice(0, 12));
  });

  it('a foreign Cloud Build row (null sha/target_family -- deploy_webhook.py\'s own shape for a build with no _SHA/_TARGET substitution) renders "--" instead of throwing', async () => {
    mockListDeploys({
      panel: [
        baseRow({
          id: 'd-foreign', target: null, target_family: null, channel: null,
          sha: null, triggered_by: null, ts: null, status: 'success',
        }),
        baseRow({ id: 'd1', target_family: 'backend', channel: 'demo', sha: SHA_A, status: 'success', ts: 200 }),
      ],
    });

    render(<DeploysPage onAuthExpired={noAuthExpired} />);

    // '(unknown)' mirrors DeploysPage.tsx's own UNKNOWN_FAMILY fallback key
    // for a row whose target_family is null.
    const unknownEntry = await screen.findByTestId('latest-family-(unknown)');
    expect(unknownEntry).toHaveTextContent('--');
    const backendEntry = await screen.findByTestId('latest-family-backend');
    expect(backendEntry).toHaveTextContent(SHA_A.slice(0, 12));
  });
});
