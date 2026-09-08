import React from 'react';
import {
  getChannelConfig, setChannelConfigKey, type ChannelConfig,
} from '../utils/adminApi';

// Mirrors admin_backend/routes/config_routes.py's KNOWN_CHANNELS -- there is
// NO prod (deploy-production.sh targets a dead project and refuses to run).
// Kept as a small literal here rather than fetched from the server: the
// server 404s an unknown channel itself, so a stale copy here degrades to
// "the tab 404s", not a silent wrong write.
const KNOWN_CHANNELS = ['demo', 'staging'] as const;

/**
 * app_config editor page, per channel (bd polyglot-pdf-b6943): the console's
 * first MUTATING page, driving admin_backend/routes/config_routes.py's
 * GET+PUT /admin/config/{channel}.
 *
 * ONE KEY AT A TIME, matching the route's own contract
 * (ConfigPutRequest -- "a whole-doc PUT would make 'what changed' a diff the
 * operator has to compute"): each row's Save button PUTs only that row's key,
 * and the round trip re-reads the channel doc afterward so the screen always
 * reflects what the server actually stored (not merely what the form held),
 * catching a value the server accepted as one KIND of coercion the console
 * did not anticipate.
 *
 * `unknown_keys` (entries no backend reads) are shown read-only in their own
 * section -- editing them here would let an operator "fix" a typo'd key by
 * writing a THIRD key next to the two that already do nothing.
 */
export const ConfigEditorPage: React.FC = () => {
  const [channel, setChannel] = React.useState<(typeof KNOWN_CHANNELS)[number]>('staging');
  const [config, setConfig] = React.useState<ChannelConfig | null>(null);
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [savingKey, setSavingKey] = React.useState<string | null>(null);
  const [savedMessage, setSavedMessage] = React.useState<string | null>(null);

  const load = React.useCallback(async (ch: string, opts: { clearSavedMessage?: boolean } = {}) => {
    const { clearSavedMessage = true } = opts;
    setLoading(true);
    setError(null);
    // The post-save re-read passes clearSavedMessage: false so the "Saved
    // ..." confirmation survives the very re-read that proves the save
    // round-tripped -- clearing it here unconditionally would wipe the
    // message before the operator ever saw it (this WAS a bug, caught by
    // this page's own round-trip test).
    if (clearSavedMessage) setSavedMessage(null);
    try {
      const cfg = await getChannelConfig(ch);
      setConfig(cfg);
      const nextDrafts: Record<string, string> = {};
      for (const key of cfg.known_keys) {
        const raw = cfg.values[key];
        nextDrafts[key] = raw === undefined ? '' : String(raw);
      }
      setDrafts(nextDrafts);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the channel config');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load(channel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel]);

  const handleSave = React.useCallback(async (key: string) => {
    setSavingKey(key);
    setError(null);
    setSavedMessage(null);
    try {
      // The raw draft string is sent as-is; the server's coerce_value is the
      // single source of truth for what counts as a valid value for this
      // key (config_routes.py's docstring) -- this page must not
      // re-implement that judgment client-side and risk disagreeing with it.
      await setChannelConfigKey(channel, key, drafts[key]);
      setSavedMessage(`Saved ${key}.`);
      // Re-read the channel doc so the screen reflects the server's own
      // coercion of the value just written, not merely the form's draft --
      // this IS the round trip the exit criterion asks for. Do not clear the
      // confirmation message this re-read would otherwise wipe.
      await load(channel, { clearSavedMessage: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not save ${key}`);
    } finally {
      setSavingKey(null);
    }
  }, [channel, drafts, load]);

  return (
    <div data-testid="config-editor-page" className="max-w-2xl">
      <h2 className="text-lg font-semibold text-gray-900">Runtime config</h2>

      <label className="block mt-4 text-sm text-gray-700" htmlFor="config-channel">
        Channel
      </label>
      <select
        id="config-channel"
        className="mt-1 border border-gray-300 rounded px-2 py-1 text-sm"
        value={channel}
        onChange={(e) => setChannel(e.target.value as (typeof KNOWN_CHANNELS)[number])}
      >
        {KNOWN_CHANNELS.map((ch) => (
          <option key={ch} value={ch}>{ch}</option>
        ))}
      </select>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
      {savedMessage && <div className="mt-3 text-sm text-green-700">{savedMessage}</div>}
      {loading && <p className="mt-3 text-sm text-gray-500">Loading...</p>}

      {config && (
        <div className="mt-4 space-y-3">
          {config.known_keys.map((key) => (
            <div key={key} className="flex items-end gap-2">
              <div className="flex-1">
                <label className="block text-sm text-gray-700" htmlFor={`config-key-${key}`}>
                  {key}
                </label>
                <input
                  id={`config-key-${key}`}
                  className="mt-1 w-full border border-gray-300 rounded px-2 py-1 text-sm"
                  value={drafts[key] ?? ''}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
                  disabled={savingKey === key}
                />
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void handleSave(key)}
                disabled={savingKey === key}
              >
                {savingKey === key ? 'Saving...' : 'Save'}
              </button>
            </div>
          ))}

          {config.unknown_keys.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-medium text-gray-700">
                Unknown keys (no backend reads these)
              </h3>
              <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm text-gray-500">
                {config.unknown_keys.map((key) => (
                  <React.Fragment key={key}>
                    <dt className="font-mono">{key}</dt>
                    <dd>{String(config.values[key])}</dd>
                  </React.Fragment>
                ))}
              </dl>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
