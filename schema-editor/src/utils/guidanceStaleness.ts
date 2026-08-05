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
 * The hash covers what SHAPES THE AUTHORED GUIDANCE -- name, spoken_name, each
 * option's label and spoken label BOUND to its stored value, and the field's
 * TYPE. The binding is what makes a SWAP flag (two labels -- or two spoken
 * labels, which outrank labels as the voice join key -- trading places, values
 * fixed): the text multiset is unchanged, but the assistant's unchanged words
 * would select a different stored answer -- a wrong answer on the form, not
 * just stale wording (bd anim handoff decision; tradeoffs in identity_payload's
 * docstring, backend/services/guidance_contract.py).
 *
 * TYPE is hashed even though it is never SPOKEN (bd polyglot-pdf-stkz): the
 * test is "does changing it make the authored guidance WRONG?", not "is it read
 * aloud?" -- a text -> date change rewrites the expected answer SHAPE while
 * every spoken text stays identical. The type is hashed NORMALIZED: every
 * option-carrying field contributes one "choice" token, so the
 * guidance-neutral kind flips (changeGroupKind's radio <-> checkbox_group,
 * schema_repair's checkbox -> checkbox_group) cannot raise the gate -- only a
 * SCALAR type change flags. It never covers the field id (renames are
 * retargeted wholesale by fieldRename, and an id is not spoken) or plumbing
 * like pdf_field_name. Changing those does not make guidance wrong, so hashing
 * them would manufacture false staleness.
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
    // Use the CENTRALIZED field_id the backend already derived -- bd h76m.11
    // deliberately moved that parse into Python so the frontend would not fork
    // a second regex that can drift from it.
    if (f.field_id) out.add(f.field_id);
  }
  return out;
}

/**
 * The field's CURRENT identity hash, as reported by the backend in the
 * staleness finding's PATH (`...help[identity:<hash>]`).
 *
 * This -- NOT the baked hash -- is what an acknowledgment pins to. The baked
 * value is frozen at bake time and does not change when a human edits, so
 * pinning an ack to it would make one click a permanent waiver covering every
 * later edit until the next re-bake (bd anim fresh-eyes finding 1). The
 * current hash changes on every material edit, so each new drift re-raises the
 * gate, which is the whole point of the feature.
 */
export function currentIdentity(findings: LintFinding[] | undefined,
                                fieldId: string): string | undefined {
  for (const f of findings ?? []) {
    if (!f || f.rule !== GUIDANCE_STALE_RULE) continue;
    if (f.field_id !== fieldId) continue;   // centralized id (bd h76m.11)
    // The hash rides the PATH, never the message: `message` is rendered to
    // humans in three places, so a raw hash there is unexplained noise.
    //
    // ANCHORED to the end of the path (bd polyglot-pdf-g5vj). The backend
    // builds `fields (id=<fid>).help[identity:<sha1>]`, interpolating the
    // field id AHEAD of the token, so an unanchored .exec would return an
    // id's own embedded `[identity:<hex>]` substring instead of the real
    // trailing hash. That mis-parse pins the ack to a string that never
    // changes, turning one click into a PERMANENT WAIVER -- precisely the
    // hole current-identity pinning exists to close. Unreachable today (ids
    // are slugified to alnum+underscore), so this is hardening, but the
    // parse is the contract's only client-side anchor and deserves to be
    // robust rather than merely lucky.
    const hm = /\[identity:([0-9a-f]+)\]$/.exec(f.path ?? '');
    if (hm) return hm[1];
  }
  return undefined;
}

/**
 * Has a human acknowledged the guidance for the field's CURRENT content?
 *
 * `current` is the identity the backend is flagging right now. An ack recorded
 * against a DIFFERENT identity means the human confirmed older content, so the
 * gate re-raises -- an ack is never a permanent waiver. With no current
 * identity available nothing is being gated, so any ack is honoured.
 */
export function isAcknowledged(field: FormField, current?: string): boolean {
  const ack = field._review?.guidance_ack_sha1;
  if (typeof ack !== 'string' || !ack) return false;
  return current === undefined || ack === current;
}

/**
 * The gate: this field's guidance drifted and nobody has acknowledged THIS
 * version of it. `staleIds` / `current` both come from the backend findings.
 */
export function needsGuidanceAck(
  field: FormField,
  staleIds: Set<string>,
  current?: string,
): boolean {
  if (!staleIds.has(field.id)) return false;
  // A flagged field with NO parseable current identity fails OPEN: there is
  // nothing to pin an ack to (withGuidanceAck without an identity is a
  // no-op), so gating here would deadlock the field behind a checkbox that
  // cannot record anything (Opus round). Unreachable from today's backend --
  // the path format is contract-pinned -- and consistent with
  // isAcknowledged's documented mercy for the same condition.
  if (current === undefined) return false;
  return !isAcknowledged(field, current);
}

/**
 * Whole-schema aggregation of needsGuidanceAck: the ids of every field whose
 * guidance drifted and has no acknowledgment for its CURRENT content. The
 * completion counters now apply the same per-field gate directly
 * (reviewStatus.isCountedReviewed calls needsGuidanceAck inside reviewCounts,
 * sprint-18 C1), so the kit-wide "% reviewed" can never report a field
 * complete while its row sits amber behind the gate -- the progress figure and
 * the FieldList icons must tell the same story (bd anim fresh-eyes finding,
 * closeout round 1).
 */
export function needsAckFieldIds(
  fields: FormField[] | undefined,
  findings: LintFinding[] | undefined,
): Set<string> {
  const out = new Set<string>();
  const stale = staleFieldIds(findings);
  if (stale.size === 0) return out;
  for (const f of fields ?? []) {
    if (!f) continue;
    // Delegate to the SAME per-field gate the FieldList row uses --
    // including its unparseable-identity fail-open -- so the counters and
    // the icons can never disagree (Opus round 2: the fail-open guard was
    // added to the row gate but hand-mirrored logic here missed it,
    // splitting the "% reviewed" figure from the rows it summarizes).
    if (needsGuidanceAck(f, stale, currentIdentity(findings, f.id))) {
      out.add(f.id);
    }
  }
  return out;
}
