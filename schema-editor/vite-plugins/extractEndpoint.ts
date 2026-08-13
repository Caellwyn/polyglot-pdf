/**
 * Dev-only extraction endpoint (bd polyglot-pdf-7a9.17).
 *
 * Makes the schema-editor a stand-alone PDF -> schema tool: a `POST /api/extract`
 * route on the Vite dev server spawns scripts/authoring/extract_form.py for one
 * form kit, so the human clicks "Run extraction" in the editor instead of running
 * a terminal command.
 *
 * WHY a server endpoint at all: the editor is a pure browser SPA that reads/writes
 * via the File System Access API. A browser cannot spawn Python or the local
 * `claude` CLI, so the extraction MUST run on the host. This plugin is the host
 * side -- present ONLY under `vite dev`. A static production build has no such
 * endpoint; the editor degrades to drag-drop + "run the extraction" instructions
 * (the UI hides the button when GET /api/extract is absent). The actual LLM
 * out-call is selected behind the Python provider seam (llm_providers.py): local
 * `claude` CLI by default, swappable to a remote backend by env -- this endpoint
 * stays dev/local regardless.
 *
 * SECURITY: the form-kits root is a SERVER-side path (FORM_KITS_ROOT, default the
 * repo's form-kits/). The request carries only a kit `id` (a folder name). The id
 * is validated as a single path segment and the resolved kit dir is confirmed to
 * sit inside the root, so a crafted id cannot escape the root (path traversal).
 * The endpoint binds to the Vite dev server (localhost) only.
 *
 * ASCII only, consistent with the repo's source-file convention.
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import type { ServerResponse } from 'node:http';
import type { Plugin, Connect } from 'vite';

/** A kit id must be ONE safe path segment: no separators, no `..`, no leading dot. */
const KIT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

/**
 * The marker the browser drops in the picked folder for this host to read
 * (bd polyglot-pdf-ball). MUST match EXTRACTOR_HANDSHAKE_FILE in
 * src/utils/formKitDirectory.ts -- the browser writes it, this host reads it.
 * Pinned by markerNames.contract.test.ts; do not edit one side alone.
 *
 * DISTINCT from the backend channel's `.editor-store-check.json` on purpose
 * (bd polyglot-pdf-bagn): both handshakes run against the same picked folder and
 * are not serialized, so a shared name let either channel's cleanup delete the
 * other's in-flight marker and refuse a folder that genuinely agrees.
 */
const HANDSHAKE_FILE = '.editor-extract-check.json';

// Monotonic per-process counter so each extraction gets a UNIQUE temp filename
// (process.pid is constant for the Vite server, so it alone cannot disambiguate
// two concurrent requests for the same kit).
let _requestCounter = 0;
function nextRequestId(): number { return ++_requestCounter; }

/**
 * A safe metadata filename: any chars EXCEPT path separators, and not `.`/`..`.
 * Looser than KIT_ID_RE on purpose -- metadata.json may legitimately point at a
 * filename with spaces ("Form W-7.pdf"), which the browser catalogue accepts, so
 * the endpoint must too (Codex r2). We constrain ONLY traversal: no `/` or `\`,
 * and reject the `.`/`..` segments. Containment is still enforced downstream by
 * resolving inside kitDir.
 */
function isSafeFilename(name: string): boolean {
  if (name === '.' || name === '..') return false;
  if (name.includes('/') || name.includes('\\')) return false;
  if (name.includes('\0')) return false;
  return name.length > 0;
}

export interface ExtractEndpointOptions {
  /**
   * Absolute or editor-relative path to the form-kits root the server resolves
   * kit ids against. Defaults to FORM_KITS_ROOT env, else the repo's form-kits/
   * (../form-kits relative to the schema-editor dir). This is the kit id ->
   * filesystem-path bridge the browser's opaque dir handles cannot provide.
   */
  formKitsRoot?: string;
  /** Repo root used to locate scripts/authoring/extract_form.py. Default ../. */
  repoRoot?: string;
}

