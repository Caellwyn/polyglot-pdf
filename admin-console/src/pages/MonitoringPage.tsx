import React from 'react';
import {
  getChannelHealth, MONITORING_CHANNELS,
  type ChannelHealth, type MonitoringChannel,
} from '../utils/adminApi';
import { PageIntro } from '../components/PageIntro';

interface MonitoringPageProps {
  /** Called first on every catch -- see UsersPage.tsx's identical prop for
   * the full rationale, and App.tsx's handleAuthExpired docstring. */
  onAuthExpired: (err: unknown) => boolean;
}

/** One channel's health card state: loading, an error, or a loaded
 * ChannelHealth. Kept PER CHANNEL (not one shared loading/error pair) so
 * one channel's fetch failure never blanks the other channel's already-
 * loaded card -- exit criterion: "an unreachable or unconfigured channel
 * renders a distinct state, never a blank card" extends to a channel whose
 * OWN health call itself 500s or throws, not only to the reachable/
 * configured flags inside a successful response. */
interface ChannelCardState {
  loading: boolean;
  error: string | null;
  health: ChannelHealth | null;
}

const INITIAL_CARD_STATE: ChannelCardState = { loading: true, error: null, health: null };

/**
 * Monitoring page (bd polyglot-pdf-i6dlb, E3.11b), driving
 * admin_backend/routes/ops_routes.py's GET /admin/health.
 *
 * ONE CARD PER CHANNEL (demo, staging), each independently fetched on
 * mount -- a slow or failing channel must not block or blank the other's
 * card (see ChannelCardState's docstring). Each card shows the PUBLIC
 * backend's reachable/configured state and version SHA, plus the ADMIN
 * SERVICE's own version (present on every response regardless of the
 * backend's own state, since ops_routes.py reads it in-process).
 *
 * THREE DISTINCT BACKEND STATES, rendered distinctly (never collapsed into
 * one generic "down" card, per the bead's own wording): `configured: false`
 * ("not wired up" -- nobody has set BACKEND_URLS_JSON for this channel yet);
 * `configured: true, reachable: false` ("wired up but not answering" -- the
 * backend itself is down or unreachable); `reachable: true` (healthy,
 * showing its version SHA). A CARD-LEVEL FETCH FAILURE (the /admin/health
 * call itself throwing, e.g. a 503 from the admin service losing Firestore)
 * is a FOURTH distinct state, rendered as this card's own error message --
 * never a blank card, matching the same "no blank card" rule extended to
 * the console's own request failing, not only to what the request reports
 * about the backend.
 */
export const MonitoringPage: React.FC<MonitoringPageProps> = ({ onAuthExpired }) => {
  const [cards, setCards] = React.useState<Record<MonitoringChannel, ChannelCardState>>({
    demo: { ...INITIAL_CARD_STATE },
    staging: { ...INITIAL_CARD_STATE },
  });

  const loadChannel = React.useCallback(async (channel: MonitoringChannel) => {
    setCards((prev) => ({ ...prev, [channel]: { loading: true, error: null, health: null } }));
    try {
      const health = await getChannelHealth(channel);
      setCards((prev) => ({ ...prev, [channel]: { loading: false, error: null, health } }));
    } catch (err) {
      if (onAuthExpired(err)) return;
      const message = err instanceof Error ? err.message : 'Could not load channel health';
      setCards((prev) => ({ ...prev, [channel]: { loading: false, error: message, health: null } }));
    }
  }, [onAuthExpired]);

  React.useEffect(() => {
    for (const channel of MONITORING_CHANNELS) {
      void loadChannel(channel);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRefresh = React.useCallback((channel: MonitoringChannel) => {
    void loadChannel(channel);
  }, [loadChannel]);

  return (
    <div data-testid="monitoring-page" className="max-w-4xl">
      <h2 className="text-lg font-semibold text-gray-900">Monitoring</h2>
      <PageIntro>
        Check each channel&apos;s live health and version so you can see
        whether staging and demo are up and what is deployed.
      </PageIntro>
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        {MONITORING_CHANNELS.map((channel) => (
          <ChannelCard
            key={channel}
            channel={channel}
            state={cards[channel]}
            onRefresh={() => handleRefresh(channel)}
          />
        ))}
      </div>
    </div>
  );
};

const ChannelCard: React.FC<{
  channel: MonitoringChannel;
  state: ChannelCardState;
  onRefresh: () => void;
}> = ({ channel, state, onRefresh }) => {
  return (
    <div
      data-testid={`health-card-${channel}`}
      className="border border-gray-200 rounded p-4 text-sm"
    >
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-gray-900 capitalize">{channel}</h3>
        <button
          type="button"
          className="btn border border-gray-300 text-xs"
          disabled={state.loading}
          onClick={onRefresh}
        >
          {state.loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {state.error && (
        <p className="mt-3 text-red-600" data-testid={`health-card-${channel}-error`}>
          {state.error}
        </p>
      )}

      {!state.error && state.health && (
        <div className="mt-3 space-y-3">
          <BackendStatus channel={channel} health={state.health} />
          <div className="border-t border-gray-100 pt-2">
            <p className="text-gray-500 text-xs uppercase tracking-wide">Admin service</p>
            <p className="mt-1">
              version {state.health.admin_service.version} -- sha{' '}
              <code className="text-xs">{state.health.admin_service.git_sha}</code>
            </p>
          </div>
        </div>
      )}

      {!state.error && !state.health && state.loading && (
        <p className="mt-3 text-gray-500" data-testid={`health-card-${channel}-loading`}>
          Loading...
        </p>
      )}
    </div>
  );
};

const BackendStatus: React.FC<{ channel: MonitoringChannel; health: ChannelHealth }> = ({
  channel, health,
}) => {
  const { backend } = health;

  if (!backend.configured) {
    return (
      <div data-testid={`health-card-${channel}-unconfigured`}>
        <span className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600">
          Not configured
        </span>
        <p className="mt-1 text-gray-500 text-xs">
          No backend URL is wired up for this channel yet.
        </p>
      </div>
    );
  }

  if (!backend.reachable) {
    return (
      <div data-testid={`health-card-${channel}-unreachable`}>
        <span className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800">
          Unreachable
        </span>
        <p className="mt-1 text-gray-500 text-xs">
          The backend is configured but did not answer /health and /version.
        </p>
      </div>
    );
  }

  const versionSha = (backend.version && (backend.version as { git_sha?: unknown }).git_sha)
    ?? 'unknown';

  return (
    <div data-testid={`health-card-${channel}-reachable`}>
      <span className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800">
        Reachable
      </span>
      <p className="mt-1 text-gray-700">
        version sha <code className="text-xs">{String(versionSha)}</code>
      </p>
    </div>
  );
};
