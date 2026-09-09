// @vitest-environment jsdom
//
// getAdminApiBaseUrl() and getAppChannel() (bd polyglot-pdf-z4ljj, Epic 2
// Track C bead C0). Both are build-time-only reads of import.meta.env --
// unlike getBackendUrl() they have no runtime/localStorage override chain,
// so what needs pinning is the ENV -> RETURN mapping, especially
// getAppChannel()'s fallback: an unset or unrecognized VITE_APP_CHANNEL must
// resolve to 'demo', never pass a typo through to the admin service's
// `?channel=` (which 404s on anything outside KNOWN_CHANNELS) and never
// silently claim 'staging' for a bare/local build.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { APP_CHANNELS, getAdminApiBaseUrl, getAppChannel } from './config';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('getAdminApiBaseUrl', () => {
  it('returns the build-time VITE_ADMIN_API_BASE_URL', () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', 'https://polyglot-admin-abc123-uc.a.run.app');
    expect(getAdminApiBaseUrl()).toBe('https://polyglot-admin-abc123-uc.a.run.app');
  });

  it('returns an empty string when unset, not undefined', () => {
    vi.stubEnv('VITE_ADMIN_API_BASE_URL', undefined);
    expect(getAdminApiBaseUrl()).toBe('');
  });
});

describe('getAppChannel', () => {
  it('returns "demo" when VITE_APP_CHANNEL=demo', () => {
    vi.stubEnv('VITE_APP_CHANNEL', 'demo');
    expect(getAppChannel()).toBe('demo');
  });

  it('returns "staging" when VITE_APP_CHANNEL=staging', () => {
    vi.stubEnv('VITE_APP_CHANNEL', 'staging');
    expect(getAppChannel()).toBe('staging');
  });

  it('defaults to "demo" when VITE_APP_CHANNEL is unset', () => {
    // The "unset means demo" convention this repo uses everywhere (backend
    // link_channel(), the form-kits bucket default, etc.) -- a local dev
    // build or a bare `vite build` must never silently claim 'staging'.
    vi.stubEnv('VITE_APP_CHANNEL', undefined);
    expect(getAppChannel()).toBe('demo');
  });

  it('defaults to "demo" on an unrecognized value rather than passing it through', () => {
    // A typo'd env var (e.g. "Staging", "prod") must not mint a channel query
    // param the admin service does not know -- it 404s any value outside its
    // own KNOWN_CHANNELS, so passing a typo through just moves the failure
    // somewhere harder to diagnose.
    vi.stubEnv('VITE_APP_CHANNEL', 'prod');
    expect(getAppChannel()).toBe('demo');
  });

  it('APP_CHANNELS is exactly {demo, staging} -- there is no prod', () => {
    expect(APP_CHANNELS).toEqual(['demo', 'staging']);
  });
});
