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
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { resolveKitDir, isSameOrigin, handleDeploy, DEFAULT_BUCKET } from './deployKitEndpoint';

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

// --- handleDeploy request validation (no spawn) ----------------------------- //
//
// Every guard below returns BEFORE the script is spawned, so these run without
// publishing anything. The complete-only refusal in particular is the guard
// specific to PUBLISHING -- a fresh-eyes round found it survived mutation
// because nothing pinned it, so it is pinned here.


function fakeReq(body: unknown): never {
  const chunks = body === undefined ? [] : [Buffer.from(JSON.stringify(body), 'utf8')];
  return {
    headers: { host: 'localhost:3001' },
    async *[Symbol.asyncIterator]() { for (const c of chunks) yield c; },
  } as never;
}

function fakeRes() {
  const state = { status: 0, body: null as unknown, headersSent: false };
  return {
    res: {
      get statusCode() { return state.status; },
      set statusCode(v: number) { state.status = v; },
      get headersSent() { return state.headersSent; },
      setHeader() {},
      end(payload: string) { state.headersSent = true; state.body = JSON.parse(payload); },
    } as never,
    state,
  };
}

function tmpRoot(): string {
  return fs.mkdtempSync(`${os.tmpdir()}/dk-`);
}

describe('handleDeploy: guards that run before any spawn', () => {
  const opts = (formKitsRoot: string) => ({
    formKitsRoot, repoRoot: formKitsRoot,
    // Deliberately a path that does not exist: if a guard ever FAILS to return
    // early, the script-missing 500 makes that loud instead of spawning.
    script: `${formKitsRoot}/__no_such_script.sh`,
    bucket: 'test-bucket',
  });

  it('refuses a kit that is not status:complete', async () => {
    // The deploy script SKIPS a non-complete kit and exits 0, so without this
    // refusal the button would report success for an upload that shipped
    // nothing. This is the publish-specific guard.
    const root = tmpRoot();
    fs.mkdirSync(`${root}/w7`);
    fs.writeFileSync(`${root}/w7/metadata.json`, JSON.stringify({ status: 'draft' }));
    const { res, state } = fakeRes();
    await handleDeploy(fakeReq({ kitId: 'w7' }), res, opts(root));
    expect(state.status).toBe(409);
    expect(String((state.body as { detail: string }).detail)).toMatch(/not complete/);
  });

  it('refuses a kit with no metadata.json at all', async () => {
    const root = tmpRoot();
    fs.mkdirSync(`${root}/w7`);
    const { res, state } = fakeRes();
    await handleDeploy(fakeReq({ kitId: 'w7' }), res, opts(root));
    expect(state.status).toBe(409);
  });

  it('404s a kit id that does not exist under the root', async () => {
    const root = tmpRoot();
    const { res, state } = fakeRes();
    await handleDeploy(fakeReq({ kitId: 'nope' }), res, opts(root));
    expect(state.status).toBe(404);
  });

  it('400s a traversing kit id before touching the filesystem', async () => {
    const root = tmpRoot();
    const { res, state } = fakeRes();
    await handleDeploy(fakeReq({ kitId: '../escape' }), res, opts(root));
    expect(state.status).toBe(400);
  });

  it('400s a non-object body instead of 500ing on a property access', async () => {
    const root = tmpRoot();
    const { res, state } = fakeRes();
    await handleDeploy(fakeReq(null), res, opts(root));
    expect(state.status).toBe(400);
  });

  it('reaches the script only for a COMPLETE kit -- and reports it missing', async () => {
    // Proves the guards above are what stopped the others: a complete kit gets
    // past them all and fails at the (deliberately absent) script instead.
    const root = tmpRoot();
    fs.mkdirSync(`${root}/w7`);
    fs.writeFileSync(`${root}/w7/metadata.json`, JSON.stringify({ status: 'complete' }));
    const { res, state } = fakeRes();
    await handleDeploy(fakeReq({ kitId: 'w7' }), res, opts(root));
    expect(state.status).toBe(500);
    expect(String((state.body as { detail: string }).detail)).toMatch(/script not found/);
  });
});

describe('deployKitEndpoint: default bucket parity with deploy-form-kit.sh (bd polyglot-pdf-d7hy)', () => {
  // The plugin always passes FORM_KITS_BUCKET explicitly when it spawns the
  // script (see handleDeploy's env block), so the script's OWN default only
  // matters for a bare CLI run with no env var set -- but if the two disagree,
  // "unset" silently means a different bucket depending on which caller runs.
  // This reads the actual script text rather than hand-copying its default, so
  // editing one side without the other fails here instead of drifting silently.
  it('scripts/deploy-form-kit.sh defaults FORM_KITS_BUCKET to the SAME bucket as the plugin', () => {
    const scriptPath = path.resolve(__dirname, '../../scripts/deploy-form-kit.sh');
    const scriptText = fs.readFileSync(scriptPath, 'utf-8');
    const m = scriptText.match(/BUCKET_NAME="\$\{FORM_KITS_BUCKET:-([^}]+)\}"/);
    expect(m, 'expected to find BUCKET_NAME="${FORM_KITS_BUCKET:-...}" in deploy-form-kit.sh').not.toBeNull();
    expect(m![1]).toBe(DEFAULT_BUCKET);
  });
});
