/**
 * Firm-scoped unacknowledged-alert banner (bd polyglot-pdf-62o4d).
 *
 * WHAT THIS IS. Epic 3 bead E3.5 (backend/services/alerts.py) writes
 * telemetry alert docs (a link hit its spend ceiling; a firm's credit
 * balance is low or exhausted) into Firestore, and the maintainer's
 * 2026-09-14 decision was "no outbound email for now; alerts appear (a) in
 * the firm's own console where staff generate links and (b) in the admin
 * console's firm detail." This component is half (a): a shared banner
 * mounted at the top of MintLinkPage.tsx and LinkHistoryPage.tsx, reading
 * GET /admin/firms/{firm_id}/alerts?acknowledged=false (Surface contract
 * 32) through the SAME adminFetch/resolveStaffToken chain those two pages
 * already use (Surface contract 23).
 *
 * ROLE AND FIRM ID COME FROM THE VERIFIED TOKEN'S CLAIMS
 * (`user.getIdTokenResult()`'s `claims.firm_id` / `claims.firm_role`),
 * mirroring LinkHistoryPage.tsx's own resolution exactly -- never trusted
 * from a prop or route param, because a manager-only Acknowledge button is
 * a UI affordance only: the real boundary is the admin service's own gate
 * (require_app_admin_or_owning_manager_or_employee, which additionally
 * refuses an employee's acknowledge attempt server-side regardless of what
 * this component renders).
 *
 * SILENT ON EVERY FAILURE MODE THE BEAD NAMES. No firm claim, a fetch
 * exception, a non-200 response, or zero unacknowledged alerts: the banner
 * renders NOTHING (returns null) rather than an error message or an empty
 * box. The bead's own words: "never blocks the page on a fetch error (it
 * shows nothing and logs to console)". This is deliberately different from
 * MintLinkPage's and LinkHistoryPage's own OWN fetches, which DO show an
 * error -- because this component is a peripheral notice bolted onto pages
 * whose primary job (minting a link, reading link history) must keep
 * working even when the alerts feed is broken; a banner that fails loudly
 * would compete with the page's own real error state for the same
 * attention.
 *
 * THE MESSAGE MAP IS CLOSED AND PLAIN-LANGUAGE (bead's own three kinds and
 * wording): kind + level are rendered alongside a human sentence built from
 * `context` fields NAMED here, one per kind -- never a raw `context` dump,
 * and never any OTHER field off the alert doc. `context` is metadata-only
 * by construction (alerts.py's own module docstring: jti/balance/spend_usd/
 * ceiling_usd, never a form field value), so there is no PII risk in
 * reading it, but this component still never renders it verbatim: an
 * unrecognized kind (a future alerts.py addition this component has not
 * been taught yet) falls back to a generic "This firm has an alert that
 * needs attention" sentence with NO context interpolation, rather than
 * either crashing or leaking a raw object.
 *
 * ACKNOWLEDGE IS MANAGER-ONLY (bead's own words), ONE CALL, THEN RE-FETCH
 * -- the same "one call, re-read" shape LinkHistoryPage.tsx's own revoke
 * button uses: the server, not local state, decides what the banner shows
 * next (a 409 from a race with another manager, or the admin service's own
 * dispatcher acknowledging it first once that ships, must be reflected by
 * re-reading, not by locally hiding the row on an optimistic assumption).
 *
 * REFRESH ON A 402 (bead's own words: "the mint page ALSO reacts to a 402
 * from the mint route by refreshing the banner"). Rather than an
 * imperative ref API (no precedent anywhere else in this codebase), the
 * parent bumps a `refreshSignal` number prop; this component's fetch
 * effect depends on it, so a new value re-runs the fetch -- the same
 * "bump a value, effect re-runs" idiom React already uses everywhere else
 * in this file for firmId/isManager. MintLinkPage.tsx's 402 handler
 * increments its own counter and passes it down.
 */
import { useCallback, useEffect, useState } from 'react';

import './styles/console.css';
import { adminFetch } from './adminApi';

interface AlertContext {
  balance?: number;
  threshold?: number;
  spend_usd?: number;
  ceiling_usd?: number;
  jti?: string;
}

/** The narrow allowlist admin_backend/routes/alert_routes.py's
 * _public_firm_alert_view returns: id, kind, level, ts, context,
 * acknowledged_at -- deliberately NOT firm_id or acknowledged_by (see that
 * route's own docstring). Every key here is the only keys this component
 * ever reads off a row. */
interface AlertRow {
  id: string;
  kind: string | null;
  level: string | null;
  ts: number | null;
  context: AlertContext | null;
  acknowledged_at: number | null;
}

const KIND_CREDIT_LOW = 'credit_low';
const KIND_CREDIT_EXHAUSTED = 'credit_exhausted';
const KIND_LINK_EXHAUSTED = 'link_exhausted';

/** THE CLOSED kind -> plain-language message MAP (bead's own three
 * sentences, verbatim). A function, not a static string, because
 * credit_low interpolates the firm's remaining balance from `context`. */
