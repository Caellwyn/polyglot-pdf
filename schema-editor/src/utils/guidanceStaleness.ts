/**
 * Guidance staleness gate (bd polyglot-pdf-anim) -- the EDITOR half.
 *
 * A field's authored guidance (help.instructions / help.details) is written
 * against the field's IDENTITY at bake time: its name, spoken_name and option
 * labels. If a human later renames the field or relabels its options, the
 * guidance may no longer match what the voice AI will say -- but a trivial
 * rename ("applicant_phone" -> "applicant_phone_number") does not warrant an
 * LLM call to re-author it.
 *
 * So the flow is HUMAN-FIRST (maintainer design, 2026-07-27):
 *   1. The bake records identity_sha1 in
 *      _bakeoff.authoring.<stage>.provenance[fieldId].
 *   2. The BACKEND recomputes that hash during its normal lint pass and emits a
 *      `guidance-identity-stale` WARNING naming the field.
 *   3. The editor (this module) turns that finding into a gate: a stale field
 *      cannot be marked reviewed-correct until a human acknowledges the
 *      guidance is still right (free) or re-authors it (costly). Human review
 *      is ALWAYS the last step.
 *
 * WHY THE BACKEND OWNS THE HASH: the recorded hash is written by Python
 * (hashlib.sha1). If the editor recomputed it in JS it would need a
 * byte-identical SHA-1 of a byte-identical payload -- a cross-language contract
 * that silently breaks the moment either side's serialization drifts, and whose
 * failure mode is EVERY field reading as permanently stale (training editors to
 * click through the gate, which is worse than having no gate). Comparing hashes
 * where they are produced removes that whole class of bug; the editor consumes a
 * finding, exactly like every other lint signal it already renders.
 *
 * The hash covers ONLY voice-facing identity -- name, spoken_name, option
 * labels -- never the field id (renames are retargeted wholesale by
 * fieldRename, and an id is not spoken), option VALUES (internal slugs), or
 * plumbing like pdf_field_name. Changing those does not make guidance wrong, so
 * hashing them would manufacture false staleness.
 */
import type { FormField } from '../types/schema';
import type { LintFinding } from './remoteKitStore';

/** The lint rule the backend emits for a drifted field identity. */
export const GUIDANCE_STALE_RULE = 'guidance-identity-stale';

/**
 * The stale field ids named by a lint report. The backend anchors the finding
 * with the same `fields (id=X).help` path shape the other guidance rules use,
 * so the id parses out identically.
 */
export function staleFieldIds(findings: LintFinding[] | undefined): Set<string> {
  const out = new Set<string>();
  for (const f of findings ?? []) {
    if (!f || f.rule !== GUIDANCE_STALE_RULE) continue;
    const m = /\(id=([^)]+)\)/.exec(f.path ?? '');
    if (m) out.add(m[1]);
  }
  return out;
}

/**
 * Has a human acknowledged the guidance for this field's CURRENT state?
 *
 * The acknowledgment stores the backend's own recorded hash it was given for,
 * so a later edit (which changes the field and therefore the backend's freshly
 * emitted finding) leaves the stored ack pointing at a superseded identity --
 * an ack is not a permanent waiver. `bakedIdentity` is the hash the backend
 * currently reports for the field; pass undefined when it reports none.
 */
export function isAcknowledged(field: FormField, bakedIdentity?: string): boolean {
  const ack = field._review?.guidance_ack_sha1;
  if (typeof ack !== 'string' || !ack) return false;
  // With no current baked identity to pin to, any ack is honoured (the field is
  // not being reported stale, so there is nothing to gate).
  return bakedIdentity === undefined || ack === bakedIdentity;
}

/**
 * The gate: this field's guidance drifted and nobody has acknowledged it.
 * `staleIds` comes from staleFieldIds(lintFindings).
 */
export function needsGuidanceAck(
  field: FormField,
  staleIds: Set<string>,
  bakedIdentity?: string,
): boolean {
  if (!staleIds.has(field.id)) return false;
  return !isAcknowledged(field, bakedIdentity);
}
