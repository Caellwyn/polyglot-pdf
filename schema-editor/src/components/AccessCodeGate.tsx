import React from 'react';
import {
  getAccessCode, setAccessCode, clearAccessCode, probeSession,
  type EditorRole,
} from '../utils/remoteKitStore';

interface AccessCodeGateProps {
  /** Called once the access code validated; carries the caller's role. */
  onReady: (role: EditorRole) => void;
}

/**
 * The hosted editor's front gate (bd polyglot-pdf-92qe.2): ask for the access
 * code ONCE, validate it against GET /api/editor/session (which also reports
 * the caller's tier -- editor vs author), and remember it in localStorage so a
 * returning contractor goes straight to the catalogue.
 *
 * Sharing model: the maintainer hands a contractor the editor URL + an access
 * code. The EDITOR code unlocks polish work (open/edit/save/mark-complete on
 * provided kits); the AUTHOR code additionally unlocks PDF onboarding + hosted
 * extraction (bd 92qe.3). Two codes, two tiers -- no accounts to manage.
 *
 * On mount, an already-stored (or build-baked) code is validated silently; the
 * form only renders when there is no working code.
 */
export const AccessCodeGate: React.FC<AccessCodeGateProps> = ({ onReady }) => {
  const [code, setCode] = React.useState('');
  const [checking, setChecking] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Silent re-validation of a remembered code on first render.
  const [probingStored, setProbingStored] = React.useState(() => getAccessCode() !== null);

  const validate = React.useCallback(async (
    candidate: string | null, silent: boolean,
  ) => {
    if (!candidate) {
      setProbingStored(false);
      return;
    }
    setChecking(true);
    setError(null);
    try {
      setAccessCode(candidate);
      const session = await probeSession();
      onReady(session.role);
    } catch (err) {
      clearAccessCode();
      setProbingStored(false);
      // A silently-probed stale code just falls back to the form, no error
      // banner; an explicit submit shows why it was refused.
      if (!silent) {
        setError(err instanceof Error ? err.message : 'Could not validate the access code');
      }
    } finally {
      setChecking(false);
    }
  }, [onReady]);

  React.useEffect(() => {
    if (probingStored) void validate(getAccessCode(), true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only probe
  }, []);

  const handleSubmit = React.useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim();
    if (!trimmed) return;
    void validate(trimmed, false);
  }, [code, validate]);

  if (probingStored) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-500">Checking your access...</p>
      </div>
    );
  }

  return (
    <div className="h-screen flex items-center justify-center bg-gray-50">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-white border border-gray-200 rounded-lg shadow-sm p-6"
        data-testid="access-code-gate"
      >
        <h1 className="text-xl font-bold text-gray-900">PDF Schema Editor</h1>
        <p className="mt-1 text-sm text-gray-600">
          Enter the access code you were given to open the shared form workspace.
        </p>
        <input
          type="password"
          autoFocus
          className="mt-4 w-full border border-gray-300 rounded px-3 py-2 text-sm"
          placeholder="Access code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          disabled={checking}
          aria-label="Access code"
        />
        {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
        <button
          type="submit"
          className="btn btn-primary mt-4 w-full"
          disabled={checking || !code.trim()}
        >
          {checking ? 'Checking...' : 'Open the workspace'}
        </button>
      </form>
    </div>
  );
};
