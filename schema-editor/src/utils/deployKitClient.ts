/**
 * Client for the dev-only single-kit deploy endpoint (bd polyglot-pdf-ipzh).
 *
 * Mirrors extractionClient: the browser cannot run gcloud, so the upload happens
 * on the VITE DEV HOST (vite-plugins/deployKitEndpoint.ts). That endpoint exists
 * only under `vite dev` -- a static/hosted build simply has no such route, which
 * is what keeps the hosted editor (contractor users) from publishing.
 *
 * Uploads THAT KIT's data only. It is not deploy-demo.sh: no Cloud Run, no
 * Firebase Hosting, no application code.
 *
 * ASCII only.
 */

export interface DeployKitResult {
  ok: boolean;
  detail: string;
  output?: string;
  bucket?: string;
}

/**
 * Is the deploy endpoint present, and where would it publish?
 *
 * Returns null when absent (a static build, or the plugin disabled), which the
 * UI reads as "do not offer the button". Never throws: a probe failure must read
 * as unavailable, not crash the catalogue.
 */
export async function getDeployTarget(): Promise<{ bucket: string } | null> {
  try {
    const res = await fetch('/api/deploy-kit', { method: 'GET' });
    if (!res.ok) return null;
    const body = await res.json() as DeployKitResult;
    if (!body.ok) return null;
    return { bucket: body.bucket ?? 'the configured bucket' };
  } catch {
    return null;
  }
}

/**
 * Upload one complete kit. Resolves with the endpoint's verdict either way --
 * `ok:false` carries the real reason (not complete, gcloud unauthenticated,
 * bucket unreachable) so the editor can show it instead of a silent no-op.
 */
export async function deployKit(kitId: string): Promise<DeployKitResult> {
  let res: Response;
  try {
    res = await fetch('/api/deploy-kit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kitId }),
    });
  } catch (err) {
    return {
      ok: false,
      detail: err instanceof Error
        ? `could not reach the deploy endpoint: ${err.message}`
        : 'could not reach the deploy endpoint',
    };
  }
  try {
    return await res.json() as DeployKitResult;
  } catch {
    return { ok: false, detail: `deploy endpoint returned ${res.status}` };
  }
}
