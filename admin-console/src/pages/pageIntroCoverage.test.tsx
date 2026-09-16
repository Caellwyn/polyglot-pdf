/**
 * Purpose-header coverage (bd polyglot-pdf-dp1zq exit criterion 2): "Every
 * console page has a one-sentence purpose header (a test enumerates the
 * pages under src/pages and asserts each renders one)."
 *
 * ENUMERATES src/pages ON DISK (not a hand-typed list, CLAUDE.md scar #8):
 * `fs.readdirSync` over `src/pages/` picks up every `*Page.tsx` file, so a
 * new page added later without a PageIntro fails this test automatically
 * rather than depending on someone remembering to extend a list here. The
 * enumeration excludes `*.test.tsx` (readdirSync sees the whole directory,
 * including test files) and this file itself.
 *
 * ONE SHARED PageIntro COMPONENT (src/components/PageIntro.tsx) is what
 * every page renders, tagged `data-testid="page-intro"` -- this test does
 * not care about the wording (that is each page's own file's job to get
 * right; see each page's own test or the module docstring), only that the
 * tag is present exactly once.
 *
 * MOCKS EVERY NETWORK CALL the ten pages make on mount, with responses
 * shaped so nothing throws and nothing stays stuck on a permanent loading
 * spinner before the assertion runs -- this test is a structural coverage
 * check, not a re-test of any one page's data rendering (each page's own
 * *.test.tsx already covers that). DeploysPage's target fixture's first
 * (and only) row is NOT gated, so its promotable-preview effect never
 * fires here -- getPromotable needs no mock. FirmDetailPage is the one page whose
 * PageIntro is conditional on its firm having loaded (it sits inside the
 * `{firm && (...)}` block, since the intro belongs next to the firm's own
 * name heading, not above a "loading" state) -- so its case below awaits
 * that load before asserting, while every other page's PageIntro renders
 * unconditionally at the top of the page and needs no such wait.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen, waitFor } from '@testing-library/react';

import { UsersPage } from './UsersPage';
import { FirmsPage } from './FirmsPage';
import { FirmDetailPage } from './FirmDetailPage';
import { KitCommercialsPage } from './KitCommercialsPage';
import { MonitoringPage } from './MonitoringPage';
import { UsagePage } from './UsagePage';
import { CostReportsPage } from './CostReportsPage';
import { AlertsPage } from './AlertsPage';
import { ErrorsPage } from './ErrorsPage';
import { DeploysPage } from './DeploysPage';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  return {
    ...actual,
    listUsers: vi.fn(),
    listFirms: vi.fn(),
    getFirm: vi.fn(),
    setFirmAllowedKits: vi.fn(),
    setFirmKind: vi.fn(),
    setFirmPlan: vi.fn(),
    grantCredits: vi.fn(),
    adjustCredits: vi.fn(),
    listFirmLinks: vi.fn(),
    revokeLink: vi.fn(),
    listKits: vi.fn(),
    getKitCommercial: vi.fn(),
    getChannelHealth: vi.fn(),
    getFirmUsage: vi.fn(),
    getCostReport: vi.fn(),
    getIncomeReport: vi.fn(),
    listAlerts: vi.fn(),
    getChannelErrors: vi.fn(),
    getDeployTargets: vi.fn(),
    getPromotable: vi.fn(),
    listDeploys: vi.fn(),
  };
});

import {
  listUsers, listFirms, getFirm, listFirmLinks, listKits, getKitCommercial,
  getChannelHealth, getFirmUsage, getCostReport, getIncomeReport, listAlerts,
  getChannelErrors, getDeployTargets, listDeploys,
} from '../utils/adminApi';

const noAuthExpired = () => false;
const noOp = () => {};

const FIRM_A = {
  firm_id: 'firm-a', name: 'Firm A', contact_email: 'a@example.com',
  kind: 'live' as const, status: 'active' as const, allowed_kits: [],
  balance_credits: 100,
  plan: { tier: 'starter' as const, monthly_credits: 35, rollover: false },
};

const FIRM_DETAIL = {
  ...FIRM_A,
  ledger: [],
  ledger_truncated: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listUsers).mockResolvedValue({ firm_id: 'firm-a', users: [], truncated: false });
  vi.mocked(listFirms).mockResolvedValue([FIRM_A]);
  vi.mocked(getFirm).mockResolvedValue(FIRM_DETAIL);
  vi.mocked(listFirmLinks).mockResolvedValue({ firm_id: 'firm-a', channel: 'demo', links: [] });
  vi.mocked(listKits).mockResolvedValue({ kits: [] });
  vi.mocked(getKitCommercial).mockResolvedValue({
    kit_id: 'w7', credit_cost: 1, cap_usd: 3, source: 'default', display: {},
  });
  vi.mocked(getChannelHealth).mockResolvedValue({
    channel: 'demo',
    backend: { configured: true, reachable: true, health: null, version: null },
    admin_service: { version: '1.0.0', git_sha: 'abc123', app_module: 'admin_backend.main' },
  });
  vi.mocked(getFirmUsage).mockResolvedValue({
    firm_id: 'firm-a', month: '2026-09', channel: 'demo',
    usage: {
      connections_ended: null, sessions_completed: null, cost_usd_total: null,
      links_opened: null, links_completed: null, links_minted: null,
      by_kit: null, by_employee: null, by_language: null, kind: null, channel: null,
    },
  });
  vi.mocked(getCostReport).mockResolvedValue({
    group_by: 'firm', from: '2026-09', to: '2026-09', channel: null, rows: [],
    delayed: false, note: '',
  });
  vi.mocked(getIncomeReport).mockResolvedValue({
    from: '2026-09', to: '2026-09', rows: [], delayed: false, note: '',
  });
  vi.mocked(listAlerts).mockResolvedValue({ alerts: [] });
  vi.mocked(getChannelErrors).mockResolvedValue({ channel: 'demo', service: 'polyglot-backend', groups: [] });
  vi.mocked(getDeployTargets).mockResolvedValue([
    { target: 'editor', target_family: 'editor', channel: 'demo', gated: false },
  ]);
  vi.mocked(listDeploys).mockResolvedValue([]);
});

describe('every page under src/pages renders exactly one purpose header', () => {
  it('enumerates the actual files on disk, not a hand-typed list', () => {
    const files = readdirSync(join(__dirname))
      .filter((f) => f.endsWith('.tsx') && !f.endsWith('.test.tsx'));
    // The set this describe block below exercises, one it() per page --
    // if a page is added to src/pages/ without a matching case here, this
    // assertion catches the omission (CLAUDE.md scar #8: pin the SET).
    expect(files.sort()).toEqual([
      'AlertsPage.tsx',
      'CostReportsPage.tsx',
      'DeploysPage.tsx',
      'ErrorsPage.tsx',
      'FirmDetailPage.tsx',
      'FirmsPage.tsx',
      'KitCommercialsPage.tsx',
      'MonitoringPage.tsx',
      'UsagePage.tsx',
      'UsersPage.tsx',
    ]);
  });

  it('UsersPage', async () => {
    render(<UsersPage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('FirmsPage', async () => {
    render(<FirmsPage onAuthExpired={noAuthExpired} onOpenFirm={noOp} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('FirmDetailPage (after its firm loads)', async () => {
    render(<FirmDetailPage firmId="firm-a" onAuthExpired={noAuthExpired} onBack={noOp} />);
    await waitFor(() => expect(getFirm).toHaveBeenCalled());
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('KitCommercialsPage', async () => {
    render(<KitCommercialsPage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('MonitoringPage', async () => {
    render(<MonitoringPage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('UsagePage', async () => {
    render(<UsagePage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('CostReportsPage', async () => {
    render(<CostReportsPage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('AlertsPage', async () => {
    render(<AlertsPage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('ErrorsPage', async () => {
    render(<ErrorsPage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });

  it('DeploysPage', async () => {
    render(<DeploysPage onAuthExpired={noAuthExpired} />);
    expect(await screen.findAllByTestId('page-intro')).toHaveLength(1);
  });
});
