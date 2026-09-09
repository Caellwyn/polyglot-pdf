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

// Imported HERE, not at the entry point: each console page imports this
// stylesheet itself (LinkHistoryPage.tsx does the same), because a
// stylesheet wired somewhere else can be mounted without it (bd
// polyglot-pdf-41ay8 exists because the markup shipped with no CSS at all).
import './styles/console.css';
import { useAuth } from '../contexts/AuthContext';
import { getBackendHttpUrl } from '../schema-forms/utils/pdfFiller';
import { resolveStaffToken } from '../shared/sessionCredential';

interface FormKit {
  id: string;
  label: string;
}

export interface MintLinkPageProps {
  /** Test override only. In the app the user comes from useAuth(). */
  user?: { getIdToken: () => Promise<string> } | null;
  /** Injected in tests. */
  fetchImpl?: typeof fetch;
}

type Phase = 'idle' | 'minting' | 'done' | 'error';

export function MintLinkPage({ user: userOverride, fetchImpl }: MintLinkPageProps) {
  // From the CONTEXT, not a prop. Mounted inside ProtectedRoute, so a user is
  // present -- and the route element passes no props, so reading a `user` prop
  // here sent every request with NO Authorization header: an empty form picker
  // and a 401 on every mint, in production only. Tests inject fetchImpl and so
  // cannot see it, and VFF_DISABLE_AUTH masks it locally. Same pattern as
  // SchemaFormDemo (bd polyglot-pdf-z2is).
  const { user: authUser } = useAuth();
  const user = userOverride ?? authUser;
  const doFetch = fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  const backend = getBackendHttpUrl();

  const [kits, setKits] = useState<FormKit[]>([]);
  const [kitId, setKitId] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [link, setLink] = useState('');
  const [message, setMessage] = useState('');
  const [copied, setCopied] = useState(false);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    // resolveSTAFFToken, not resolveSessionToken: this is a staff-only action,
    // and the form-filling resolver prefers a stashed client-link token -- so
    // a staffer who tried one of their own links in this tab would mint with
    // the CLIENT credential and be refused (bd polyglot-pdf-so88g).
    const token = await resolveStaffToken(user);
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
        // TWO different problems share this status, and they need opposite
        // fixes (cross-surface review r2):
        //   "Not found"      -> minting is switched off
        //   "Kit not availab" -> minting is ON, but this form is not in the
        //                        firm's allowlist
        // The catalogue lists every PUBLIC kit to any signed-in staffer, while
        // mint requires the kit to be in the firm's explicit allowlist
        // (get_allowed_kits returns kits "beyond public kits"), so the picker
        // can legitimately offer a form that minting then refuses. Reporting
        // that as "switched off" sends the operator to a setting that is
        // already correct.
        const detail = await response.json().then(
          (d) => String(d?.detail ?? ''),
          () => '',
        );
        setPhase('error');
        setMessage(
          detail === 'Kit not available'
            ? 'This form is not on your firm\'s allowed list, so links cannot be created for it yet.'
            : 'Link minting is switched off. Set LINK_MINTING_ENABLED on the backend to turn it on.',
        );
        return;
      }
      if (response.status === 402) {
        // A3's credits-enforced gate (bd polyglot-pdf-jecrl): the firm's
        // balance does not cover this kit's credit_cost. The route's
        // detail is a plain string with no balance field today, but a
        // future response MAY carry one (a numeric `balance` alongside
        // `detail`) -- checked defensively so this page picks it up for
        // free the moment the backend adds it, without a frontend change.
        const body = await response.json().then(
          (d) => d as { detail?: unknown; balance?: unknown },
          () => ({}) as { detail?: unknown; balance?: unknown },
        );
        const balance = typeof body.balance === 'number' ? body.balance : undefined;
        setPhase('error');
        setMessage(
          balance !== undefined
            ? `Your firm does not have enough credits to mint a link (balance: ${balance}).`
            : 'Your firm does not have enough credits to mint a link.',
        );
        return;
      }
      if (response.status === 403) {
        // TWO different 403s share this status (cross-surface shape, mirrors
        // the 404 split above): the ORIGINAL "no firm claim" refusal (this
        // account holds no firm_id/uid at all) vs. A3's NEW "live firm on a
        // non-demo channel" refusal (bd polyglot-pdf-jecrl) -- a real firm
        // account, refused only because THIS DEPLOYMENT may not mint for it.
        // Distinguished by the route's detail text (link_routes.py's
        // MintRefused), since the two need opposite remedies: the first
        // means "ask an app admin to attach your account to a firm"; the
        // second means "use the demo deployment for this firm, not this
        // one" and is not something the signed-in staffer can fix at all.
        const detail = await response.json().then(
          (d) => String((d as { detail?: unknown })?.detail ?? ''),
          () => '',
        );
        setPhase('error');
        setMessage(
          detail.toLowerCase().includes('live firm')
            ? 'This deployment cannot mint links for a live firm. Use the demo deployment for this firm.'
            : 'Your account is not attached to a firm, so it cannot mint links.',
        );
        return;
      }
      if (response.status === 503) {
        // THREE different 503s share this status once PR polyglot-pdf-jecrl
        // (A3, in flight -- see link_routes.py's LedgerError branch) is on
        // dev: two config-missing faults this page already knew about
        // (LINK_BASE_URL or LINK_TOKEN_SECRET unset) plus a NEW transient
        // one -- the reservation's Firestore/ledger write itself failed
        // ("Link minting is temporarily unavailable"), which is a
        // deployment/data fault, not a missing setting. Folding it into the
        // config-missing message would send the operator to check two
        // settings that are already correct -- the exact anti-pattern the
        // 404 and 403 branches above were split to avoid.
        const detail = await response.json().then(
          (d) => String((d as { detail?: unknown })?.detail ?? ''),
          () => '',
        );
        setPhase('error');
        setMessage(
          detail === 'Link minting is temporarily unavailable'
            ? 'Link minting is temporarily unavailable. Please try again in a moment.'
            : 'Link setup is incomplete on the backend: LINK_BASE_URL or LINK_TOKEN_SECRET is missing.',
        );
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
