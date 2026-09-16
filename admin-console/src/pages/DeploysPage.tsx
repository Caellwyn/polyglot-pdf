import React from 'react';
import {
  getChannelHealth, MONITORING_CHANNELS,
  getDeployTargets, getPromotable, listDeploys, triggerDeploy,
  isDeployInFlight, DEPLOY_STATUSES, DEPLOY_CHANNELS,
  type ChannelHealth, type MonitoringChannel,
  type DeployTargetRow, type PromotableResult, type DeploymentRow, type DeployStatus,
  type DeployChannel,
} from '../utils/adminApi';
import { PageIntro } from '../components/PageIntro';

interface DeploysPageProps {
  /** Called first on every catch -- see UsersPage.tsx's identical prop for
   * the full rationale. */
  onAuthExpired: (err: unknown) => boolean;
}

/** A git commit SHA, and nothing looser -- mirrors deploy_routes.py's own
 * `_SHA_RE`: exactly 40 lowercase hex characters. Checked client-side so
 * the promotable preview and the Deploy button's enabled state do not fire
 * a network call (or a misleadingly-enabled button) on a half-typed sha;
 * the server's own 422 remains the validation authority. */
const SHA_RE = /^[0-9a-f]{40}$/;

/** How often the table re-polls GET /admin/deploys while a row is queued
 * or working (exit criterion 2). */
const POLL_INTERVAL_MS = 15_000;

function formatTs(ts: number | null): string {
  if (ts === null) return '--';
  return new Date(ts * 1000).toISOString();
}

/** A `DeploymentRow.sha` is nullable (a foreign Cloud Build with no
 * `_SHA` substitution lands a row with `sha: null` -- see DeploymentRow's
 * own doc comment in adminApi.ts): never call `.slice` on it directly. */
function shortSha(sha: string | null): string {
  if (sha === null) return '--';
  return sha.slice(0, 12);
}

/** Tailwind classes per status -- covers every DEPLOY_STATUSES entry
 * (derived off that same closed set below, never a second hand list), plus
 * a neutral fallback for a status value this console has not been taught
 * yet (the server's set is closed, but a stale console build must not
 * crash on a future addition). */
const STATUS_CHIP_CLASSES: Record<DeployStatus, string> = {
  queued: 'bg-gray-100 text-gray-700',
  working: 'bg-blue-100 text-blue-800',
  success: 'bg-green-100 text-green-800',
  failure: 'bg-red-100 text-red-800',
  cancelled: 'bg-yellow-100 text-yellow-800',
};

function StatusChip({ status }: { status: string }) {
  const known = (DEPLOY_STATUSES as readonly string[]).includes(status);
  const classes = known
    ? STATUS_CHIP_CLASSES[status as DeployStatus]
    : 'bg-gray-100 text-gray-500';
  return (
    <span
      data-testid={`status-chip-${status}`}
      className={'inline-block rounded px-2 py-0.5 text-xs font-medium ' + classes}
    >
      {status}
    </span>
  );
}

interface ChannelCardState {
  loading: boolean;
  error: string | null;
  health: ChannelHealth | null;
}

const INITIAL_CARD_STATE: ChannelCardState = { loading: true, error: null, health: null };

/** The Map key `latestSuccessByFamily` groups under when a row's own
 * `target_family` is null (a foreign Cloud Build's row -- see
 * DeploymentRow's doc comment in adminApi.ts). Keeping this a plain string
 * (never the null itself) means every consumer of the Map's keys, e.g. the
 * family list's `.sort((a, b) => a.localeCompare(b))`, can keep assuming a
 * string without its own null check. */
const UNKNOWN_FAMILY = '(unknown)';

/** One target family's latest SUCCESSFUL deployment, or none seen in the
 * fetched window. Derived client-side from an unfiltered GET /admin/deploys
 * read (rows already come back newest-first) -- the route itself documents
 * this collection as low-volume, so a single generously-limited read is
 * cheap enough not to need its own server-side aggregation. */