interface ExtractRequest {
  id?: string;
  pdfFile?: string;    // metadata.pdf override; default form.pdf
  schemaFile?: string; // metadata.schema override; default schema.json
  force?: boolean;     // re-extract over an EXISTING schema (default: refuse)
  // OPTIONAL instructions PDF filename inside the SAME kit dir (bd s4dp.3). The
  // browser writes the uploaded instructions PDF into the kit folder (like the
  // form PDF) and passes its filename here; the server resolves it inside kitDir
  // and passes --instructions-pdf to the extractor. Absent -> /TU-only extraction.
  instructionsPdfFile?: string;
}

interface ExtractResponse {
  ok: boolean;
  /** Human-readable detail (validation result on success, error reason on failure). */
  detail: string;
  /** The schema filename written (so the client can refresh/open it). */
  schemaFile?: string;
  /** extract_form.py exit code, when it ran. */
  exitCode?: number;
}

function venvCandidates(root: string): string[] {
  // The venv interpreter is under Scripts/ on Windows, bin/ on POSIX.
  return [
    path.join(root, 'backend', '.venv', 'Scripts', 'python.exe'),
    path.join(root, 'backend', '.venv', 'bin', 'python'),
  ];
}

function resolvePythonExe(repoRoot: string): string {
  // EXTRACTOR_PYTHON wins (explicit override / CI). Then the repo venv (has
  // PyMuPDF etc.). CRUCIAL for worktrees: the backend/.venv lives ONLY in the
  // MAIN checkout, never in a worktree, so when repoRoot is a worktree we also
  // probe the main repo resolved via the git common dir -- otherwise the button
  // falls back to a bare `python3` that lacks PyMuPDF/google-genai and fails in
  // exactly the worktree setup this feature supports (Codex r2).
  const explicit = process.env.EXTRACTOR_PYTHON;
  if (explicit) {
    // Resolve to an ABSOLUTE path: the existence check runs from the Vite
    // process cwd but spawn() uses cwd: repoRoot, so a relative override would
    // be re-resolved against the wrong dir at spawn time (Codex r4). Resolve it
    // against repoRoot so check-time and spawn-time agree.
    const resolved = path.resolve(repoRoot, explicit);
    if (fs.existsSync(resolved)) return resolved;
  }

  const roots = [repoRoot];
  const mainRoot = resolveMainRepoRoot(repoRoot);
  if (mainRoot && mainRoot !== repoRoot) roots.push(mainRoot);

  for (const root of roots) {
    for (const c of venvCandidates(root)) {
      if (fs.existsSync(c)) return c;
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

/** The main checkout's root, even when repoRoot is a git worktree: the parent
 *  of `git rev-parse --git-common-dir` (which points at the main .git). Returns
 *  null if git can't resolve it (not a repo / git absent). */
function resolveMainRepoRoot(repoRoot: string): string | null {
  try {
    const out = spawnSync('git', ['-C', repoRoot, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
      { encoding: 'utf8' });
    if (out.status !== 0 || !out.stdout) return null;
    return path.dirname(out.stdout.trim());
  } catch {
    return null;
  }
}

/**
 * Kill the extractor AND its descendants (the `claude`/`gemini` process that
 * extract_form.py spawns). A plain child.kill() signals only the direct child
 * (the Python wrapper), so on POSIX we signal the process GROUP (the child was
 * spawned `detached`, so -pid addresses the group) and on Windows we taskkill the
 * tree (no process groups). Best effort -- the race where the child already
 * exited is fine.
 */
function killTree(child: ReturnType<typeof spawn>): void {
  const pid = child.pid;
  if (pid == null) { child.kill(); return; }
  try {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(pid), '/T', '/F']);
    } else {
      process.kill(-pid, 'SIGTERM'); // negative pid -> the whole process group
    }
  } catch {
    try { child.kill(); } catch { /* already gone */ }
  }
}

function readJsonBody(req: Connect.IncomingMessage): Promise<ExtractRequest> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on('data', (c: Buffer) => {
      size += c.length;
      if (size > 1_000_000) {
        // Stop accumulating: drain the rest of the stream so chunks[] does not
        // keep growing after we've already decided to reject.
        req.destroy();
        reject(new Error('request body too large'));
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8').trim();
      if (!raw) { resolve({}); return; }
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        reject(new Error('invalid JSON body'));
        return;
      }
      // Require a JSON OBJECT: JSON.parse("null")/"5"/"[]" are valid JSON but not
      // an ExtractRequest, and the later `body.id` access on a non-object would
      // throw (Codex r4). Reject them as a clean 400 instead.
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        reject(new Error('request body must be a JSON object'));
        return;
      }
      resolve(parsed as ExtractRequest);
    });
    req.on('error', reject);
  });
}

