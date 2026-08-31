/**
 * Mint a client link (bd polyglot-pdf-gob8l, first slice).
 *
 * The maintainer needs to put testers on the deployed app and has no way to do
 * it: minting exists as an API call and nothing more. This is the smallest
 * real thing that fixes that -- pick a form, click, copy a link -- and it is
 * deliberately the FIRST SLICE OF THE CONSOLE rather than a throwaway script,
 * so it grows into the employee half (link tracking, then firm-admin
 * management) instead of being deleted.
 *
 * STAFF ONLY. Mounted behind ProtectedRoute, and the backend independently
 * requires a firm claim: /api/links/mint reads firm_id and employee_id from
 * the VERIFIED token, never from anything this page sends. A page cannot
 * grant itself a firm.
 *
 * MINTING IS OFF BY DEFAULT. LINK_MINTING_ENABLED gates the route (the bd
 * ik7e interlock: no live link may exist without a spend ceiling behind it),
 * and the backend answers 404 when it is off -- deliberately not 503, so a
 * disabled endpoint does not advertise itself. This page says so in plain
 * words rather than showing a raw error, because "Not found" on a button you
 * just pressed is not a useful thing to read.
 */
import { useCallback, useEffect, useState } from 'react';

import { getBackendHttpUrl } from '../schema-forms/utils/pdfFiller';
import { resolveSessionToken } from '../shared/sessionCredential';

interface FormKit {
  id: string;
  label: string;
}

export interface MintLinkPageProps {
  /** The signed-in staff user; supplies the bearer token. */
  user?: { getIdToken: () => Promise<string> } | null;
  /** Injected in tests. */
  fetchImpl?: typeof fetch;
}

type Phase = 'idle' | 'minting' | 'done' | 'error';

export function MintLinkPage({ user, fetchImpl }: MintLinkPageProps) {
  const doFetch = fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  const backend = getBackendHttpUrl();

  const [kits, setKits] = useState<FormKit[]>([]);
  const [kitId, setKitId] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [link, setLink] = useState('');
  const [message, setMessage] = useState('');
  const [copied, setCopied] = useState(false);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await resolveSessionToken(user);
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [user]);

  // The catalogue the caller may actually see. Deliberately the SAME route the
  // voice app uses, so this page cannot show a form the backend would refuse
  // to mint against.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await doFetch(`${backend}/api/form-kits`, {
          headers: await authHeaders(),
        });
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled) return;
        // `forms`, not `parts`. The WS handshake manifest uses `parts` and
        // this route does not -- assuming the wrong envelope key showed an
        // empty picker with no error anywhere.
        const forms = Array.isArray(data?.forms) ? data.forms : [];
        setKits(forms.map((f: { id: string; label?: string }) => ({
          id: f.id,
          label: f.label || f.id,
        })));
        if (forms.length && !kitId) setKitId(forms[0].id);
      } catch {
        // A catalogue we cannot load leaves the picker empty; the mint button
        // is disabled without a selection, so there is nothing to mislead.
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backend]);

  const mint = useCallback(async () => {
    setPhase('minting');
    setMessage('');
    setLink('');
    setCopied(false);
    try {
      const response = await doFetch(`${backend}/api/links/mint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
        body: JSON.stringify({ kit_id: kitId }),
      });

      if (response.status === 404) {
        // The ik7e interlock, not a broken page.
        setPhase('error');
        setMessage(
          'Link minting is switched off. Set LINK_MINTING_ENABLED on the backend to turn it on.',
        );
        return;
      }
      if (response.status === 403) {
        setPhase('error');
        setMessage('Your account is not attached to a firm, so it cannot mint links.');
        return;
      }
      if (response.status === 503) {
        setPhase('error');
        setMessage('Link delivery is not configured: LINK_BASE_URL is unset on the backend.');
        return;
      }
      if (!response.ok) {
        setPhase('error');
        setMessage('Could not create a link. Please try again.');
        return;
      }

      const data = await response.json();
      setLink(String(data.url || ''));
      setPhase('done');
    } catch {
      setPhase('error');
      setMessage('Could not reach the server.');
    }
  }, [backend, kitId, authHeaders, doFetch]);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      // Clipboard access is refused in plenty of contexts. The link is on
      // screen and selectable, so this is a convenience, not the mechanism.
    }
  }, [link]);

  return (
    <div className="mint-page">
      <h1>Send someone a link</h1>
      <p>
        Creates a one-time link for a single form. Send it to the person
        yourself -- we never see their email address.
      </p>

      <label htmlFor="mint-kit">Form</label>
      <select
        id="mint-kit"
        value={kitId}
        onChange={(e) => setKitId(e.target.value)}
      >
        {kits.map((kit) => (
          <option key={kit.id} value={kit.id}>{kit.label}</option>
        ))}
      </select>

      <button
        type="button"
        onClick={() => void mint()}
        disabled={!kitId || phase === 'minting'}
      >
        {phase === 'minting' ? 'Creating...' : 'Create link'}
      </button>

      {phase === 'done' && (
        <div className="mint-result">
          {/* readOnly, not disabled: a disabled input cannot be selected, and
              selecting the text by hand is the fallback when the clipboard is
              unavailable. */}
          <input readOnly value={link} aria-label="Client link" />
          <button type="button" onClick={() => void copy()}>
            {copied ? 'Copied' : 'Copy'}
          </button>
          <p className="mint-note">
            This link opens one form, once. It expires if it is not opened.
          </p>
        </div>
      )}

      {phase === 'error' && <p role="alert">{message}</p>}
    </div>
  );
}
