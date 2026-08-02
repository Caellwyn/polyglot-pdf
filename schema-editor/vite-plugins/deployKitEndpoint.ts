/**
 * Dev-only single-kit deploy endpoint (bd polyglot-pdf-ipzh).
 *
 * Adds `POST /api/deploy-kit` to the Vite dev server, which runs
 * scripts/deploy-form-kit.sh <kit-id> on the host: it uploads THAT KIT's files
 * to the GCS bucket and regenerates the manifest. The human clicks "Deploy this
 * form" on a complete kit's card instead of dropping to a terminal.
 *
 * WHAT IT DELIBERATELY IS NOT: this is not deploy-demo.sh. It ships kit DATA
 * only -- no Cloud Run backend, no Firebase Hosting, no application code. A full
 * demo deploy stays a maintainer-run command gated on explicit per-instance
 * permission (CLAUDE.md "Deployment / promotion"); nothing here changes that.
 *
 * WHY A HOST ENDPOINT: the editor is a browser SPA. It cannot run gcloud, so the
 * upload must happen on the host. Mirrors extractEndpoint.ts, the existing
 * privileged-local-action precedent, including its `apply: 'serve'` so a static
 * production build simply has no such route.
 *
 * SECURITY, three layers, because this one PUBLISHES:
 *   - apply:'serve' keeps it out of every production bundle, so the hosted
 *     editor (whose users are contractors, not the maintainer) cannot reach it;
 *   - the same-origin guard refuses a cross-origin POST, so a malicious page
 *     cannot no-cors trigger a publish against localhost;
 *   - the kit id is validated as ONE safe path segment and the resolved kit dir
 *     must sit inside the form-kits root, so a crafted id cannot escape it.
 * The UI adds a confirmation naming the kit and bucket before it ever POSTs --
 * that is what keeps a deploy a deliberate act rather than a stray click.
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

/** The demo bucket the deploy script defaults to when FORM_KITS_BUCKET is unset. */
const DEFAULT_BUCKET = 'polyglot-demo-aa709-form-kits';

export interface DeployKitResponse {
  ok: boolean;
  detail: string;
  /** Tail of the script's combined output, so a failure is diagnosable in the UI. */
  output?: string;
  /** Where it went (or would go) -- shown in the confirm dialog and the result. */
  bucket?: string;
}

export interface DeployKitEndpointOptions {
  repoRoot?: string;
  formKitsRoot?: string;
  bucket?: string;
}

function sendJson(res: ServerResponse, status: number, body: DeployKitResponse): void {
  const payload = JSON.stringify(body);
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Content-Length', Buffer.byteLength(payload));
  res.end(payload);
}

/**
 * Refuse a cross-origin POST. Same reasoning as extractEndpoint: this is a
 * side-effecting localhost endpoint, and here the side effect is a PUBLISH.
 * A request with no Origin header (curl, same-origin fetch in some browsers) is
 * allowed -- the header is only present on cross-origin requests we must refuse.
 */
