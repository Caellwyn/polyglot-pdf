/**
 * Client for the dev-only extraction endpoint (bd polyglot-pdf-7a9.17).
 *
 * The schema-editor is a browser SPA and cannot run the PDF->schema extractor
 * itself (it spawns Python + the local `claude` CLI on the host). The Vite dev
 * server exposes POST /api/extract (vite-plugins/extractEndpoint.ts) to run it;
 * these helpers are the browser side.
 *
 * Capability probe: a static production build has NO such endpoint, so the UI
 * calls isExtractionAvailable() first and shows the "Run extraction" button only
 * when it resolves true. That keeps the deployed editor's drag-drop + instructions
 * flow intact (no broken button) while the local editor gains the one-click path.
 */

export interface ExtractionResult {
  ok: boolean;
  /** Validation detail on success, or the failure reason. */
  detail: string;
  schemaFile?: string;
  exitCode?: number;
}

const ENDPOINT = '/api/extract';

/**
 * Probe whether the host-side extraction endpoint exists (it does only under
 * `vite dev`). Resolves false on any network/non-OK response so a static build
 * -- where the route 404s or the fetch fails -- simply hides the button.
 */
export async function isExtractionAvailable(): Promise<boolean> {
  try {
    const res = await fetch(ENDPOINT, { method: 'GET' });
    if (!res.ok) return false;
    const body = (await res.json()) as { ok?: boolean };
    return body.ok === true;
  } catch {
    return false;
  }
}

/**
 * Run extraction for one kit by id. The server resolves the kit dir against its
 * own form-kits root (the browser's directory handle is opaque to the host), so
 * this works when the editor's open folder is the server's form-kits root -- the
 * normal local-dev case. pdfFile/schemaFile carry the kit's metadata overrides
 * so a non-default layout still resolves. instructionsPdfFile (optional, bd
 * s4dp.3) names an instructions PDF already written into the kit dir; when set the
 * server enriches help.instructions from it, otherwise extraction is /TU-only.
 */
export async function runExtraction(
  id: string,
  opts: { pdfFile?: string; schemaFile?: string; instructionsPdfFile?: string } = {},
): Promise<ExtractionResult> {
  let res: Response;
  try {
    res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, ...opts }),
    });
  } catch (err) {
    return { ok: false, detail: err instanceof Error ? err.message : 'network error' };
  }
  let body: ExtractionResult;
  try {
    body = (await res.json()) as ExtractionResult;
  } catch {
    return { ok: false, detail: `extractor returned a non-JSON response (HTTP ${res.status})` };
  }
  return body;
}
