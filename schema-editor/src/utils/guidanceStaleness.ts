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
import type { FormField, FormSchema } from '../types/schema';
import type { LintFinding } from './remoteKitStore';

/** The lint rule the backend emits for a drifted field identity. */
export const GUIDANCE_STALE_RULE = 'guidance-identity-stale';

/**
 * The authoring stage whose provenance a consumer reads. The
 * option-translation re-run checker (another session) records its own
 * identity_sha1 under its own stage and can reuse these helpers by passing
 * 'option_translation' rather than forking a parallel implementation.
 */
export type ProvenanceStage = 'instructions_enrich' | 'option_translation';

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
 * The identity hash the BAKE recorded for this field, read straight out of the
 * schema's provenance block. The editor never computes this (the backend owns
 * hashing); it only needs the value to pin an acknowledgment to.
 */
export function bakedIdentity(
  schema: FormSchema,
  fieldId: string,
  stage: ProvenanceStage = 'instructions_enrich',
): string | undefined {
  const bakeoff = (schema as unknown as Record<string, unknown>)._bakeoff;
  const authoring =
    bakeoff && typeof bakeoff === 'object' && !Array.isArray(bakeoff)
      ? (bakeoff as Record<string, unknown>).authoring
      : undefined;
  const stageObj =
    authoring && typeof authoring === 'object' && !Array.isArray(authoring)
      ? (authoring as Record<string, unknown>)[stage]
      : undefined;
  const prov =
    stageObj && typeof stageObj === 'object' && !Array.isArray(stageObj)
      ? (stageObj as Record<string, unknown>).provenance
      : undefined;
  const rec =
    prov && typeof prov === 'object' && !Array.isArray(prov)
      ? (prov as Record<string, unknown>)[fieldId]
      : undefined;
  const h =
    rec && typeof rec === 'object' && !Array.isArray(rec)
      ? (rec as Record<string, unknown>).identity_sha1
      : undefined;
  return typeof h === 'string' && h ? h : undefined;
}

/**
 * Has a human acknowledged the guidance for this field's CURRENT state?
 *
 * The acknowledgment stores the hash it was given for. On a LATER edit the
 * backend re-bakes/re-flags against a new identity, so the stored ack no longer
 * matches and the gate re-raises -- an ack is not a permanent waiver.
 * `baked` is the hash currently recorded for the field; pass undefined when
 * none is recorded (then any ack is honoured, since nothing is being gated).
 */
export function isAcknowledged(field: FormField, baked?: string): boolean {
  const ack = field._review?.guidance_ack_sha1;
  if (typeof ack !== 'string' || !ack) return false;
  return baked === undefined || ack === baked;
}

/**
 * The gate: this field's guidance drifted and nobody has acknowledged it.
 * `staleIds` comes from staleFieldIds(lintFindings).
 */
export function needsGuidanceAck(
  field: FormField,
  staleIds: Set<string>,
  baked?: string,
): boolean {
  if (!staleIds.has(field.id)) return false;
  return !isAcknowledged(field, baked);
}
