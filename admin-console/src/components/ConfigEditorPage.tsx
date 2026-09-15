import React from 'react';
import {
  getChannelConfig, setChannelConfigKey, type ChannelConfig, type ConfigKeySchema,
} from '../utils/adminApi';

// Mirrors admin_backend/routes/config_routes.py's KNOWN_CHANNELS -- there is
// NO prod (deploy-production.sh targets a dead project and refuses to run).
// Kept as a small literal here rather than fetched from the server: the
// server 404s an unknown channel itself, so a stale copy here degrades to
// "the tab 404s", not a silent wrong write.
const KNOWN_CHANNELS = ['demo', 'staging'] as const;

// Sentinel drafts value meaning "no value typed/selected yet -- use the
// fallback". Distinct from any real value: 'true'/'false' are reserved for
// an actual bool selection, and a numeric key's UNSET state must not be
// confused with the empty string a cleared number input produces -- both
// route to this same sentinel so Save always has a definite choice to make.
// Never sent to the server: handleSave refuses to PUT while a draft is UNSET.
const UNSET = '__unset__';

/** True when `schema[key]` names a type this page renders a dedicated
 * control for. An unrecognized type (or a key GET never described in
 * `schema` -- should not happen once the route is deployed, but a stale
 * deploy skew is exactly the case a fallback exists for) renders as the
 * original plain text input. */
function controlKind(schema: ConfigKeySchema | undefined): 'bool' | 'number' | 'text' {
  if (!schema) return 'text';
  if (schema.type === 'bool') return 'bool';
  if (schema.type === 'int' || schema.type === 'float') return 'number';
  return 'text';
}

interface ConfigEditorPageProps {
  /** Called first on every catch. Returns true when `err` was an
   * AuthError/ForbiddenError that App has already routed back to the
   * sign-in gate -- in that case this page must NOT also set its own
   * generic error banner (the gate is about to replace this page entirely).
   * Returns false for anything else, so this page's normal error handling
   * still applies. See App.tsx's handleAuthExpired docstring for why this
   * is the console's single mid-session-eviction predicate. */
  onAuthExpired: (err: unknown) => boolean;
}

/**
 * app_config editor page, per channel (bd polyglot-pdf-b6943): the console's
 * first MUTATING page, driving admin_backend/routes/config_routes.py's
 * GET+PUT /admin/config/{channel}.
 *
 * SCHEMA-DRIVEN CONTROLS (bd polyglot-pdf-wxcj0): the GET response's
 * `schema` map ({key: {type, default}}, derived server-side from
 * runtime_config.KEY_TYPES) is the ONLY thing this page consults to decide
 * how a key renders -- never a key name pattern or a second hand-typed list
 * (CLAUDE.md scar #8). A `bool` key renders a <select> of true/false plus an
 * "unset -- use the fallback" option; `int`/`float` render a number input
 * (step="1" or step="any"); anything else falls back to the original text
 * input. Whatever the control, the PUT body sends a TYPED JSON value --
 * `true`/`false` for a bool, a JS number for int/float -- never the string
 * "true" a naive text binding would produce, so runtime_config.coerce_value
 * on the server sees exactly the type it expects.
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
export const ConfigEditorPage: React.FC<ConfigEditorPageProps> = ({ onAuthExpired }) => {
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
        nextDrafts[key] = raw === undefined ? UNSET : String(raw);
      }
      setDrafts(nextDrafts);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the channel config');
    } finally {
      setLoading(false);
    }
  }, [onAuthExpired]);

  React.useEffect(() => {
    void load(channel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel]);

  const handleSave = React.useCallback(async (key: string) => {
    const draft = drafts[key];
    // UNSET means "the operator has not typed/selected a real value" --
    // there is nothing to PUT. This is reachable for a bool select left on
    // its placeholder option, or a number/text input cleared back to empty.
    if (draft === undefined || draft === UNSET) return;

    const kind = controlKind(config?.schema[key]);
    let value: unknown = draft;
    if (kind === 'bool') {
      value = draft === 'true';
    } else if (kind === 'number') {
      const parsed = Number(draft);
      // An unparsable number never reaches the server as NaN -- surface the
      // SAME "not a valid value" shape a server-side rejection would show,
      // rather than letting JSON.stringify silently turn NaN into `null`
      // and look like a deliberate clear.
      if (Number.isNaN(parsed)) {
        setError(`'${draft}' is not a valid value for ${key}`);
        return;
      }
      value = parsed;
    }

    setSavingKey(key);
    setError(null);
    setSavedMessage(null);
    try {
      // The typed value (boolean/number/string) is sent as-is; the server's
      // coerce_value is the single source of truth for what counts as a
      // valid value for this key (config_routes.py's docstring) -- this page
      // must not re-implement that judgment client-side beyond turning the
      // control's own input into the right JSON type.
      await setChannelConfigKey(channel, key, value);
      setSavedMessage(`Saved ${key}.`);
      // Re-read the channel doc so the screen reflects the server's own
      // coercion of the value just written, not merely the form's draft --
      // this IS the round trip the exit criterion asks for. Do not clear the
      // confirmation message this re-read would otherwise wipe.
      await load(channel, { clearSavedMessage: false });
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : `Could not save ${key}`);
    } finally {
      setSavingKey(null);
    }
  }, [channel, config, drafts, load, onAuthExpired]);

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
          {config.known_keys.map((key) => {
            const schema = config.schema[key];
            const kind = controlKind(schema);
            const draft = drafts[key] ?? UNSET;
            return (
              <div key={key} className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-sm text-gray-700" htmlFor={`config-key-${key}`}>
                    {key}
                  </label>
                  {kind === 'bool' ? (
                    <select
                      id={`config-key-${key}`}
                      className="mt-1 w-full border border-gray-300 rounded px-2 py-1 text-sm"
                      value={draft}
                      onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
                      disabled={savingKey === key}
                    >
                      <option value={UNSET}>unset -- use the fallback</option>
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : kind === 'number' ? (
                    <input
                      id={`config-key-${key}`}
                      type="number"
                      step={schema?.type === 'float' ? 'any' : '1'}
                      className="mt-1 w-full border border-gray-300 rounded px-2 py-1 text-sm"
                      value={draft === UNSET ? '' : draft}
                      onChange={(e) => setDrafts((prev) => ({
                        ...prev,
                        [key]: e.target.value === '' ? UNSET : e.target.value,
                      }))}
                      disabled={savingKey === key}
                    />
                  ) : (
                    <input
                      id={`config-key-${key}`}
                      className="mt-1 w-full border border-gray-300 rounded px-2 py-1 text-sm"
                      value={draft === UNSET ? '' : draft}
                      onChange={(e) => setDrafts((prev) => ({
                        ...prev,
                        [key]: e.target.value === '' ? UNSET : e.target.value,
                      }))}
                      disabled={savingKey === key}
                    />
                  )}
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
            );
          })}

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
