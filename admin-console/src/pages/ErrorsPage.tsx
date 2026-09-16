import React from 'react';
import { getChannelErrors, MONITORING_CHANNELS, type ErrorGroup, type MonitoringChannel } from '../utils/adminApi';
import { PageIntro } from '../components/PageIntro';

interface ErrorsPageProps {
  onAuthExpired: (err: unknown) => boolean;
}

/**
 * Errors page (bd polyglot-pdf-i6dlb, E3.11b), driving
 * admin_backend/routes/ops_routes.py's GET /admin/errors.
 *
 * CHANNEL TABS, ONE FETCH PER TAB SWITCH -- unlike MonitoringPage (which
 * loads both channels at once into side-by-side cards), the bead's own
 * wording is "channel tabs", so this page loads ONE channel's error groups
 * at a time, on mount and again whenever the selected tab changes.
 *
 * THE RESPONSE ALLOWLIST IS RENDERED VERBATIM AND NOTHING ELSE (bead
 * requirement: "nothing else from the payload is rendered ... pinned by a
 * test that feeds an extra `message` key and asserts it never reaches the
 * DOM"). This page reads ONLY the five ErrorGroup fields adminApi.ts types
 * (count, first_seen_time, last_seen_time, error_type, top_frame) by NAME
 * -- it never spreads a group object into the DOM or iterates its own
 * keys, so a group payload carrying an extra field (a `message`, or
 * anything else Cloud Error Reporting might one day add) has no code path
 * that would render it.
 */
export const ErrorsPage: React.FC<ErrorsPageProps> = ({ onAuthExpired }) => {
  const [channel, setChannel] = React.useState<MonitoringChannel>('demo');
  const [groups, setGroups] = React.useState<ErrorGroup[]>([]);
  const [service, setService] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const loadChannel = React.useCallback(async (target: MonitoringChannel) => {
    setLoading(true);
    setError(null);
    try {
      const page = await getChannelErrors(target);
      setGroups(page.groups);
      setService(page.service);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load channel errors');
      setGroups([]);
      setService('');
    } finally {
      setLoading(false);
    }
  }, [onAuthExpired]);

  React.useEffect(() => {
    void loadChannel(channel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel]);

  return (
    <div data-testid="errors-page" className="max-w-5xl">
      <h2 className="text-lg font-semibold text-gray-900">Errors</h2>
      <PageIntro>
        See grouped, deduplicated application errors per channel from Cloud
        Error Reporting.
      </PageIntro>

      <nav className="mt-4 flex gap-4 text-sm border-b border-gray-200">
        {MONITORING_CHANNELS.map((c) => (
          <button
            key={c}
            type="button"
            className={
              'py-2 border-b-2 capitalize ' +
              (channel === c ? 'border-primary-600 text-primary-700 font-medium' : 'border-transparent text-gray-500')
            }
            onClick={() => setChannel(c)}
          >
            {c}
          </button>
        ))}
      </nav>

      {service && <p className="mt-2 text-xs text-gray-500">Service: {service}</p>}
      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
      {loading && <p className="mt-3 text-gray-500" data-testid="errors-loading">Loading...</p>}

      {!loading && !error && (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm text-left" data-testid="errors-table">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500">
                <th className="py-1 pr-4">Type</th>
                <th className="py-1 pr-4">Count</th>
                <th className="py-1 pr-4">First seen</th>
                <th className="py-1 pr-4">Last seen</th>
                <th className="py-1 pr-4">Top frame</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group, i) => (
                <tr key={group.group_id ?? i} className="border-b border-gray-100">
                  <td className="py-1 pr-4">{group.error_type ?? 'unknown'}</td>
                  <td className="py-1 pr-4">{group.count}</td>
                  <td className="py-1 pr-4">{group.first_seen_time ?? '--'}</td>
                  <td className="py-1 pr-4">{group.last_seen_time ?? '--'}</td>
                  <td className="py-1 pr-4">
                    {group.top_frame.file_path
                      ? group.top_frame.file_path + ':' + (group.top_frame.line_number ?? '?')
                        + ' (' + (group.top_frame.function_name ?? 'unknown') + ')'
                      : '--'}
                  </td>
                </tr>
              ))}
              {groups.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-4 text-gray-500">No errors reported for this channel.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
