/**
 * Tests for the dev-only extraction endpoint's REQUEST-VALIDATION contracts
 * (bd 7a9.17, Codex r2). These are the security + data-safety invariants the
 * endpoint must never regress: same-origin rejection, kit-id/filename validation
 * (incl. path traversal), and refuse-to-overwrite. Every path exercised here
 * returns BEFORE the extractor is spawned, so no Python runs -- we drive
 * `handleExtract` directly with mock req/res over a real temp form-kits dir.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  handleExtract, handleHandshake, isHandshakePath, isSameOrigin,
} from './extractEndpoint';

// --- mock req/res ----------------------------------------------------------- //
function mockReq(opts: {
  body?: unknown;
  headers?: Record<string, string>;
}): EventEmitter & { headers: Record<string, string> } {
  const req = new EventEmitter() as EventEmitter & { headers: Record<string, string>; destroy: () => void };
  req.headers = opts.headers ?? {};
  req.destroy = () => {};
  // Emit the body asynchronously so the readJsonBody 'data'/'end' listeners are
  // attached first (handleExtract awaits readJsonBody before anything else).
  queueMicrotask(() => {
    if (opts.body !== undefined) req.emit('data', Buffer.from(JSON.stringify(opts.body)));
    req.emit('end');
  });
  return req;
}

interface CapturedRes {
  statusCode: number;
  body: { ok: boolean; detail: string; schemaFile?: string };
  setHeader: () => void;
  end: (p: string) => void;
  on: () => void;
  off: () => void;
  headersSent: boolean;
}
function mockRes(): CapturedRes {
  const res: Partial<CapturedRes> = { statusCode: 200, headersSent: false };
  res.setHeader = () => {};
  res.on = () => {};
  res.off = () => {};
  res.end = (payload: string) => { res.body = JSON.parse(payload); res.headersSent = true; };
  return res as CapturedRes;
}

// --- temp form-kits fixture ------------------------------------------------- //
let root: string;
let ctx: { formKitsRoot: string; extractScript: string; repoRoot: string };

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'fk-'));
  // a kit with a pdf but no schema (the button's normal precondition)
  fs.mkdirSync(path.join(root, 'w7'));
  fs.writeFileSync(path.join(root, 'w7', 'form.pdf'), 'PDF');
  // ctx.extractScript points at a real existing file so the "extractor not found"
  // guard passes; we never actually spawn it because every test returns earlier.
  const scriptStub = path.join(root, 'extract_form.py');
  fs.writeFileSync(scriptStub, '# stub');
  ctx = { formKitsRoot: root, extractScript: scriptStub, repoRoot: root };
});
afterEach(() => { fs.rmSync(root, { recursive: true, force: true }); });

async function run(body: unknown, headers?: Record<string, string>): Promise<CapturedRes> {
  const req = mockReq({ body, headers });
  const res = mockRes();
  await handleExtract(req as never, res as never, ctx);
  return res;
}

describe('isSameOrigin', () => {
  it('accepts an absent Origin (same-origin fetch / curl)', () => {
    expect(isSameOrigin({ headers: {} } as never)).toBe(true);
  });
  it('accepts a matching Origin host', () => {
    expect(isSameOrigin({ headers: { origin: 'http://localhost:3001', host: 'localhost:3001' } } as never)).toBe(true);
  });
  it('rejects a cross-origin host', () => {
    expect(isSameOrigin({ headers: { origin: 'http://evil.example.com', host: 'localhost:3001' } } as never)).toBe(false);
  });
  it('rejects an unparseable Origin', () => {
    expect(isSameOrigin({ headers: { origin: 'not a url', host: 'localhost:3001' } } as never)).toBe(false);
  });
});

describe('handleExtract -- request validation (no spawn)', () => {
  it('rejects a non-string kit id (coercion guard)', async () => {
    const res = await run({ id: 123 });
    expect(res.statusCode).toBe(400);
    expect(res.body.detail).toMatch(/invalid kit id/i);
  });

  it('rejects a non-object JSON body (null/array/scalar)', async () => {
    for (const body of [null, 5, 'str', [1, 2]]) {
      const res = await run(body);
      expect(res.statusCode).toBe(400);
      expect(res.body.detail).toMatch(/must be a JSON object/i);
    }
  });

  it('rejects a traversal kit id', async () => {
    const res = await run({ id: '../escape' });
    expect(res.statusCode).toBe(400);
  });

  it('rejects a kit id that does not exist under the root', async () => {
    const res = await run({ id: 'nope' });
    expect(res.statusCode).toBe(404);
  });

  it('rejects a bad pdf extension override', async () => {
    const res = await run({ id: 'w7', pdfFile: 'form.exe' });
    expect(res.statusCode).toBe(400);
    expect(res.body.detail).toMatch(/filename/i);
  });

  it('rejects a filename with a path separator', async () => {
    const res = await run({ id: 'w7', schemaFile: 'sub/out.json' });
    expect(res.statusCode).toBe(400);
  });

  it('accepts a safe filename WITH SPACES (matches the catalogue)', async () => {
    // "Form W-7.pdf" is a valid metadata override; it must pass validation. The
    // pdf does not exist on disk so we expect a 404 (no such pdf) -- NOT a 400
    // (which would mean the name was wrongly rejected).
    const res = await run({ id: 'w7', pdfFile: 'Form W-7.pdf' });
    expect(res.statusCode).toBe(404);
    expect(res.body.detail).toMatch(/no Form W-7\.pdf/);
  });

  it('rejects a non-string instructionsPdfFile (coercion guard)', async () => {
    const res = await run({ id: 'w7', instructionsPdfFile: 123 });
    expect(res.statusCode).toBe(400);
    expect(res.body.detail).toMatch(/instructionsPdfFile must be strings/i);
  });

  it('rejects an instructionsPdfFile with a path separator (traversal)', async () => {
    const res = await run({ id: 'w7', instructionsPdfFile: '../escape.pdf' });
    expect(res.statusCode).toBe(400);
    expect(res.body.detail).toMatch(/instructionsPdfFile/i);
  });

  it('rejects a bad instructions PDF extension', async () => {
    const res = await run({ id: 'w7', instructionsPdfFile: 'instructions.exe' });
    expect(res.statusCode).toBe(400);
    expect(res.body.detail).toMatch(/instructionsPdfFile.*\.pdf/i);
  });

  it('404s when the named instructions PDF is missing from the kit dir', async () => {
    // The form.pdf exists, so we get past its check; the named instructions PDF
    // does not, so the endpoint refuses rather than silently degrading to /TU-only.
    const res = await run({ id: 'w7', instructionsPdfFile: 'instructions.pdf' });
    expect(res.statusCode).toBe(404);
    expect(res.body.detail).toMatch(/no instructions\.pdf/);
  });

  it('refuses to overwrite an existing schema without force', async () => {
    fs.writeFileSync(path.join(root, 'w7', 'schema.json'), '{}');
    const res = await run({ id: 'w7' });
    expect(res.statusCode).toBe(409);
    expect(res.body.detail).toMatch(/already exists/i);
  });

  it('force:true skips the overwrite gate', async () => {
    // The overwrite gate runs BEFORE the extractScript-exists check, so with an
    // existing schema + a missing script: WITHOUT force -> 409 (blocked at the
    // gate); WITH force -> 500 "extractor not found" (got past the gate). The
    // force flag is the only difference, so this isolates its effect.
    fs.writeFileSync(path.join(root, 'w7', 'schema.json'), '{}');
    ctx.extractScript = path.join(root, 'does-not-exist.py');

    const noForce = await run({ id: 'w7' });
    expect(noForce.statusCode).toBe(409);

    const withForce = await run({ id: 'w7', force: true });
    expect(withForce.statusCode).toBe(500);
    expect(withForce.body.detail).toMatch(/extractor not found/i);
  });
});

// --- same-folder handshake (bd polyglot-pdf-ball) --------------------------- //
//
// The extractor resolves a kit id against THIS host's form-kits root and writes
// schema.json there. If the editor's picked folder is a copy elsewhere, that is a
// silent overwrite of a DIFFERENT kit. These pin the nonce read that proves the
// two are one directory -- the gate the browser refuses on.

// The EXTRACTOR channel's marker -- distinct from the backend's
// .editor-store-check.json (bd polyglot-pdf-bagn). Coupled to the production
// declarations by src/utils/markerNames.contract.test.ts.
const HANDSHAKE_FILE = '.editor-extract-check.json';

async function handshake(body: unknown): Promise<CapturedRes> {
  const req = mockReq({ body });
  const res = mockRes();
  await handleHandshake(req as never, res as never, { formKitsRoot: root });
  return res;
}

describe('isHandshakePath', () => {
  it('matches the rewritten sub-path connect mounts on a prefix', () => {
    expect(isHandshakePath('/handshake')).toBe(true);
  });
  it('matches the full path too (independent of the use() rewrite)', () => {
    expect(isHandshakePath('/api/extract/handshake')).toBe(true);
  });
  it('ignores a query string', () => {
    expect(isHandshakePath('/handshake?x=1')).toBe(true);
  });
  it('does NOT match the extraction path itself', () => {
    expect(isHandshakePath('/')).toBe(false);
    expect(isHandshakePath(undefined)).toBe(false);
  });
});

describe('extract handshake', () => {
  it('reports sameFolder when it reads the SAME nonce from its own root', () => {
    fs.writeFileSync(path.join(root, HANDSHAKE_FILE), JSON.stringify({ nonce: 'n1' }));
    return handshake({ nonce: 'n1' }).then((res) => {
      expect(res.statusCode).toBe(200);
      expect((res.body as unknown as { sameFolder: boolean }).sameFolder).toBe(true);
    });
  });

  it('refuses when the marker is ABSENT -- the picked folder is a different one', async () => {
    // The bead's exact failure: the editor wrote its nonce into the folder it
    // opened, and this host cannot see it, because it is looking elsewhere.
    const res = await handshake({ nonce: 'n1' });
    const body = res.body as unknown as { sameFolder: boolean; reason: string; extractorRoot: string };
    expect(body.sameFolder).toBe(false);
    expect(body.reason).toBe('mismatch');
    // The refusal names the root the extractor WOULD have written to, so the
    // message can tell the human which folder to open.
    expect(body.extractorRoot).toBe(root);
  });

  it('refuses a STALE marker left by an earlier session', async () => {
    // A leftover from a previous check must never read as a match -- this is why
    // the nonce is minted per check rather than reused.
    fs.writeFileSync(path.join(root, HANDSHAKE_FILE), JSON.stringify({ nonce: 'old' }));
    const res = await handshake({ nonce: 'fresh' });
    const body = res.body as unknown as { sameFolder: boolean; reason: string };
    expect(body.sameFolder).toBe(false);
    expect(body.reason).toBe('stale');
  });

  it('refuses a corrupt/unparseable marker rather than throwing', async () => {
    fs.writeFileSync(path.join(root, HANDSHAKE_FILE), 'not json');
    const res = await handshake({ nonce: 'n1' });
    expect((res.body as unknown as { sameFolder: boolean }).sameFolder).toBe(false);
  });

  it('refuses a marker whose nonce is not a string', async () => {
    fs.writeFileSync(path.join(root, HANDSHAKE_FILE), JSON.stringify({ nonce: 42 }));
    const res = await handshake({ nonce: '42' });
    expect((res.body as unknown as { sameFolder: boolean }).sameFolder).toBe(false);
  });

  it('rejects a missing/blank nonce', async () => {
    expect((await handshake({})).statusCode).toBe(400);
    expect((await handshake({ nonce: '' })).statusCode).toBe(400);
    expect((await handshake({ nonce: 7 })).statusCode).toBe(400);
  });

  it('never creates or deletes the marker -- the browser owns its lifecycle', async () => {
    // Read-only on this side, so a read-only root degrades to sameFolder=false
    // instead of failing (mirrors the backend half, bd polyglot-pdf-s2bf).
    await handshake({ nonce: 'n1' });
    expect(fs.existsSync(path.join(root, HANDSHAKE_FILE))).toBe(false);

    fs.writeFileSync(path.join(root, HANDSHAKE_FILE), JSON.stringify({ nonce: 'n1' }));
    await handshake({ nonce: 'n1' });
    expect(fs.existsSync(path.join(root, HANDSHAKE_FILE))).toBe(true);
  });
});

// The marker-filename coupling (this host reader vs. the browser writer) is
// pinned in src/utils/markerNames.contract.test.ts (bd polyglot-pdf-kesf),
// which covers all THREE production declarations -- including the Python one --
// rather than only the two TS sides. Deliberately not duplicated here: a second
// copy keyed on the bare name `HANDSHAKE_FILE` would now match the BACKEND
// channel's constant in formKitDirectory.ts and compare the wrong pair.