function messageFor(row: AlertRow): string {
  const ctx = row.context || {};
  switch (row.kind) {
    case KIND_CREDIT_LOW:
      return `This firm has ${ctx.balance ?? '?'} credits left`;
    case KIND_CREDIT_EXHAUSTED:
      return 'This firm is out of credits; new links cannot be minted';
    case KIND_LINK_EXHAUSTED:
      return 'A client link hit its spend cap';
    default:
      // An alert kind this component has not been taught yet -- never
      // interpolate an unrecognized shape's context, just say something is
      // wrong in the vaguest true sentence available.
      return 'This firm has an alert that needs attention';
  }
}

interface AuthUserLike {
  uid?: string;
  getIdToken: () => Promise<string>;
  getIdTokenResult?: () => Promise<{ claims: Record<string, unknown> }>;
}

export interface FirmAlertsBannerProps {
  /** The signed-in staffer, passed down by the mounting page (which reads
   * it from useAuth() itself -- this component has no context dependency
   * of its own, so it can be unit-tested with a plain object). */
  user?: AuthUserLike | null;
  /** Injected in tests. */
  fetchImpl?: typeof fetch;
  /** Bump this number to force a re-fetch (bead's own "the mint page ALSO
   * reacts to a 402 ... by refreshing the banner"). Optional: a page that
   * never needs to force a refresh (LinkHistoryPage.tsx) simply omits it. */
  refreshSignal?: number;
}

export function FirmAlertsBanner({
  user,
  fetchImpl,
  refreshSignal,
}: FirmAlertsBannerProps) {
  const doFetch = fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));

  const [firmId, setFirmId] = useState<string | null>(null);
  const [isManager, setIsManager] = useState(false);
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);

  // The verified token's OWN claims -- same resolution as
  // LinkHistoryPage.tsx's own effect. Unlike that page, a missing firm
  // claim or a claims-read failure here does NOT set any error state --
  // it simply leaves firmId null, which the render below already treats
  // as "show nothing" (module docstring's "SILENT ON EVERY FAILURE MODE").
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!user) return;
      try {
        const result = user.getIdTokenResult
          ? await user.getIdTokenResult()
          : { claims: {} as Record<string, unknown> };
        if (cancelled) return;
        const claims = result.claims || {};
        const claimedFirmId = typeof claims.firm_id === 'string' ? claims.firm_id : null;
        setFirmId(claimedFirmId);
        setIsManager(claims.firm_role === 'manager');
      } catch {
        if (!cancelled) {
          setFirmId(null);
          setIsManager(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const load = useCallback(async () => {
    if (!firmId) return;
    try {
      const response = await adminFetch(
        `/admin/firms/${encodeURIComponent(firmId)}/alerts?acknowledged=false`,
        user,
        {},
        doFetch,
      );
      if (!response.ok) {
        // Silent -- see module docstring. Logged for an operator reading
        // the browser console, never surfaced to the page itself.
        // eslint-disable-next-line no-console
        console.error('FirmAlertsBanner: could not load alerts', response.status);
        setRows([]);
        return;
      }
      const data = await response.json();
      const alerts = Array.isArray(data?.alerts) ? (data.alerts as AlertRow[]) : [];
      setRows(alerts);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('FirmAlertsBanner: could not reach the server', err);
      setRows([]);
    }
  }, [firmId, user, doFetch]);

  useEffect(() => {
    void load();
    // refreshSignal is a deliberate re-fetch trigger, not a value read
    // inside load() -- bumping it alone must re-run this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, refreshSignal]);

  const acknowledge = useCallback(async (alertId: string) => {
    if (!isManager || acknowledgingId) return;
    setAcknowledgingId(alertId);
    try {
      const response = await adminFetch(
        `/admin/alerts/${encodeURIComponent(alertId)}/acknowledge`,
        user,
        { method: 'PATCH' },
        doFetch,
      );
      if (!response.ok) {
        // eslint-disable-next-line no-console
        console.error('FirmAlertsBanner: could not acknowledge alert', response.status);
        return;
      }
      // ONE call, then RE-FETCH -- see module docstring.
      await load();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('FirmAlertsBanner: could not reach the server', err);
    } finally {
      setAcknowledgingId(null);
    }
  }, [isManager, acknowledgingId, user, doFetch, load]);

  if (!firmId || rows.length === 0) return null;

  return (
    <div className="firm-alerts-banner" role="status">
      {rows.map((row) => (
        <div key={row.id} className="firm-alerts-banner-row">
          <span className="firm-alerts-banner-level" data-level={row.level ?? 'warning'}>
            {row.level === 'critical' ? 'Critical' : 'Warning'}
          </span>
          <span className="firm-alerts-banner-message">{messageFor(row)}</span>
          {isManager && (
            <button
              type="button"
              className="firm-alerts-banner-ack"
              onClick={() => void acknowledge(row.id)}
              disabled={acknowledgingId === row.id}
            >
              {acknowledgingId === row.id ? 'Acknowledging...' : 'Acknowledge'}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