function latestSuccessByFamily(rows: DeploymentRow[]): Map<string, DeploymentRow> {
  const byFamily = new Map<string, DeploymentRow>();
  for (const row of rows) {
    if (row.status !== 'success') continue;
    const family = row.target_family ?? UNKNOWN_FAMILY;
    if (!byFamily.has(family)) byFamily.set(family, row);
  }
  return byFamily;
}

/**
 * Deploys page (bd polyglot-pdf-ryx86, E4.7), driving admin_backend/routes/
 * deploy_routes.py's full /admin/deploys surface: POST (trigger), GET
 * (list), GET .../targets (the picker) and GET .../promotable (the gated
 * preview).
 *
 * THREE SECTIONS, independent of one another:
 *
 * 1. LIVE PANEL -- one health card per channel (GET /admin/health, the
 *    SAME route MonitoringPage.tsx already reads) beside that channel
 *    family's latest successful deploy (derived from an unfiltered GET
 *    /admin/deploys read) -- so an operator sees "what is live" without a
 *    tab switch. Loaded once on mount plus a manual Refresh; NOT part of
 *    the table's 15s poll below (a health/version fetch is a heavier,
 *    less time-sensitive read than the deployments list).
 * 2. TRIGGER FORM -- a target picker sourced ONLY from GET /admin/deploys/
 *    targets (never a hand-copied list, CLAUDE.md scar #8) and a REQUIRED
 *    40-hex sha input; no "use dev head" helper (the bead's own rule: this
 *    page must not guess a ref). For a GATED target with a syntactically
 *    valid sha, GET /admin/deploys/promotable is queried and the Deploy
 *    button disables with the server's own reason when it is not
 *    promotable (exit criterion 1). Clicking Deploy opens a confirm panel
 *    showing the target and the FULL 40-character sha -- never truncated
 *    (module rule: a truncated sha is how a wrong build gets approved) --
 *    and POSTs exactly once per Confirm click.
 * 3. DEPLOYMENTS TABLE -- channel/target filters, a status chip per row
 *    (every DEPLOY_STATUSES value, not a hand list), triggered_by, and a
 *    build-id link to log_url. Polls GET /admin/deploys every 15s WHILE
 *    the most recently fetched batch has a queued/working row, and stops
 *    scheduling once every row in that batch is terminal (exit
 *    criterion 2) -- a recursive setTimeout (not setInterval), so a slow
 *    response can never overlap with the next tick and the decision to
 *    keep polling is made fresh off each response, not off stale state.
 */