function sendJson(res: ServerResponse, status: number, body: ExtractResponse): void {
  sendRaw(res, status, body);
}

/** JSON responder for any payload shape (the handshake's differs from ExtractResponse). */
function sendRaw(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(payload);
}

/**
 * Same-origin check for the side-effecting POST. A browser sets `Origin` on
 * cross-origin (incl. no-cors) requests; a same-origin fetch from the editor
 * either omits Origin or sets it to the dev server's own origin. We accept only
 * when Origin is absent (same-origin fetch / curl) OR its host matches the
 * request's Host header. This blocks a malicious page from driving the endpoint.
 */
export function isSameOrigin(req: Connect.IncomingMessage): boolean {
  const origin = req.headers.origin;
  if (!origin) return true; // same-origin fetches may omit Origin; curl has none
  try {
    return new URL(origin).host === req.headers.host;
  } catch {
    return false; // unparseable Origin -> refuse
  }
}

export interface HandshakeResponse {
  /** True when THIS host read the same nonce back from its own form-kits root. */
  sameFolder: boolean;
  /** This host's root, so the refusal message can name the folder it would use. */
  extractorRoot?: string;
  /**
   * Why it failed: "mismatch" (nothing observed) or "stale" (a different nonce).
   *
   * DIAGNOSTIC ONLY -- no client reads this. The browser collapses both into one
   * refusal, because the remedy is identical (open the folder this host uses) and
   * the user cannot act on the difference. It is emitted for parity with the
   * backend's StoreHandshakeResponse (editor_kit_routes.py) and for anyone
   * reading the response by hand; do not wire a message off it without first
   * plumbing it through verifyExtractorFolder, which today drops it.
   */
  reason?: 'mismatch' | 'stale';
}

/**
 * Confirm the editor's picked folder and THIS host's form-kits root are one
 * directory (bd polyglot-pdf-ball).
 *
 * The backend's same-folder handshake (bd polyglot-pdf-s2bf) does NOT cover this
 * channel: extraction is served by the VITE DEV SERVER, whose FORM_KITS_ROOT is a
 * separate setting from the backend's FORM_KITS_LOCAL_ROOT. Proving the editor
 * agrees with the backend therefore proves nothing about where the extractor
 * writes -- so this host needs its own nonce read.
 *
 * Same proof-by-shared-observation as the backend's: the browser writes a fresh
 * nonce into the picked folder, this reads it back from the root it would
 * actually resolve kit ids against, and a match means both are looking at one
 * directory. READ-ONLY -- the browser owns the marker's lifecycle, so a
 * read-only root degrades to sameFolder=false rather than failing.
 *
 * Exported for unit tests.
 */
export async function handleHandshake(
  req: Connect.IncomingMessage,
  res: ServerResponse,
  ctx: { formKitsRoot: string },
): Promise<void> {
  let body: ExtractRequest & { nonce?: unknown };
  try {
    body = await readJsonBody(req);
  } catch (err) {
    sendRaw(res, 400, { sameFolder: false, detail: err instanceof Error ? err.message : 'bad request' });
    return;
  }
  const nonce = body.nonce;
  if (typeof nonce !== 'string' || !nonce) {
    sendRaw(res, 400, { sameFolder: false, detail: 'missing or invalid nonce' });
    return;
  }
  const markerPath = path.join(ctx.formKitsRoot, HANDSHAKE_FILE);
  let seen: string | null = null;
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(markerPath, 'utf8'));
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const val = (parsed as { nonce?: unknown }).nonce;
      seen = typeof val === 'string' ? val : null;
    }
  } catch {
    // Absent, unreadable, or unparseable -- all "nothing observed".
    seen = null;
  }
  const payload: HandshakeResponse = seen === null
    // Either the editor is pointed somewhere else, or it could not write its
    // marker. The browser knows which (it just tried the write), so it picks
    // the message; this only reports that nothing was observed.
    ? { sameFolder: false, extractorRoot: ctx.formKitsRoot, reason: 'mismatch' }
    : seen !== nonce
      // A STALE marker from an earlier session in a different folder. Same
      // verdict, but worth distinguishing from "no file at all".
      ? { sameFolder: false, extractorRoot: ctx.formKitsRoot, reason: 'stale' }
      : { sameFolder: true, extractorRoot: ctx.formKitsRoot };
  sendRaw(res, 200, payload);
}

