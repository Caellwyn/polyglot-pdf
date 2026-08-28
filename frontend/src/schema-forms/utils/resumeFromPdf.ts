/**
 * Read a client's saved PDF back into a resumable form state (bd dft1).
 *
 * THE CLIENT'S FILE NEVER LEAVES THEIR BROWSER. Everything here runs on bytes
 * the client picked from their own disk, using pdf-lib, which the app already
 * depends on. Uploading the file to read it would put a document full of the
 * client's answers on our servers -- exactly what the stateless-architecture
 * rule and the split-key privacy design exist to avoid.
 *
 * WHAT COMES BACK, and from where:
 *   - their ANSWERS, out of the PDF's form fields (keyed by pdf_field_name)
 *   - their IDENTITY, out of the metadata stamp written by /api/fill-pdf
 *
 * THE STAMP IS A HINT, NEVER A CREDENTIAL. A client can edit PDF metadata with
 * free tools, so nothing read here may grant access, entitlement, or spend:
 *   - entitlement still comes from the signed link (bd ugm6)
 *   - the kit id is a SUGGESTION about which form to reopen, to be checked
 *     against what the caller may actually see
 *   - a forged jti buys nothing: spend keys on the SIGNED token at the socket
 * The backend re-validates the session id on read (services/resume_stamp.py);
 * this module mirrors that shape so a hostile file is refused on BOTH sides
 * rather than either trusting the other to have checked.
 */
import { PDFDocument } from 'pdf-lib';

import type { FormSchema } from '../types/schema';

/** Mirrors backend STAMP_VERSION. Decline anything else rather than guess. */
export const STAMP_VERSION = 1;

/** Same bound as the backend's MAX_STAMP_BYTES. */
const MAX_STAMP_BYTES = 8192;

/**
 * Mirrors backend `_is_safe_session_id`. The id reaches a FILENAME server-side,
 * so a hand-edited "../../../etc/passwd" must never be adopted as this
 * session's identity and sent onward.
 */
const SESSION_ID_RE = /^[A-Za-z0-9_.-]{1,128}$/;
const WINDOWS_DEVICE_NAMES = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
  'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
]);

function isSafeSessionId(value: unknown): value is string {
  if (typeof value !== 'string' || !value) return false;
  if (value.includes('..')) return false;
  if (!SESSION_ID_RE.test(value)) return false;
  if (value.replace(/\./g, '') === '') return false;
  if (value.endsWith('.')) return false;
  // Windows matches the device name before the extension, case-insensitively.
  const stem = value.split('.', 1)[0].toUpperCase();
  return !WINDOWS_DEVICE_NAMES.has(stem);
}

export interface ResumeStamp {
  formSessionId: string;
  kitId?: string;
  schemaVersion?: string;
  linkJtis: string[];
}

export interface ResumedForm {
  stamp: ResumeStamp;
  /** schema field id -> value, ready to merge into form state. */
  fieldValues: Record<string, string>;
  /** Fields present in the PDF that this schema does not know about. */
  unmatchedPdfFields: string[];
}

/** Parse the metadata stamp. Returns null for anything unusable, never throws. */
export function parseResumeStamp(raw: string | undefined | null): ResumeStamp | null {
  if (typeof raw !== 'string' || !raw) return null;
  if (raw.length > MAX_STAMP_BYTES) return null;

  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    // A PDF whose keywords hold ordinary keywords, which is what that field
    // is for. Not ours, not an error.
    return null;
  }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) return null;

  const rec = data as Record<string, unknown>;
  if (rec.v !== STAMP_VERSION) return null;          // decline, do not guess
  if (!isSafeSessionId(rec.fsid)) return null;

  const jtis = Array.isArray(rec.jtis)
    ? rec.jtis.filter((j): j is string => typeof j === 'string' && !!j)
    : [];

  return {
    formSessionId: rec.fsid,
    kitId: typeof rec.kit === 'string' && rec.kit ? rec.kit : undefined,
    schemaVersion: typeof rec.sv === 'string' && rec.sv ? rec.sv : undefined,
    linkJtis: jtis,
  };
}

/**
 * Map pdf_field_name -> schema field id, so PDF values land on the right
 * fields. Built from the SCHEMA rather than guessed from field names: the two
 * namespaces differ (a schema id like `applicant_last_name` maps to a PDF
 * widget like `form1[0].#subform[0].f1_5[0]`).
 */
function buildPdfFieldIndex(schema: FormSchema): Map<string, string> {
  const index = new Map<string, string>();
  const sections = (schema as unknown as { sections?: unknown[] }).sections ?? [];
  for (const section of sections) {
    const fields = (section as { fields?: unknown[] }).fields ?? [];
    for (const field of fields) {
      const f = field as { id?: string; pdf_field_name?: string };
      if (f.id && f.pdf_field_name) index.set(f.pdf_field_name, f.id);
    }
  }
  return index;
}

/**
 * Read a saved PDF into a resumable state.
 *
 * Throws only when the file is not a readable PDF at all -- the caller shows
 * "we could not read that file". A readable PDF with no stamp resolves to
 * null, which is a different message: "this does not look like a saved form".
 */
export async function readResumeFromPdf(
  bytes: Uint8Array,
  schema: FormSchema,
): Promise<ResumedForm | null> {
  const doc = await PDFDocument.load(bytes, { ignoreEncryption: true });

  const stamp = parseResumeStamp(doc.getKeywords());
  if (!stamp) return null;

  const index = buildPdfFieldIndex(schema);
  const fieldValues: Record<string, string> = {};
  const unmatchedPdfFields: string[] = [];

  const form = doc.getForm();
  for (const field of form.getFields()) {
    const pdfName = field.getName();
    let value: string | undefined;

    // Read by TYPE. A checkbox has no getText, and calling it would throw
    // partway through and lose every field after it.
    const kind = field.constructor.name;
    try {
      if (kind === 'PDFTextField') {
        value = (field as { getText?: () => string | undefined }).getText?.() ?? undefined;
      } else if (kind === 'PDFCheckBox') {
        value = (field as { isChecked?: () => boolean }).isChecked?.() ? 'true' : undefined;
      } else if (kind === 'PDFDropdown' || kind === 'PDFRadioGroup') {
        const selected = (field as { getSelected?: () => string[] }).getSelected?.();
        value = Array.isArray(selected) && selected.length ? selected[0] : undefined;
      }
    } catch {
      // One unreadable widget must not cost the client the rest of their form.
      value = undefined;
    }

    if (value === undefined || value === '') continue;

    const schemaId = index.get(pdfName);
    if (schemaId) {
      fieldValues[schemaId] = value;
    } else {
      unmatchedPdfFields.push(pdfName);
    }
  }

  return { stamp, fieldValues, unmatchedPdfFields };
}
