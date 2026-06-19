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
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import type { ServerResponse } from 'node:http';
import type { Plugin, Connect } from 'vite';

/** A kit id must be ONE safe path segment: no separators, no `..`, no leading dot. */
const KIT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

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

function resolvePythonExe(repoRoot: string): string {
  // Prefer the repo venv (has PyMuPDF etc.); fall back to PATH python. On Windows
  // the venv interpreter is under Scripts/, on POSIX under bin/.
  const candidates = [
    path.join(repoRoot, 'backend', '.venv', 'Scripts', 'python.exe'),
    path.join(repoRoot, 'backend', '.venv', 'bin', 'python'),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function readJsonBody(req: Connect.IncomingMessage): Promise<ExtractRequest> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on('data', (c: Buffer) => {
      size += c.length;
      if (size > 1_000_000) { reject(new Error('request body too large')); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8').trim();
      if (!raw) { resolve({}); return; }
      try {
        resolve(JSON.parse(raw) as ExtractRequest);
      } catch {
        reject(new Error('invalid JSON body'));
      }
    });
    req.on('error', reject);
  });
}

function sendJson(res: ServerResponse, status: number, body: ExtractResponse): void {
  const payload = JSON.stringify(body);
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(payload);
}

/**
 * Vite plugin: registers POST/GET /api/extract on the dev server. GET is a cheap
 * capability probe (the UI uses it to decide whether to show the button); POST
 * runs the extraction for one kit.
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
        void handleExtract(req, res, { formKitsRoot, extractScript, repoRoot });
      });
    },
  };
}

async function handleExtract(
  req: Connect.IncomingMessage,
  res: ServerResponse,
  ctx: { formKitsRoot: string; extractScript: string; repoRoot: string },
): Promise<void> {
  let body: ExtractRequest;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    sendJson(res, 400, { ok: false, detail: err instanceof Error ? err.message : 'bad request' });
    return;
  }

  const id = body.id;
  if (!id || !KIT_ID_RE.test(id)) {
    sendJson(res, 400, { ok: false, detail: 'missing or invalid kit id (must be a single safe folder name)' });
    return;
  }
  // pdf/schema filenames are optional metadata overrides; constrain them to a
  // bare filename so they cannot redirect the read/write outside the kit dir.
  const pdfFile = body.pdfFile ?? 'form.pdf';
  const schemaFile = body.schemaFile ?? 'schema.json';
  if (!KIT_ID_RE.test(pdfFile.replace(/\.pdf$/i, '')) || !KIT_ID_RE.test(schemaFile.replace(/\.json$/i, ''))) {
    sendJson(res, 400, { ok: false, detail: 'invalid pdf/schema filename' });
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
      detail: `kit "${id}" not found under the server's form-kits root (${ctx.formKitsRoot}). `
        + 'Open that folder in the editor, or set FORM_KITS_ROOT to match.',
    });
    return;
  }
  const pdfPath = path.join(kitDir, pdfFile);
  if (!fs.existsSync(pdfPath)) {
    sendJson(res, 404, { ok: false, detail: `no ${pdfFile} in kit "${id}"` });
    return;
  }
  if (!fs.existsSync(ctx.extractScript)) {
    sendJson(res, 500, { ok: false, detail: `extractor not found at ${ctx.extractScript}` });
    return;
  }

  const outPath = path.join(kitDir, schemaFile);
  const py = resolvePythonExe(ctx.repoRoot);
  const args = [ctx.extractScript, '--pdf', pdfPath, '--out', outPath];

  const child = spawn(py, args, {
    cwd: ctx.repoRoot,
    env: { ...process.env, PYTHONUTF8: '1' }, // force UTF-8 stdio (cp1252 trap)
  });
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (d) => { stdout += d.toString(); });
  child.stderr.on('data', (d) => { stderr += d.toString(); });

  child.on('error', (err) => {
    sendJson(res, 500, { ok: false, detail: `failed to launch extractor: ${err.message}` });
  });
  child.on('close', (code) => {
    // extract_form.py prints a "[OK]/[INVALID] wrote ... ; <validation detail>"
    // line and exits 0 only when the draft validated. Surface its last line as
    // the human-readable detail.
    const lines = (stdout + stderr).trim().split(/\r?\n/).filter(Boolean);
    const lastLine = lines.length ? lines[lines.length - 1] : '(no output)';
    const ok = code === 0 && fs.existsSync(outPath);
    sendJson(res, ok ? 200 : 500, {
      ok,
      detail: ok ? lastLine : `extraction failed (exit ${code}): ${lastLine}`,
      schemaFile,
      exitCode: code ?? -1,
    });
  });
}
