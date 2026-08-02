/**
 * Request-validation contracts for the dev-only deploy endpoint
 * (bd polyglot-pdf-ipzh).
 *
 * These guards are the reason a localhost publish endpoint is acceptable at
 * all, so they are pinned separately from the UI tests: the endpoint spawns a
 * script that UPLOADS to a real GCS bucket, and the browser cannot be trusted to
 * be the only caller.
 *
 * Lives beside the plugin, matching extractEndpoint.test.ts.
 *
 * ASCII only.
 */
import { describe, it, expect } from 'vitest';
import { resolveKitDir, isSameOrigin } from './deployKitEndpoint';

const ROOT = 'C:/repo/form-kits';

describe('deployKitEndpoint: kit id validation', () => {
  it('refuses anything that is not one safe path segment', () => {
    // Traversal is the attack that matters: the id names a directory the
    // endpoint then hands to a deploy script.
    for (const bad of ['../../etc', '..', '../w7', 'a/b', 'a\\b', '', '.hidden']) {
      const r = resolveKitDir(bad, ROOT);
      expect('error' in r, `expected ${JSON.stringify(bad)} to be refused`).toBe(true);
    }
  });

  it('refuses a non-string id', () => {
    for (const bad of [undefined, null, 42, {}, ['w7']]) {
      expect('error' in resolveKitDir(bad, ROOT)).toBe(true);
    }
  });

  it('accepts real kit ids and keeps them inside the root', () => {
    for (const good of ['w7', 'i-90', 'w7_v2', 'f1040']) {
      const r = resolveKitDir(good, ROOT);
      expect('dir' in r, `expected ${good} to resolve`).toBe(true);
      if ('dir' in r) expect(r.dir.replace(/\\/g, '/')).toContain('form-kits/' + good);
    }
  });
});

describe('deployKitEndpoint: same-origin guard', () => {
  const mk = (origin: string | undefined, host: string | undefined) =>
    ({ headers: { origin, host } }) as never;

  it('refuses a cross-origin POST', () => {
    // Without this, a page the human happens to have open could no-cors POST to
    // localhost and publish a kit.
    expect(isSameOrigin(mk('http://evil.example', 'localhost:3001'))).toBe(false);
    expect(isSameOrigin(mk('http://localhost:5173', 'localhost:3001'))).toBe(false);
  });

  it('allows the dev server itself', () => {
    expect(isSameOrigin(mk('http://localhost:3001', 'localhost:3001'))).toBe(true);
  });

  it('allows a request with no Origin header', () => {
    // Origin is only sent on cross-origin requests; a same-origin fetch or curl
    // omits it, and refusing those would break the button itself.
    expect(isSameOrigin(mk(undefined, 'localhost:3001'))).toBe(true);
  });

  it('refuses a malformed Origin, and one with no Host to compare against', () => {
    expect(isSameOrigin(mk('not a url', 'localhost:3001'))).toBe(false);
    expect(isSameOrigin(mk('http://localhost:3001', undefined))).toBe(false);
  });
});
