import React from 'react';
import {
  getFirm, setFirmAllowedKits, setFirmKind, setFirmPlan,
  grantCredits, adjustCredits, listFirmLinks, revokeLink,
  FIRM_KINDS, GRANT_TYPES, USD_REQUIRED_GRANT_TYPES, LINK_CHANNELS, PLAN_TIERS,
  type FirmDetail, type FirmKind, type FirmPlan, type GrantType,
  type LinkChannel, type LinkRow, type PlanTier,
} from '../utils/adminApi';

interface FirmDetailPageProps {
  firmId: string;
  /** Called first on every catch -- see FirmsPage.tsx's identical prop. */
  onAuthExpired: (err: unknown) => boolean;
  /** Back to the firms list. No router in this console (App.tsx's
   * docstring), so navigation is reported upward like everywhere else. */
  onBack: () => void;
}

/** usd_amount is shown ONLY for the two income grant types (bead exit
 * criterion 1: "grant sends usd_amount only for the two income types"). */
function usdAmountApplies(type: GrantType): boolean {
  return (USD_REQUIRED_GRANT_TYPES as readonly GrantType[]).includes(type);
}

/**
 * Firm detail page (bd polyglot-pdf-r8z9g, Epic 2 Track C bead C2): profile,
 * allowed_kits editor, kind change (confirm-twice + required reason),
 * balance, a paginated ledger table, grant/adjust forms, and the firm's
 * links (bead B4's listing) with a channel selector and revoke.
 *
 * MUTATE THEN RE-READ, same round-trip pattern ConfigEditorPage and
 * UsersPage already use: every write below (allowed_kits, kind, grant,
 * adjust, revoke) calls its route once and then reloads the firm profile
 * (and, for revoke, the link list) from the server, so the screen always
 * reflects what the server actually stored rather than an optimistic local
 * patch.
 *
 * KIND CHANGE IS CONFIRM-TWICE IN THIS CONSOLE, NOT THE ROUTE (mirrors
 * firm_routes.py's SetKindRequest docstring: "a route cannot see how many
 * times a human clicked"). The UI enforces two explicit confirmations
 * before setFirmKind is ever called: opening the kind-change form is the
 * first step, and its own Submit click inside a confirm dialog rendered
 * only after a reason is typed is the second -- see handleKindChangeClick /
 * handleConfirmKindChange below. A REASON IS ALSO REQUIRED client-side
 * (blank refuses submit), mirroring the route's own 422.
 *
 * usd_amount ONLY RENDERS (and is only sent) for subscription_grant and
 * purchase -- the two types credit_routes.py requires it for; switching the
 * grant-type <select> to promo_grant clears any typed usd_amount so a
 * leftover value cannot ride along on a type the route would refuse it on.
 *
 * CHANNEL SELECTOR ON LINKS. list_firm_links's `channel` query param is
 * REQUIRED (link_routes.py's own 422-on-missing/unknown rule) -- there is
 * no "all channels" reading, since a link record lives in exactly one
 * channel's collection. This page defaults to 'demo' and lets the operator
 * switch, reloading the link list on change.
 *
 * REVOKE CALLS THE ROUTE ONCE THEN RE-READS (exit criterion: "revoke calls
 * the route once and re-reads"), same as every other mutation on this page.
 *
 * PLAN EDITOR (bd polyglot-pdf-0euzk): tier + monthly_credits + rollover,
 * ONE WRITE PER SAVE -- unlike kind, a plan change carries no "mints for
 * free" failure mode (it only changes a monthly top-up amount a scheduled
 * route applies once a month), so it skips the confirm-twice dance
 * entirely. Client-side validation mirrors the route's own rules
 * (monthly_credits a positive integer) ahead of the network call, but the
 * route's own 422 detail is still what this page trusts for anything that
 * check does not catch.
 */