/**
 * Whether a request targets the handshake sub-route. Connect's `use()` mounts on
 * a prefix and REWRITES req.url to the remainder ("/handshake"), but accept the
 * full path too so the check does not depend on that rewrite. Query/hash are
 * stripped first so "/handshake?x=1" still matches.
 *
 * Exported for unit tests.
 */
export function isHandshakePath(url: string | undefined): boolean {
  if (!url) return false;
  const pathOnly = url.split(/[?#]/)[0].replace(/\/+$/, '');
  return pathOnly === '/handshake' || pathOnly === '/api/extract/handshake';
}

/**
 * Vite plugin: registers POST/GET /api/extract on the dev server. GET is a cheap
 * capability probe (the UI uses it to decide whether to show the button); POST
 * runs the extraction for one kit. POST /api/extract/handshake proves the picked
 * folder is this host's own form-kits root before any extraction is allowed.
 */
export function extractEndpoint(options: ExtractEndpointOptions = {}): Plugin {
  return {
    name: 'schema-editor-extract-endpoint',
    apply: 'serve', // dev only -- never in a production build
    configureServer(server) {
      const editorDir = process.cwd(); // vite runs from schema-editor/
      const repoRoot = path.resolve(options.repoRoot
        ?? process.env.SCHEMA_EDITOR_REPO_ROOT
        ?? path.join(editorDir, '..'));
      const formKitsRoot = path.resolve(options.formKitsRoot
        ?? process.env.FORM_KITS_ROOT
        ?? path.join(repoRoot, 'form-kits'));
      const extractScript = path.join(repoRoot, 'scripts', 'authoring', 'extract_form.py');

      server.middlewares.use('/api/extract', (req, res) => {
        // Capability probe: the UI calls GET to learn the endpoint exists (and so
        // hides the button in a static build where this middleware is absent).
        if (req.method === 'GET') {
          sendJson(res, 200, { ok: true, detail: 'extraction endpoint available' });
          return;
        }
        if (req.method !== 'POST') {
          sendJson(res, 405, { ok: false, detail: 'use POST to run extraction' });
          return;
        }
        // Same-origin guard (Codex): this is a SIDE-EFFECTING localhost endpoint
        // (spawns a local/paid extractor, writes files). Without an origin check a
        // malicious page could no-cors POST to localhost and trigger it. Reject any
        // request whose Origin host is not this dev server's own host.
        if (!isSameOrigin(req)) {
          sendJson(res, 403, { ok: false, detail: 'cross-origin extraction requests are refused' });
          return;
        }
        // The same-folder handshake (bd polyglot-pdf-ball). `use()` mounts on a
        // PREFIX, so the sub-path arrives here with req.url rewritten to
        // "/handshake" -- dispatch on it before the extraction path. Guarded by
        // the same-origin check above: it reveals this host's form-kits root.
        if (isHandshakePath(req.url)) {
          handleHandshake(req, res, { formKitsRoot }).catch((err) => {
            if (!res.headersSent) {
              sendRaw(res, 500, {
                sameFolder: false,
                detail: err instanceof Error ? err.message : 'internal error',
              });
            }
          });
          return;
        }
        // Convert any async throw into the JSON error contract (Codex): a floating
        // promise would otherwise surface as an unhandled rejection that can take
        // down the dev server instead of returning 4xx/5xx.
        handleExtract(req, res, {
          formKitsRoot, extractScript, repoRoot,
          // Forward EXTRACTOR_MODEL to the script's --model so a configured
          // provider swap (e.g. EXTRACTOR_PROVIDER=gemini + a gemini-* model)
          // actually takes effect from the button (Codex). Unset -> the script's
          // own default (claude-opus-5) stands.
          model: process.env.EXTRACTOR_MODEL,
        }).catch((err) => {
          if (!res.headersSent) {
            sendJson(res, 500, { ok: false, detail: err instanceof Error ? err.message : 'internal error' });
          }
        });
      });
    },
  };
}

// Exported for unit tests (the request-validation contracts -- same-origin,
// traversal, type/filename checks, no-overwrite -- all return before spawn).
export async function handleExtract(
  req: Connect.IncomingMessage,
  res: ServerResponse,
  ctx: { formKitsRoot: string; extractScript: string; repoRoot: string; model?: string },
): Promise<void> {
  let body: ExtractRequest;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    sendJson(res, 400, { ok: false, detail: err instanceof Error ? err.message : 'bad request' });
    return;
  }

  // Type-check BEFORE the regex (Codex): a non-string id like {"id":123} would
  // coerce to "123" and pass KIT_ID_RE, then a non-string pdfFile/schemaFile
  // could throw deeper in. Require strings (or absent, for the optional ones).
  const id = body.id;
  if (typeof id !== 'string' || !KIT_ID_RE.test(id)) {
    sendJson(res, 400, { ok: false, detail: 'missing or invalid kit id (must be a single safe folder name)' });
    return;
  }
  if ((body.pdfFile != null && typeof body.pdfFile !== 'string')
      || (body.schemaFile != null && typeof body.schemaFile !== 'string')
      || (body.instructionsPdfFile != null && typeof body.instructionsPdfFile !== 'string')) {
    sendJson(res, 400, { ok: false, detail: 'pdfFile/schemaFile/instructionsPdfFile must be strings' });
    return;
  }
  // pdf/schema filenames are optional metadata overrides; require the expected
  // extension (so we never point the extractor at a non-PDF or write a non-.json)
  // but allow any otherwise-safe filename incl. SPACES ("Form W-7.pdf") -- the
  // browser catalogue accepts those, so the endpoint must too (Codex r2). Only
  // path separators / `.`/`..` are rejected (isSafeFilename); containment is
  // still enforced by resolving inside kitDir.
  const pdfFile = body.pdfFile ?? 'form.pdf';
  const schemaFile = body.schemaFile ?? 'schema.json';
  const validName = (name: string, ext: RegExp): boolean =>
    ext.test(name) && isSafeFilename(name);
  if (!validName(pdfFile, /\.pdf$/i) || !validName(schemaFile, /\.json$/i)) {
    sendJson(res, 400, { ok: false, detail: 'invalid pdf/schema filename (need a safe *.pdf / *.json name)' });
    return;
  }
  // Optional instructions PDF: same safe-*.pdf-name + in-kit-dir rule as the form
  // PDF (bd s4dp.3). Absent -> /TU-only extraction; the script handles a missing
  // --instructions-pdf gracefully.
  const instructionsPdfFile = body.instructionsPdfFile ?? undefined;
  if (instructionsPdfFile != null && !validName(instructionsPdfFile, /\.pdf$/i)) {
    sendJson(res, 400, { ok: false, detail: 'invalid instructionsPdfFile (need a safe *.pdf name)' });
    return;
  }

  const kitDir = path.resolve(ctx.formKitsRoot, id);
  // Confirm the resolved kit dir is INSIDE the root (defense in depth on top of
  // the id regex): a path that escapes the root is rejected.
  const rel = path.relative(ctx.formKitsRoot, kitDir);
  if (rel.startsWith('..') || path.isAbsolute(rel)) {
    sendJson(res, 400, { ok: false, detail: 'kit id resolves outside the form-kits root' });
    return;
  }
  if (!fs.existsSync(kitDir) || !fs.statSync(kitDir).isDirectory()) {
    sendJson(res, 404, {
      ok: false,
      // Do NOT say "set FORM_KITS_ROOT to match" (bd polyglot-pdf-ball): the
      // launcher starts TWO servers resolving kit ids independently, so naming
      // only the extractor's variable unblocks extraction while silently
      // switching every backend action off. Opening the named folder always
      // works; the README carries the two-variable recipe for the other route.
      detail: `kit "${id}" not found under the server's form-kits root (${ctx.formKitsRoot}). `
        + 'Open that folder in the editor (see the editor README to point the dev '
        + 'server somewhere else).',
    });
    return;
  }
  const pdfPath = path.join(kitDir, pdfFile);
  if (!fs.existsSync(pdfPath)) {
    sendJson(res, 404, { ok: false, detail: `no ${pdfFile} in kit "${id}"` });
    return;
  }
  // Resolve the optional instructions PDF inside the kit dir. If named but
  // missing on disk, refuse (the caller asked for enrichment from a file that is
  // not there) rather than silently degrading to /TU-only -- the browser writes
  // it before POSTing, so absence means something went wrong (bd s4dp.3).
  let instructionsPdfPath: string | undefined;
  if (instructionsPdfFile) {
    instructionsPdfPath = path.join(kitDir, instructionsPdfFile);
    if (!fs.existsSync(instructionsPdfPath)) {
      sendJson(res, 404, { ok: false, detail: `no ${instructionsPdfFile} in kit "${id}"` });
      return;
    }
  }

  const outPath = path.join(kitDir, schemaFile);
  // Refuse to clobber an EXISTING schema unless force=true (Codex): a stale
  // catalogue, a second tab, or a same-id kit in another root could otherwise
  // overwrite hand-reviewed work. `force` is the explicit re-extract opt-in.
  // Checked BEFORE the extractScript-exists check so the request is fully
  // validated (incl. the force gate) before we probe server tooling.
  if (fs.existsSync(outPath) && body.force !== true) {
    sendJson(res, 409, {
      ok: false,
      detail: `"${schemaFile}" already exists for kit "${id}"; re-extract would overwrite it `
        + '(pass force:true to replace it).',
      schemaFile,
    });
    return;
  }

  if (!fs.existsSync(ctx.extractScript)) {
    sendJson(res, 500, { ok: false, detail: `extractor not found at ${ctx.extractScript}` });
    return;
  }

  // Write to a TEMP file and promote only on a validated success (Codex): the
  // extractor writes outPath even when validation FAILS and exits non-zero, which
  // would leave a broken schema.json at the real path (hiding the Run button /
  // letting the user open a broken draft). Extracting to a temp + atomic rename
  // means a failed run never lands at outPath. The temp name is UNIQUE PER REQUEST
  // (pid is fixed for the Vite server, so a per-process counter is what prevents
  // two concurrent extractions of the same kit from racing on one temp -- Codex r2).
  const tmpOut = path.join(kitDir, `.extract_${process.pid}_${nextRequestId()}_${schemaFile}.tmp`);
  const py = resolvePythonExe(ctx.repoRoot);
  const args = [ctx.extractScript, '--pdf', pdfPath, '--out', tmpOut];
  if (ctx.model) args.push('--model', ctx.model);
  if (instructionsPdfPath) args.push('--instructions-pdf', instructionsPdfPath);
  // Local dev extraction is the extraction-STRATEGY-testing path, so the option
  // label-translation bake (bd 2h9j; pro-tier Gemini, default ON in the script)
  // is opted OUT here for cost efficiency -- otherwise a dev shell with
  // GEMINI_API_KEY/VERTEXAI exported would silently spend pro tokens on every
  // test run, with no local checkbox to stop it (the hosted editor has one).
  // Bake translations for a locally-authored kit via the decoupled paths:
  // scripts/authoring/translate_option_labels.py or the hosted editor's
  // Translate-options action.
  args.push('--no-translate-options');

  const cleanupTmp = () => { try { if (fs.existsSync(tmpOut)) fs.rmSync(tmpOut); } catch { /* best effort */ } };

  // `detached` puts the child in its OWN process group so an abort can kill the
  // WHOLE tree -- extract_form.py spawns the `claude`/`gemini` subprocess, and a
  // plain child.kill() would signal only the Python wrapper, leaving the
  // (paid, minutes-long) model process running after a tab close (Codex r3).
  const child = spawn(py, args, {
    cwd: ctx.repoRoot,
    env: { ...process.env, PYTHONUTF8: '1' }, // force UTF-8 stdio (cp1252 trap)
    detached: process.platform !== 'win32', // POSIX: new process group to signal
  });
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (d) => { stdout += d.toString(); });
  child.stderr.on('data', (d) => { stderr += d.toString(); });

  // Kill the (possibly minutes-long, possibly paid) extractor if the client
  // disconnects -- tab closed/refreshed, request aborted (Codex). During the long
  // run the abort surfaces on the RESPONSE (req was already consumed by
  // readJsonBody and its 'close' has usually fired), so listen on `res` -- and on
  // `req` too as a belt-and-suspenders (Codex r2: req.close alone misses the abort).
  // `responded` also suppresses the close handler's response in that case.
  let responded = false;
  const onClientGone = () => {
    if (responded) return;
    responded = true;
    killTree(child);
    cleanupTmp();
  };
  res.on('close', onClientGone);
  req.on('aborted', onClientGone);
  const detachClientGone = () => {
    res.off('close', onClientGone);
    req.off('aborted', onClientGone);
  };

  // A failed spawn (e.g. no Python on PATH) fires BOTH 'error' and 'close', so
  // guard against a double response -- the second sendJson would throw
  // ERR_HTTP_HEADERS_SENT after res.end() and bury the real diagnostic.
  child.on('error', (err) => {
    if (responded) return;
    responded = true;
    detachClientGone();
    cleanupTmp();
    sendJson(res, 500, { ok: false, detail: `failed to launch extractor: ${err.message}` });
  });
  child.on('close', (code) => {
    if (responded) return;
    responded = true;
    detachClientGone();
    // extract_form.py prints a "[OK]/[INVALID] wrote ... ; <validation detail>"
    // line. Surface its last line as the human-readable detail.
    const lines = (stdout + stderr).trim().split(/\r?\n/).filter(Boolean);
    const lastLine = lines.length ? lines[lines.length - 1] : '(no output)';

    // Tri-state exit code (extract_form.py EXIT_*): 0 VALID, 3 ISSUES, 1 HARD_FAIL.
    // Exit 3 means a USABLE draft was written that is invalid and/or carries lint
    // ERRORs -- the extractor's contract is "STORE it with its issue report", and
    // the hosted route does exactly that (editor_kit_routes.py, bd v96b). This
    // endpoint used to treat any nonzero code as failure and cleanupTmp() the
    // draft away, so a local extraction that hosted would have stored for repair
    // vanished with a bare "did not validate" -- the local-vs-hosted drift that
    // running the real backend locally exists to eliminate.
    //
    // Re-derive the usability floor from the WRITTEN draft rather than trusting
    // the exit code alone (mirrors the hosted route), so a mis-exit can never
    // store garbage: parseable JSON with >= 1 dict-shaped field.
    const EXIT_ISSUES = 3;
    const wrote = fs.existsSync(tmpOut);
    let usable = false;
    if (wrote && (code === 0 || code === EXIT_ISSUES)) {
      try {
        const draft = JSON.parse(fs.readFileSync(tmpOut, 'utf-8'));
        usable = Array.isArray(draft?.fields)
          && draft.fields.some((f: unknown) => f !== null && typeof f === 'object' && !Array.isArray(f));
      } catch {
        usable = false; // unparseable draft is no draft
      }
    }
    const storedWithIssues = usable && code === EXIT_ISSUES;
    const ok = usable;
    if (ok) {
      // Promote the temp file to the real path only on success.
      try {
        fs.renameSync(tmpOut, outPath);
      } catch (err) {
        cleanupTmp();
        sendJson(res, 500, { ok: false, detail: `extraction succeeded but could not write ${schemaFile}: ${err instanceof Error ? err.message : err}` });
        return;
      }
    } else {
      cleanupTmp(); // a failed run must not leave anything at outPath
    }
    // The script's detail line names its --out arg, which is the temp path; show
    // the real output path to the user instead of the internal .tmp name (replace
    // both the absolute temp path and its bare basename, whichever the line used).
    const cleanDetail = lastLine
      .split(tmpOut).join(outPath)
      .split(path.basename(tmpOut)).join(schemaFile);
    // A stored-with-issues draft must NOT read as a clean success: it is saved and
    // openable, but it has validation and/or lint problems to fix in the editor.
    // Say so in the detail line the catalogue renders.
    const detail = ok
      ? (storedWithIssues
        ? `stored with issues -- the draft was saved to ${schemaFile} but did not `
          + `fully validate; open it and fix the flagged fields. ${cleanDetail}`
        : cleanDetail)
      : `extraction failed (exit ${code}): ${cleanDetail}`;
    sendJson(res, ok ? 200 : 500, {
      ok,
      detail,
      schemaFile,
      exitCode: code ?? -1,
      storedWithIssues,
    });
  });
}