export function isSameOrigin(req: Connect.IncomingMessage): boolean {
  const origin = req.headers.origin;
  if (!origin) return true;
  const host = req.headers.host;
  if (!host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Read a JSON body, bounded so a huge payload cannot exhaust the dev server. */
async function readJsonBody(req: Connect.IncomingMessage): Promise<unknown> {
  const MAX = 64 * 1024;
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX) throw new Error('request body too large');
    chunks.push(chunk as Buffer);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown;
}

/**
 * Validate the kit id and prove the resolved directory sits inside the root.
 * Returns the absolute kit dir, or null with the reason already sent.
 */
export function resolveKitDir(
  kitId: unknown, formKitsRoot: string,
): { dir: string } | { error: string } {
  if (typeof kitId !== 'string' || !KIT_ID_RE.test(kitId)) {
    return { error: 'missing or invalid kit id (must be a single safe folder name)' };
  }
  const dir = path.resolve(formKitsRoot, kitId);
  const rel = path.relative(formKitsRoot, dir);
  if (rel.startsWith('..') || path.isAbsolute(rel)) {
    return { error: 'kit id escapes the form-kits root' };
  }
  return { dir };
}

/**
 * A kit must be status:complete to deploy. The deploy script skips non-complete
 * kits anyway (kit_is_complete), so without this check the button would report
 * a cheerful success for an upload that silently did nothing.
 */
export function readKitStatus(kitDir: string): string | null {
  try {
    const raw = fs.readFileSync(path.join(kitDir, 'metadata.json'), 'utf8');
    const meta = JSON.parse(raw) as { status?: unknown };
    return typeof meta.status === 'string' ? meta.status : null;
  } catch {
    return null;
  }
}

async function handleDeploy(
  req: Connect.IncomingMessage,
  res: ServerResponse,
  opts: { formKitsRoot: string; repoRoot: string; script: string; bucket: string },
): Promise<void> {
  const body = await readJsonBody(req) as { kitId?: unknown };
  const resolved = resolveKitDir(body.kitId, opts.formKitsRoot);
  if ('error' in resolved) {
    sendJson(res, 400, { ok: false, detail: resolved.error });
    return;
  }
  const kitId = body.kitId as string;

  if (!fs.existsSync(resolved.dir)) {
    sendJson(res, 404, { ok: false, detail: `no kit "${kitId}" in ${opts.formKitsRoot}` });
    return;
  }
  const status = readKitStatus(resolved.dir);
  if (status !== 'complete') {
    // Refuse rather than run: the script would skip it and exit 0, which would
    // read as a successful deploy that uploaded nothing.
    sendJson(res, 409, {
      ok: false,
      detail: `"${kitId}" is ${status ?? 'not marked'}, not complete -- only a `
        + 'complete kit deploys. Mark it complete first (which runs the publish '
        + 'checks and the translation sweep).',
    });
    return;
  }
  if (!fs.existsSync(opts.script)) {
    sendJson(res, 500, { ok: false, detail: `deploy script not found at ${opts.script}` });
    return;
  }

  const child = spawn('bash', [opts.script, kitId], {
    cwd: opts.repoRoot,
    env: { ...process.env, FORM_KITS_BUCKET: opts.bucket },
  });
  let out = '';
  const cap = (chunk: Buffer) => {
    out += chunk.toString('utf8');
    // Keep only the tail: a full gcloud transcript is large and only the end
    // carries the verdict.
    if (out.length > 8000) out = out.slice(-8000);
  };
  child.stdout.on('data', cap);
  child.stderr.on('data', cap);

  await new Promise<void>((resolve) => {
    child.on('error', (err) => {
      sendJson(res, 500, {
        ok: false, bucket: opts.bucket,
        detail: `could not run the deploy script: ${err.message}`,
        output: out,
      });
      resolve();
    });
    child.on('close', (code) => {
      if (res.headersSent) { resolve(); return; }
      if (code === 0) {
        sendJson(res, 200, {
          ok: true, bucket: opts.bucket,
          detail: `Deployed "${kitId}" to ${opts.bucket}.`,
          output: out,
        });
      } else {
        // Surface the real failure (unauthenticated gcloud, missing bucket,
        // permission denied) rather than a generic message.
        sendJson(res, 500, {
          ok: false, bucket: opts.bucket,
          detail: `deploy failed (exit ${code}) -- see the output below.`,
          output: out,
        });
      }
      resolve();
    });
  });
}

export function deployKitEndpoint(options: DeployKitEndpointOptions = {}): Plugin {
  return {
    name: 'schema-editor-deploy-kit-endpoint',
    apply: 'serve', // dev only -- never in a production build
    configureServer(server) {
      const editorDir = process.cwd(); // vite runs from schema-editor/
      const repoRoot = path.resolve(options.repoRoot
        ?? process.env.SCHEMA_EDITOR_REPO_ROOT
        ?? path.join(editorDir, '..'));
      const formKitsRoot = path.resolve(options.formKitsRoot
        ?? process.env.FORM_KITS_ROOT
        ?? path.join(repoRoot, 'form-kits'));
      const script = path.join(repoRoot, 'scripts', 'deploy-form-kit.sh');
      const bucket = options.bucket ?? process.env.FORM_KITS_BUCKET ?? DEFAULT_BUCKET;

      server.middlewares.use('/api/deploy-kit', (req, res) => {
        // Capability probe: the UI calls GET to learn the endpoint exists, and
        // reads the bucket so the confirm dialog can NAME where this will go.
        if (req.method === 'GET') {
          sendJson(res, 200, { ok: true, detail: 'deploy endpoint available', bucket });
          return;
        }
        if (req.method !== 'POST') {
          sendJson(res, 405, { ok: false, detail: 'use POST to deploy a kit' });
          return;
        }
        if (!isSameOrigin(req)) {
          sendJson(res, 403, { ok: false, detail: 'cross-origin deploy requests are refused' });
          return;
        }
        handleDeploy(req, res, { formKitsRoot, repoRoot, script, bucket }).catch((err) => {
          if (!res.headersSent) {
            sendJson(res, 500, {
              ok: false,
              detail: err instanceof Error ? err.message : 'internal error',
            });
          }
        });
      });
    },
  };
}