export const FirmDetailPage: React.FC<FirmDetailPageProps> = ({
  firmId, onAuthExpired, onBack,
}) => {
  const [firm, setFirm] = React.useState<FirmDetail | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // allowed_kits editor -- a single comma-separated text field, committed
  // as a full replace (matches the route's own full-replace contract).
  const [allowedKitsInput, setAllowedKitsInput] = React.useState('');
  const [savingKits, setSavingKits] = React.useState(false);
  const [kitsError, setKitsError] = React.useState<string | null>(null);

  // Kind-change confirm-twice flow. `kindFormOpen` is confirmation #1
  // (opening the form at all); `confirmingKind` gates a second explicit
  // dialog that only appears once a non-blank reason is typed, and its own
  // Submit is confirmation #2.
  const [kindFormOpen, setKindFormOpen] = React.useState(false);
  const [pendingKind, setPendingKind] = React.useState<FirmKind | ''>('');
  const [kindReason, setKindReason] = React.useState('');
  const [confirmingKind, setConfirmingKind] = React.useState(false);
  const [savingKind, setSavingKind] = React.useState(false);
  const [kindError, setKindError] = React.useState<string | null>(null);

  // Plan editor -- one write per save, no confirm-twice (see module
  // docstring). String state for the number input so an operator can
  // clear the field mid-edit without it snapping to 0/NaN.
  const [planTier, setPlanTier] = React.useState<PlanTier>('starter');
  const [planMonthlyCredits, setPlanMonthlyCredits] = React.useState('');
  const [planRollover, setPlanRollover] = React.useState(false);
  const [savingPlan, setSavingPlan] = React.useState(false);
  const [planError, setPlanError] = React.useState<string | null>(null);

  // Grant form.
  const [grantType, setGrantType] = React.useState<GrantType>('subscription_grant');
  const [grantAmount, setGrantAmount] = React.useState('');
  const [grantUsdAmount, setGrantUsdAmount] = React.useState('');
  const [granting, setGranting] = React.useState(false);
  const [grantError, setGrantError] = React.useState<string | null>(null);

  // Adjust form.
  const [adjustAmount, setAdjustAmount] = React.useState('');
  const [adjustReason, setAdjustReason] = React.useState('');
  const [adjusting, setAdjusting] = React.useState(false);
  const [adjustError, setAdjustError] = React.useState<string | null>(null);

  // Links.
  const [channel, setChannel] = React.useState<LinkChannel>('demo');
  const [links, setLinks] = React.useState<LinkRow[]>([]);
  const [linksLoading, setLinksLoading] = React.useState(false);
  const [linksError, setLinksError] = React.useState<string | null>(null);
  const [revokingJti, setRevokingJti] = React.useState<string | null>(null);

  const loadFirm = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detail = await getFirm(firmId);
      setFirm(detail);
      setAllowedKitsInput(detail.allowed_kits.join(', '));
      setPlanTier(detail.plan.tier);
      setPlanMonthlyCredits(String(detail.plan.monthly_credits));
      setPlanRollover(detail.plan.rollover);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setError(err instanceof Error ? err.message : 'Could not load the firm');
    } finally {
      setLoading(false);
    }
  }, [firmId, onAuthExpired]);

  const loadLinks = React.useCallback(async (ch: LinkChannel) => {
    setLinksLoading(true);
    setLinksError(null);
    try {
      const page = await listFirmLinks(firmId, ch);
      setLinks(page.links);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setLinksError(err instanceof Error ? err.message : 'Could not load the firm links');
    } finally {
      setLinksLoading(false);
    }
  }, [firmId, onAuthExpired]);

  React.useEffect(() => {
    void loadFirm();
    // Deliberately excludes `channel` from the deps below (loadLinks below
    // covers it): the firm profile itself has no channel of its own, so a
    // channel switch must not re-fetch it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firmId]);

  React.useEffect(() => {
    // ONE effect for the link list, keyed on BOTH firmId and channel --
    // firing it from two separate effects (one per dependency) double-calls
    // listFirmLinks on the initial mount, since both would run together the
    // first time. A firm switch and a channel switch each reach this same
    // effect, so the link list is fetched exactly once per meaningful
    // change, never twice for the same render.
    void loadLinks(channel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firmId, channel]);

  const handleSaveAllowedKits = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const kits = allowedKitsInput
      .split(',')
      .map((k) => k.trim())
      .filter((k) => k.length > 0);
    setSavingKits(true);
    setKitsError(null);
    try {
      await setFirmAllowedKits(firmId, kits);
      await loadFirm();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setKitsError(err instanceof Error ? err.message : 'Could not update the allowed kits');
    } finally {
      setSavingKits(false);
    }
  }, [firmId, allowedKitsInput, loadFirm, onAuthExpired]);

  // Confirmation #1: opening the kind-change form at all.
  const handleOpenKindForm = React.useCallback(() => {
    setPendingKind(firm?.kind ?? '');
    setKindReason('');
    setConfirmingKind(false);
    setKindError(null);
    setKindFormOpen(true);
  }, [firm]);

  const handleCancelKindForm = React.useCallback(() => {
    setKindFormOpen(false);
    setConfirmingKind(false);
    setPendingKind('');
    setKindReason('');
    setKindError(null);
  }, []);

  // First submit: validate, then show the second confirmation dialog
  // rather than writing anything yet.
  const handleRequestKindChange = React.useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingKind) {
      setKindError('Kind is required.');
      return;
    }
    if (!kindReason.trim()) {
      setKindError('A reason is required.');
      return;
    }
    setKindError(null);
    setConfirmingKind(true);
  }, [pendingKind, kindReason]);

  // Confirmation #2: the dialog's own Submit actually writes.
  const handleConfirmKindChange = React.useCallback(async () => {
    if (!pendingKind) return;
    setSavingKind(true);
    setKindError(null);
    try {
      await setFirmKind(firmId, pendingKind, kindReason.trim());
      setKindFormOpen(false);
      setConfirmingKind(false);
      setPendingKind('');
      setKindReason('');
      await loadFirm();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setKindError(err instanceof Error ? err.message : 'Could not change the firm kind');
    } finally {
      setSavingKind(false);
    }
  }, [firmId, pendingKind, kindReason, loadFirm, onAuthExpired]);

  const handleSavePlan = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const monthlyCredits = Number(planMonthlyCredits);
    if (!Number.isInteger(monthlyCredits) || monthlyCredits <= 0) {
      setPlanError('Monthly credits must be a positive whole number.');
      return;
    }
    const plan: FirmPlan = {
      tier: planTier, monthly_credits: monthlyCredits, rollover: planRollover,
    };
    setSavingPlan(true);
    setPlanError(null);
    try {
      await setFirmPlan(firmId, plan);
      await loadFirm();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setPlanError(err instanceof Error ? err.message : 'Could not update the firm plan');
    } finally {
      setSavingPlan(false);
    }
  }, [firmId, planTier, planMonthlyCredits, planRollover, loadFirm, onAuthExpired]);

  const handleGrantTypeChange = React.useCallback((type: GrantType) => {
    setGrantType(type);
    // Clear any typed usd_amount when switching to a type that must not
    // carry one -- see module docstring.
    if (!usdAmountApplies(type)) setGrantUsdAmount('');
  }, []);

  const handleGrant = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const amount = Number(grantAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setGrantError('Amount must be a positive number.');
      return;
    }
    const needsUsd = usdAmountApplies(grantType);
    let usdAmount: number | undefined;
    if (needsUsd) {
      usdAmount = Number(grantUsdAmount);
      if (!Number.isFinite(usdAmount) || usdAmount <= 0) {
        setGrantError('This grant type requires a USD amount.');
        return;
      }
    }
    setGranting(true);
    setGrantError(null);
    try {
      await grantCredits(firmId, { type: grantType, amount, usdAmount });
      setGrantAmount('');
      setGrantUsdAmount('');
      await loadFirm();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setGrantError(err instanceof Error ? err.message : 'Could not grant credits');
    } finally {
      setGranting(false);
    }
  }, [firmId, grantType, grantAmount, grantUsdAmount, loadFirm, onAuthExpired]);

  const handleAdjust = React.useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const amount = Number(adjustAmount);
    if (!Number.isFinite(amount) || amount === 0) {
      setAdjustError('Amount must be a non-zero number.');
      return;
    }
    if (!adjustReason.trim()) {
      setAdjustError('A reason is required.');
      return;
    }
    setAdjusting(true);
    setAdjustError(null);
    try {
      await adjustCredits(firmId, { amount, reason: adjustReason.trim() });
      setAdjustAmount('');
      setAdjustReason('');
      await loadFirm();
    } catch (err) {
      if (onAuthExpired(err)) return;
      setAdjustError(err instanceof Error ? err.message : 'Could not adjust credits');
    } finally {
      setAdjusting(false);
    }
  }, [firmId, adjustAmount, adjustReason, loadFirm, onAuthExpired]);

  const handleRevoke = React.useCallback(async (jti: string) => {
    setRevokingJti(jti);
    setLinksError(null);
    try {
      await revokeLink(jti, channel);
      await loadLinks(channel);
    } catch (err) {
      if (onAuthExpired(err)) return;
      setLinksError(err instanceof Error ? err.message : 'Could not revoke the link');
    } finally {
      setRevokingJti(null);
    }
  }, [channel, loadLinks, onAuthExpired]);

  return (
    <div data-testid="firm-detail-page" className="max-w-4xl">
      <button type="button" className="text-blue-600 hover:underline text-sm" onClick={onBack}>
        Back to firms
      </button>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
      {loading && !firm && <p className="mt-3 text-gray-500 text-sm">Loading...</p>}

      {firm && (
        <>
          <h2 className="mt-2 text-lg font-semibold text-gray-900">
            {firm.name || firm.firm_id}
          </h2>
          <div className="mt-1 text-sm text-gray-600">
            <span className="mr-4">ID: {firm.firm_id}</span>
            <span className="mr-4">Contact: {firm.contact_email}</span>
            <span
              className={
                'inline-block rounded px-2 py-0.5 text-xs font-medium ' +
                (firm.kind === 'live'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-amber-100 text-amber-800')
              }
            >
              {firm.kind}
            </span>
            <span className="ml-4">Status: {firm.status ?? 'unknown'}</span>
          </div>
          <div className="mt-2 text-2xl font-semibold text-gray-900" data-testid="firm-balance">
            {firm.balance_credits} credits
          </div>

          {/* Allowed kits */}
          <form onSubmit={(e) => void handleSaveAllowedKits(e)} className="mt-6 border border-gray-200 rounded p-4 text-sm">
            <label className="block text-gray-700" htmlFor="firm-allowed-kits">
              Allowed kits (comma-separated)
            </label>
            <textarea
              id="firm-allowed-kits"
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1"
              value={allowedKitsInput}
              onChange={(e) => setAllowedKitsInput(e.target.value)}
            />
            <button type="submit" className="mt-2 btn btn-primary" disabled={savingKits}>
              {savingKits ? 'Saving...' : 'Save allowed kits'}
            </button>
            {kitsError && <div className="mt-2 text-red-600">{kitsError}</div>}
          </form>

          {/* Kind change (confirm-twice) */}
          <div className="mt-6 border border-gray-200 rounded p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium text-gray-700">Firm kind</span>
              {!kindFormOpen && (
                <button type="button" className="btn border border-gray-300" onClick={handleOpenKindForm}>
                  Change kind
                </button>
              )}
            </div>

            {kindFormOpen && !confirmingKind && (
              <form onSubmit={handleRequestKindChange} className="mt-3 flex flex-wrap items-end gap-2">
                <div>
                  <label className="block text-gray-700" htmlFor="firm-kind-select">
                    New kind
                  </label>
                  <select
                    id="firm-kind-select"
                    className="mt-1 border border-gray-300 rounded px-2 py-1"
                    value={pendingKind}
                    onChange={(e) => setPendingKind(e.target.value as FirmKind)}
                  >
                    {FIRM_KINDS.map((k) => (
                      <option key={k} value={k}>{k}</option>
                    ))}
                  </select>
                </div>
                <div className="flex-1 min-w-[16rem]">
                  <label className="block text-gray-700" htmlFor="firm-kind-reason">
                    Reason (required)
                  </label>
                  <input
                    id="firm-kind-reason"
                    required
                    className="mt-1 w-full border border-gray-300 rounded px-2 py-1"
                    value={kindReason}
                    onChange={(e) => setKindReason(e.target.value)}
                  />
                </div>
                <button type="submit" className="btn btn-primary">Continue</button>
                <button type="button" className="btn border border-gray-300" onClick={handleCancelKindForm}>
                  Cancel
                </button>
              </form>
            )}

            {confirmingKind && (
              <div className="mt-3 border border-red-200 bg-red-50 rounded p-3" data-testid="kind-confirm-dialog">
                <p className="text-red-800">
                  Confirm: change {firm.firm_id} from {firm.kind} to {pendingKind}?
                  This affects real billing behavior.
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={savingKind}
                    onClick={() => void handleConfirmKindChange()}
                  >
                    {savingKind ? 'Changing...' : 'Yes, change kind'}
                  </button>
                  <button type="button" className="btn border border-gray-300" onClick={handleCancelKindForm}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {kindError && <div className="mt-2 text-red-600">{kindError}</div>}
          </div>

          {/* Plan (bd polyglot-pdf-0euzk) -- one write per save, no confirm-twice */}
          <form onSubmit={(e) => void handleSavePlan(e)} className="mt-6 border border-gray-200 rounded p-4 text-sm" data-testid="plan-form">
            <h3 className="font-medium text-gray-700">Plan</h3>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <div>
                <label className="block text-gray-700" htmlFor="plan-tier">Tier</label>
                <select
                  id="plan-tier"
                  className="mt-1 border border-gray-300 rounded px-2 py-1"
                  value={planTier}
                  onChange={(e) => setPlanTier(e.target.value as PlanTier)}
                >
                  {PLAN_TIERS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-gray-700" htmlFor="plan-monthly-credits">
                  Monthly credits
                </label>
                <input
                  id="plan-monthly-credits"
                  required
                  type="number"
                  className="mt-1 border border-gray-300 rounded px-2 py-1"
                  value={planMonthlyCredits}
                  onChange={(e) => setPlanMonthlyCredits(e.target.value)}
                />
              </div>
              <div className="flex items-center gap-1">
                <input
                  id="plan-rollover"
                  type="checkbox"
                  checked={planRollover}
                  onChange={(e) => setPlanRollover(e.target.checked)}
                />
                <label className="text-gray-700" htmlFor="plan-rollover">
                  Rollover (add, don&apos;t cap)
                </label>
              </div>
              <button type="submit" className="btn btn-primary" disabled={savingPlan}>
                {savingPlan ? 'Saving...' : 'Save plan'}
              </button>
            </div>
            {planError && <div className="mt-2 text-red-600">{planError}</div>}
          </form>

          {/* Grant / adjust */}
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            <form onSubmit={(e) => void handleGrant(e)} className="border border-gray-200 rounded p-4 text-sm">
              <h3 className="font-medium text-gray-700">Grant credits</h3>
              <div className="mt-2">
                <label className="block text-gray-700" htmlFor="grant-type">Type</label>
                <select
                  id="grant-type"
                  className="mt-1 border border-gray-300 rounded px-2 py-1"
                  value={grantType}
                  onChange={(e) => handleGrantTypeChange(e.target.value as GrantType)}
                >
                  {GRANT_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="mt-2">
                <label className="block text-gray-700" htmlFor="grant-amount">Amount (credits)</label>
                <input
                  id="grant-amount"
                  required
                  type="number"
                  min="1"
                  className="mt-1 border border-gray-300 rounded px-2 py-1"
                  value={grantAmount}
                  onChange={(e) => setGrantAmount(e.target.value)}
                />
              </div>
              {usdAmountApplies(grantType) && (
                <div className="mt-2">
                  <label className="block text-gray-700" htmlFor="grant-usd-amount">USD amount</label>
                  <input
                    id="grant-usd-amount"
                    required
                    type="number"
                    min="0.01"
                    step="0.01"
                    className="mt-1 border border-gray-300 rounded px-2 py-1"
                    value={grantUsdAmount}
                    onChange={(e) => setGrantUsdAmount(e.target.value)}
                  />
                </div>
              )}
              <button type="submit" className="mt-3 btn btn-primary" disabled={granting}>
                {granting ? 'Granting...' : 'Grant'}
              </button>
              {grantError && <div className="mt-2 text-red-600">{grantError}</div>}
            </form>

            <form onSubmit={(e) => void handleAdjust(e)} className="border border-gray-200 rounded p-4 text-sm">
              <h3 className="font-medium text-gray-700">Adjust credits</h3>
              <div className="mt-2">
                <label className="block text-gray-700" htmlFor="adjust-amount">
                  Amount (may be negative)
                </label>
                <input
                  id="adjust-amount"
                  required
                  type="number"
                  className="mt-1 border border-gray-300 rounded px-2 py-1"
                  value={adjustAmount}
                  onChange={(e) => setAdjustAmount(e.target.value)}
                />
              </div>
              <div className="mt-2">
                <label className="block text-gray-700" htmlFor="adjust-reason">Reason (required)</label>
                <input
                  id="adjust-reason"
                  required
                  className="mt-1 w-full border border-gray-300 rounded px-2 py-1"
                  value={adjustReason}
                  onChange={(e) => setAdjustReason(e.target.value)}
                />
              </div>
              <button type="submit" className="mt-3 btn btn-primary" disabled={adjusting}>
                {adjusting ? 'Adjusting...' : 'Adjust'}
              </button>
              {adjustError && <div className="mt-2 text-red-600">{adjustError}</div>}
            </form>
          </div>

          {/* Ledger */}
          <div className="mt-6 overflow-x-auto">
            <h3 className="font-medium text-gray-700 text-sm">Ledger</h3>
            <table className="mt-2 min-w-full text-sm text-left" data-testid="ledger-table">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500">
                  <th className="py-1 pr-4">Type</th>
                  <th className="py-1 pr-4">Amount</th>
                  <th className="py-1 pr-4">USD</th>
                  <th className="py-1 pr-4">Balance after</th>
                  <th className="py-1 pr-4">Reason</th>
                  <th className="py-1 pr-4">Actor</th>
                </tr>
              </thead>
              <tbody>
                {firm.ledger.map((entry, index) => (
                  // doc_id is not sent by GET /admin/firms/{firm_id} (see
                  // LedgerEntry's comment in adminApi.ts) -- key on the
                  // fields the route does send instead of a value the
                  // producer omits.
                  <tr key={`${entry.ts}-${index}`} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{entry.type}</td>
                    <td className="py-1 pr-4">{entry.amount}</td>
                    <td className="py-1 pr-4">{entry.usd_amount ?? ''}</td>
                    <td className="py-1 pr-4">{entry.balance_after}</td>
                    <td className="py-1 pr-4">{entry.reason ?? ''}</td>
                    <td className="py-1 pr-4">{entry.actor}</td>
                  </tr>
                ))}
                {firm.ledger.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-4 text-gray-500">No ledger entries.</td>
                  </tr>
                )}
              </tbody>
            </table>
            {firm.ledger_truncated && (
              <p className="mt-2 text-xs text-amber-700">
                Only the most recent entries are shown.
              </p>
            )}
          </div>

          {/* Links */}
          <div className="mt-6">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-gray-700 text-sm">Links</h3>
              <div className="flex items-center gap-2 text-sm">
                <label htmlFor="link-channel" className="text-gray-700">Channel</label>
                <select
                  id="link-channel"
                  className="border border-gray-300 rounded px-2 py-1"
                  value={channel}
                  onChange={(e) => setChannel(e.target.value as LinkChannel)}
                >
                  {LINK_CHANNELS.map((ch) => (
                    <option key={ch} value={ch}>{ch}</option>
                  ))}
                </select>
              </div>
            </div>

            {linksError && <div className="mt-2 text-sm text-red-600">{linksError}</div>}

            <div className="mt-2 overflow-x-auto">
              <table className="min-w-full text-sm text-left" data-testid="links-table">
                <thead>
                  <tr className="border-b border-gray-200 text-gray-500">
                    <th className="py-1 pr-4">Kit</th>
                    <th className="py-1 pr-4">Employee</th>
                    <th className="py-1 pr-4">Status</th>
                    <th className="py-1 pr-4">Spend</th>
                    <th className="py-1 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {links.map((link) => (
                    <tr key={link.jti} className="border-b border-gray-100">
                      <td className="py-1 pr-4">{link.kit_id ?? ''}</td>
                      <td className="py-1 pr-4">{link.employee_id ?? ''}</td>
                      <td className="py-1 pr-4">{link.status ?? ''}</td>
                      <td className="py-1 pr-4">{link.spend_usd ?? ''}</td>
                      <td className="py-1 pr-4">
                        <button
                          type="button"
                          className="btn border border-gray-300"
                          disabled={link.status !== 'minted' || revokingJti === link.jti}
                          onClick={() => void handleRevoke(link.jti)}
                        >
                          {revokingJti === link.jti ? 'Revoking...' : 'Revoke'}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {links.length === 0 && !linksLoading && (
                    <tr>
                      <td colSpan={5} className="py-4 text-gray-500">No links for this channel.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
