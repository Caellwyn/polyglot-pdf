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
 * Ask the EXTRACTOR HOST whether it can see a nonce the browser just wrote into
 * the picked folder (bd polyglot-pdf-ball) -- the asker half of
 * verifySameFolder() for this channel.
 *
 * Why this exists separately from the backend's store-handshake
 * (bd polyglot-pdf-s2bf): extraction is served by the VITE DEV SERVER, whose
 * FORM_KITS_ROOT is a different setting from the backend's FORM_KITS_LOCAL_ROOT.
 * Agreement with the backend therefore does NOT prove agreement with the host
 * that actually writes schema.json, so this channel needs its own nonce read.
 *
 * A network failure or non-OK response resolves sameFolder=false: unproven must
 * never read as proven, because the action it gates is destructive.
 *
 * `reachable` distinguishes "the host answered, and said no" from "the host never
 * answered at all". Both refuse -- the verdict is identical and fail-closed -- but
 * they need DIFFERENT messages: a wrong folder is fixed by opening another one,
 * while a dead dev server is not, and telling that user their folder is wrong
 * sends them to change correct configuration. verifySameFolder's asker contract
 * has no slot for it, so it is reported out-of-band via `onUnreachable` rather
 * than by widening a shape shared with the backend channel.
 */
export async function verifyExtractorFolder(
  nonce: string,
  onUnreachable?: () => void,
): Promise<{ sameFolder: boolean; backendRoot?: string | null }> {
  const unreachable = () => {
    onUnreachable?.();
    return { sameFolder: false };
  };
  try {
    const res = await fetch(`${ENDPOINT}/handshake`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nonce }),
    });
    if (!res.ok) return unreachable();
    const body = (await res.json()) as { sameFolder?: boolean; extractorRoot?: string };
    // A body we cannot read as a verdict is the host failing to answer, not the
    // host answering "different folder".
    if (typeof body?.sameFolder !== 'boolean') return unreachable();
    // Map extractorRoot -> backendRoot: verifySameFolder's asker contract (and
    // the dialog that renders it) speaks of "the root the server uses"; here
    // that server is the extractor host.
    return { sameFolder: body.sameFolder === true, backendRoot: body.extractorRoot ?? null };
  } catch {
    return unreachable();
  }
}

/**
 * Run extraction for one kit by id. The server resolves the kit dir against its
 * own form-kits root (the browser's directory handle is opaque to the host), so
 * this is only safe once verifyExtractorFolder() has proven the editor's open
 * folder IS that root -- callers MUST gate on it (bd polyglot-pdf-ball), or the
 * extractor overwrites a same-id kit in a DIFFERENT copy, invisibly. pdfFile/
 * schemaFile carry the kit's metadata overrides so a non-default layout still
 * resolves. instructionsPdfFile (optional, bd s4dp.3) names an instructions PDF
 * already written into the kit dir; when set the server enriches help.instructions
 * from it, otherwise extraction is /TU-only.
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