export const DeploysPage: React.FC<DeploysPageProps> = ({ onAuthExpired }) => {
  // --- Section 1: live panel -------------------------------------------
  const [healthCards, setHealthCards] = React.useState<Record<MonitoringChannel, ChannelCardState>>({
    demo: { ...INITIAL_CARD_STATE },
    staging: { ...INITIAL_CARD_STATE },
  });
  const [latestByFamily, setLatestByFamily] = React.useState<Map<string, DeploymentRow>>(new Map());
  const [latestError, setLatestError] = React.useState<string | null>(null);
  const [latestLoading, setLatestLoading] = React.useState(true);

  const loadHealthChannel = React.useCallback(async (channel: MonitoringChannel) => {
    setHealthCards((prev) => ({ ...prev, [channel]: { loading: true, error: null, health: null } }));
    try {
      const health = await getChannelHealth(channel);
      setHealthCards((prev) => ({ ...prev, [channel]: { loading: false, error: null, health } }));
    } catch (err) {
      if (onAuthExpired(err)) return;
      const message = err instanceof Error ? err.message : 'Could not load channel health';
      setHealthCards((prev) => ({ ...prev, [channel]: { loading: false, error: message, health: null } }));
    }
  }, [onAuthExpired]);

  const loadLatestByFamily = React.useCallback(async () => {
    setLatestLoading(true);
    setLatestError(null);
    try {
      const rows = await listDeploys({ limit: 200 });
      setLatestByFamily(latestSuccessByFamily(rows));
    } catch (err) {
      if (onAuthExpired(err)) return;
      setLatestError(err instanceof Error ? err.message : 'Could not load the latest deployments');
    } finally {
      setLatestLoading(false);
    }
  }, [onAuthExpired]);

  React.useEffect(() => {
    for (const channel of MONITORING_CHANNELS) void loadHealthChannel(channel);
    void loadLatestByFamily();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Section 3 hooks (deployments table) -- DECLARED HERE, ahead of
  // Section 2's confirm handler below, purely so that handler can call
  // `loadTable` directly instead of through a ref indirection. The JSX for
  // this section is still rendered LAST, after Section 2's form. ----------
  const [channelFilter, setChannelFilter] = React.useState<DeployChannel | ''>('');
  const [targetFilter, setTargetFilter] = React.useState('');
  const [tableRows, setTableRows] = React.useState<DeploymentRow[]>([]);
  const [tableLoading, setTableLoading] = React.useState(true);
  const [tableError, setTableError] = React.useState<string | null>(null);
  const pollTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPollTimer = React.useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const loadTable = React.useCallback(async (filters: { channel: string; target: string }) => {
    setTableLoading(true);
    setTableError(null);
    try {
      const rows = await listDeploys({
        channel: (filters.channel || undefined) as DeployChannel | undefined,
        target: filters.target || undefined,
      });
      setTableRows(rows);
      clearPollTimer();
      // Re-schedule off the FRESH response, not stale state -- exit
      // criterion 2's "stops when none is" (module docstring).
      if (rows.some((r) => isDeployInFlight(r.status))) {
        pollTimerRef.current = setTimeout(() => {
          void loadTable(filters);
        }, POLL_INTERVAL_MS);
      }
    } catch (err) {
      if (onAuthExpired(err)) return;
      setTableError(err instanceof Error ? err.message : 'Could not load the deployments list');
    } finally {
      setTableLoading(false);
    }
  }, [onAuthExpired, clearPollTimer]);

  React.useEffect(() => {
    void loadTable({ channel: '', target: '' });
    return () => clearPollTimer();
    // Deliberately mount-only -- filter changes apply on explicit Filter
    // submit (handleFilterSubmit), mirroring AlertsPage's own pattern.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilterSubmit = React.useCallback((e: React.FormEvent) => {
    e.preventDefault();
    clearPollTimer();
    void loadTable({ channel: channelFilter, target: targetFilter });
  }, [loadTable, channelFilter, targetFilter, clearPollTimer]);

  // --- Section 2: trigger form -------------------------------------------
  const [targets, setTargets] = React.useState<DeployTargetRow[] | null>(null);
  const [targetsError, setTargetsError] = React.useState<string | null>(null);
  const [formTarget, setFormTarget] = React.useState('');
  const [formSha, setFormSha] = React.useState('');
  const [promotable, setPromotable] = React.useState<PromotableResult | null>(null);
  const [promotableChecking, setPromotableChecking] = React.useState(false);
  const [promotableError, setPromotableError] = React.useState<string | null>(null);
  const [confirming, setConfirming] = React.useState(false);
  const [triggering, setTriggering] = React.useState(false);
  const [triggerError, setTriggerError] = React.useState<string | null>(null);
  const [triggerSuccess, setTriggerSuccess] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await getDeployTargets();
        if (cancelled) return;
        setTargets(rows);
        setFormTarget((prev) => prev || rows[0]?.target || '');
      } catch (err) {
        if (cancelled) return;
        if (onAuthExpired(err)) return;
        setTargetsError(err instanceof Error ? err.message : 'Could not load the target list');
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedTarget = targets?.find((t) => t.target === formTarget) ?? null;
  const shaValid = SHA_RE.test(formSha);

  // The promotable preview: only meaningful for a GATED target with a
  // syntactically valid sha (module docstring). A stale response for a
  // target/sha that has since changed is ignored via the `cancelled` guard
  // -- the effect re-runs and re-fetches on every change, so only the
  // LATEST request's result is ever applied.
  React.useEffect(() => {
    if (!selectedTarget || !selectedTarget.gated || !shaValid) {
      setPromotable(null);
      setPromotableError(null);
      return;
    }
    let cancelled = false;
    setPromotableChecking(true);
    setPromotableError(null);
    (async () => {
      try {
        const result = await getPromotable(selectedTarget.target, formSha);
        if (cancelled) return;
        setPromotable(result);
      } catch (err) {
        if (cancelled) return;
        if (onAuthExpired(err)) return;
        setPromotableError(err instanceof Error ? err.message : 'Could not check promotability');
        setPromotable(null);
      } finally {
        if (!cancelled) setPromotableChecking(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTarget?.target, selectedTarget?.gated, formSha, shaValid]);

  // Deploy is disabled unless the form is complete AND (the target is not
  // gated OR the server has said it is promotable) -- exit criterion 1.
  const deployDisabled = (
    !formTarget || !shaValid || triggering
    || (selectedTarget?.gated === true && promotable?.promotable !== true)
  );

  const reloadAfterTrigger = React.useCallback(() => {
    void loadLatestByFamily();
    clearPollTimer();
    void loadTable({ channel: channelFilter, target: targetFilter });
  }, [loadLatestByFamily, loadTable, clearPollTimer, channelFilter, targetFilter]);

  const handleConfirmDeploy = React.useCallback(async () => {
    // Re-check the SAME gate `deployDisabled` enforces on the Deploy button
    // -- not just the initial form-completeness check -- because the
    // confirm panel is a sibling <div>, not a modal: the target/sha
    // controls stay live while it is open, so a user can switch to a
    // gated-and-not-yet-verified target without closing the dialog first.
    // Exit criterion 1 ("Deploy is disabled ... enabled when it is") must
    // hold on the control that actually fires the POST, not only on the
    // button that opened the dialog.
    if (!formTarget || !shaValid) return;
    if (selectedTarget?.gated === true && promotable?.promotable !== true) return;
    setTriggering(true);
    setTriggerError(null);
    setTriggerSuccess(null);
    try {
      const result = await triggerDeploy(formTarget, formSha);
      setTriggerSuccess(`Triggered build ${result.build_id ?? '(pending)'} for ${result.target}.`);
      setConfirming(false);
      setFormSha('');
      setPromotable(null);
      reloadAfterTrigger();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setTriggerError(err instanceof Error ? err.message : 'Could not trigger the deploy');
    } finally {
      setTriggering(false);
    }
  }, [formTarget, formSha, shaValid, selectedTarget, promotable, onAuthExpired, reloadAfterTrigger]);

  return (
    <div data-testid="deploys-page" className="max-w-5xl">
      <h2 className="text-lg font-semibold text-gray-900">Deploys</h2>
      <PageIntro>
        See what is live on each channel, trigger a Cloud Build for a
        specific commit, and watch its status through to success or
        failure.
      </PageIntro>

      {/* Section 1: live panel -- health cards beside the latest-success-per-family list. */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {MONITORING_CHANNELS.map((channel) => {
            const state = healthCards[channel];
            const backend = state.health?.backend;
            const backendSha = backend?.reachable
              ? String((backend.version as { git_sha?: unknown } | null)?.git_sha ?? 'unknown')
              : null;
            return (
              <div
                key={channel}
                data-testid={`live-panel-${channel}`}
                className="border border-gray-200 rounded p-4 text-sm"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-gray-900 capitalize">{channel}</h3>
                  <button
                    type="button"
                    className="btn border border-gray-300 text-xs"
                    disabled={state.loading}
                    onClick={() => void loadHealthChannel(channel)}
                  >
                    {state.loading ? 'Loading...' : 'Refresh'}
                  </button>
                </div>

                {state.error && (
                  <p className="mt-3 text-red-600" data-testid={`live-panel-${channel}-error`}>
                    {state.error}
                  </p>
                )}

                {!state.error && state.loading && !state.health && (
                  <p className="mt-3 text-gray-500" data-testid={`live-panel-${channel}-loading`}>
                    Loading...
                  </p>
                )}

                {!state.error && state.health && (
                  !backend?.configured ? (
                    <div data-testid={`live-panel-${channel}-unconfigured`}>
                      <span className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600">
                        Not configured
                      </span>
                    </div>
                  ) : !backend.reachable ? (
                    <div data-testid={`live-panel-${channel}-unreachable`}>
                      <span className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800">
                        Unreachable
                      </span>
                    </div>
                  ) : (
                    <div data-testid={`live-panel-${channel}-reachable`}>
                      <span className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800">
                        Reachable
                      </span>
                      <p className="mt-1 text-gray-700">
                        live sha <code className="text-xs">{backendSha}</code>
                      </p>
                    </div>
                  )
                )}

                <div className="mt-3 border-t border-gray-100 pt-2">
                  <p className="text-gray-500 text-xs uppercase tracking-wide">Admin service</p>
                  <p className="mt-1">
                    version {state.health?.admin_service.version ?? '--'} -- sha{' '}
                    <code className="text-xs">{state.health?.admin_service.git_sha ?? '--'}</code>
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <div
          data-testid="latest-by-family-panel"
          className="border border-gray-200 rounded p-4 text-sm"
        >
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-gray-900">Latest successful deploys</h3>
            <button
              type="button"
              className="btn border border-gray-300 text-xs"
              disabled={latestLoading}
              onClick={() => void loadLatestByFamily()}
            >
              {latestLoading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
          {latestError && <p className="mt-3 text-red-600">{latestError}</p>}
          {!latestError && latestLoading && latestByFamily.size === 0 && (
            <p className="mt-3 text-gray-500">Loading...</p>
          )}
          {!latestError && !(latestLoading && latestByFamily.size === 0) && (
            latestByFamily.size === 0 ? (
              <p className="mt-3 text-gray-500">No successful deployments recorded yet.</p>
            ) : (
              <dl className="mt-3 space-y-2">
                {[...latestByFamily.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([family, row]) => (
                  <div key={family} data-testid={`latest-family-${family}`}>
                    <dt className="text-gray-500 text-xs uppercase tracking-wide">{family}</dt>
                    <dd>
                      <code className="text-xs">{shortSha(row.sha)}</code> on {row.channel}
                      {' -- '}{formatTs(row.ts)}
                    </dd>
                  </div>
                ))}
              </dl>
            )
          )}
        </div>
      </div>

      {/* Section 2: trigger form */}
      <div className="mt-6 border border-gray-200 rounded p-4">
        <h3 className="font-medium text-gray-900">Trigger a deploy</h3>
        {targetsError && <p className="mt-2 text-sm text-red-600">{targetsError}</p>}

        <div className="mt-3 flex flex-wrap items-end gap-2 text-sm">
          <div>
            <label className="block text-gray-700" htmlFor="deploy-target">Deploy target</label>
            <select
              id="deploy-target"
              data-testid="deploy-target-select"
              className="mt-1 border border-gray-300 rounded px-2 py-1"
              value={formTarget}
              onChange={(e) => { setFormTarget(e.target.value); setTriggerSuccess(null); setTriggerError(null); }}
              disabled={!targets}
            >
              {!targets && <option value="">Loading...</option>}
              {targets?.map((t) => (
                <option key={t.target} value={t.target}>
                  {t.target} ({t.channel}{t.gated ? ', gated' : ''})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-gray-700" htmlFor="deploy-sha">Commit sha</label>
            <input
              id="deploy-sha"
              data-testid="deploy-sha-input"
              className="mt-1 border border-gray-300 rounded px-2 py-1 font-mono"
              size={44}
              placeholder="40-character commit sha"
              value={formSha}
              onChange={(e) => { setFormSha(e.target.value.trim()); setTriggerSuccess(null); setTriggerError(null); }}
            />
          </div>
          <button
            type="button"
            data-testid="deploy-button"
            className="btn btn-primary"
            disabled={deployDisabled}
            onClick={() => setConfirming(true)}
          >
            Deploy
          </button>
        </div>

        {formSha && !shaValid && (
          <p className="mt-2 text-sm text-red-600">
            A commit sha must be exactly 40 lowercase hex characters.
          </p>
        )}
        {selectedTarget?.gated && shaValid && (
          <p className="mt-2 text-sm" data-testid="promotable-status">
            {promotableChecking && 'Checking staging status...'}
            {!promotableChecking && promotableError && (
              <span className="text-red-600">{promotableError}</span>
            )}
            {!promotableChecking && !promotableError && promotable?.promotable === false && (
              <span className="text-red-600">
                No successful staging deployment found for this sha -- deploy to staging first.
              </span>
            )}
            {!promotableChecking && !promotableError && promotable?.promotable === true && (
              <span className="text-green-700">Staging-verified -- ready to deploy.</span>
            )}
          </p>
        )}

        {triggerError && <p className="mt-2 text-sm text-red-600">{triggerError}</p>}
        {triggerSuccess && <p className="mt-2 text-sm text-green-700">{triggerSuccess}</p>}

        {confirming && (
          <div
            data-testid="deploy-confirm-dialog"
            className="mt-4 border border-gray-300 rounded p-3 bg-gray-50 text-sm"
          >
            <p>
              Deploy <strong>{formTarget}</strong> at commit{' '}
              <code data-testid="deploy-confirm-sha" className="text-xs break-all">{formSha}</code>?
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                data-testid="deploy-confirm-button"
                className="btn btn-primary"
                disabled={deployDisabled}
                onClick={() => void handleConfirmDeploy()}
              >
                {triggering ? 'Deploying...' : 'Confirm deploy'}
              </button>
              <button
                type="button"
                data-testid="deploy-cancel-button"
                className="btn border border-gray-300"
                disabled={triggering}
                onClick={() => setConfirming(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Section 3: deployments table */}
      <form onSubmit={handleFilterSubmit} className="mt-6 flex flex-wrap items-end gap-2 text-sm">
        <div>
          <label className="block text-gray-700" htmlFor="deploys-channel-filter">Channel</label>
          <select
            id="deploys-channel-filter"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={channelFilter}
            onChange={(e) => setChannelFilter(e.target.value as DeployChannel | '')}
          >
            <option value="">All channels</option>
            {DEPLOY_CHANNELS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-gray-700" htmlFor="deploys-target-filter">Target</label>
          <select
            id="deploys-target-filter"
            className="mt-1 border border-gray-300 rounded px-2 py-1"
            value={targetFilter}
            onChange={(e) => setTargetFilter(e.target.value)}
          >
            <option value="">All targets</option>
            {targets?.map((t) => (
              <option key={t.target} value={t.target}>{t.target}</option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn btn-primary" disabled={tableLoading}>
          {tableLoading ? 'Loading...' : 'Filter'}
        </button>
      </form>

      {tableError && <div className="mt-3 text-sm text-red-600">{tableError}</div>}

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-sm text-left" data-testid="deploys-table">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500">
              <th className="py-1 pr-4">Status</th>
              <th className="py-1 pr-4">Target</th>
              <th className="py-1 pr-4">Channel</th>
              <th className="py-1 pr-4">Sha</th>
              <th className="py-1 pr-4">Triggered by</th>
              <th className="py-1 pr-4">Build</th>
              <th className="py-1 pr-4">Time</th>
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => (
              <tr key={row.id} className="border-b border-gray-100" data-testid={`deploy-row-${row.id}`}>
                <td className="py-1 pr-4"><StatusChip status={row.status} /></td>
                <td className="py-1 pr-4">{row.target}</td>
                <td className="py-1 pr-4">{row.channel}</td>
                <td className="py-1 pr-4"><code className="text-xs">{shortSha(row.sha)}</code></td>
                <td className="py-1 pr-4">{row.triggered_by}</td>
                <td className="py-1 pr-4">
                  {row.build_id ? (
                    row.log_url ? (
                      <a
                        href={row.log_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline"
                      >
                        {row.build_id}
                      </a>
                    ) : row.build_id
                  ) : '--'}
                </td>
                <td className="py-1 pr-4">{formatTs(row.ts)}</td>
              </tr>
            ))}
            {tableRows.length === 0 && !tableLoading && (
              <tr>
                <td colSpan={7} className="py-4 text-gray-500">No deployments match this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
