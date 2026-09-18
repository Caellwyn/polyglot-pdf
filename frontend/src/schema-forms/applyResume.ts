/**
 * Apply a verified resume to the client's form state (bd polyglot-pdf-dft1).
 *
 * Runs only AFTER /api/resume-form has confirmed the upload is structurally the
 * form this link assigned. Nothing here re-checks that; this is the merge, not
 * the gate.
 *
 * THE DISCLAIMER IS RE-ACCEPTED. Maintainer, 2026-08-27: *"we might as well
 * have them agree to the disclaimer again, since it's a very small
 * inconvenience"*. It is also the honest thing for the acceptance record: the
 * client is starting a new working session, and the audit trail should say they
 * agreed in THIS one rather than inheriting a tick from a session that ended
 * who-knows-when.
 *
 * THE CARRIED SESSION ID IS KEPT WHEN THERE IS ONE. That is what lets one
 * client's form read as ONE record even when it took two links (bd
 * polyglot-pdf-1uyof) -- their disclaimer acceptance and field confirmations
 * from before the save join up with the ones after it.
 */
import type { FieldValue } from './types/schema';
import { readFieldEntryWithAlias } from './utils/fieldValue';
import type { SchemaFormState } from './state/schemaFormState';

export interface ResumePayload {
  /** A checkbox_group answer arrives as string[], a standalone checkbox as
   * bool (bd polyglot-pdf-8ewxs) -- matches ResumeUpload's
   * ResumeResult.fieldValues, which this is always fed from verbatim. */
  fieldValues: Record<string, string | string[] | boolean>;
  formSessionId?: string;
  linkJtis: string[];
}

/**
 * Merge a verified resume into existing state.
 *
 * Returns a NEW state object; the caller persists it. Pure on purpose -- the
 * decisions here (which values win, what the disclaimer does, which section to
 * land on) are worth testing without a store or a component in the way.
 */
export function applyResume(
  current: SchemaFormState,
  payload: ResumePayload,
): SchemaFormState {
  // The UPLOAD wins on conflict. A client who saved, walked away, and came
  // back is telling us the file is their real work -- whatever half-typed
  // remnant survives in this tab is not.
  //
  // Values arrive as bare strings from the PDF and must be wrapped as
  // FieldValue objects: writing raw strings into fieldValues would corrupt
  // state everywhere that reads .value, .confirmed or .lastModified. tsc
  // caught this; the tests did not, because they asserted on what the merge
  // returned rather than on its shape.
  //
  // MANUAL_EDIT, not ai_voice: these answers came from the client's own file,
  // not from something the assistant heard in this session. The confirmation
  // record should not claim otherwise.
  const stamped = Date.now();
  const restored: Record<string, FieldValue> = {};
  for (const [fieldId, raw] of Object.entries(payload.fieldValues)) {
    restored[fieldId] = {
      value: raw,
      confirmed: true,
      confirmedAt: new Date(stamped).toISOString(),
      confirmationMethod: 'manual_edit',
      lastModified: stamped,
    };
  }
  const fieldValues = { ...current.fieldValues, ...restored };

  // Land them on the first section that still has an unanswered field, so a
  // client who saved at question 60 does not restart at question 1.
  const currentSectionId = firstIncompleteSection(current, fieldValues);

  return {
    ...current,
    fieldValues,
    currentSectionId,
    // Re-accept, deliberately (see the module docstring).
    disclaimerAccepted: false,
    disclaimerAcceptedAt: undefined,
    // Keep the carried identity so both halves of one form aggregate.
    formSessionId: payload.formSessionId || current.formSessionId,
    lastUpdated: stamped,
  };
}

/**
 * The first section holding a field with no value, or the current one when
 * every section is answered.
 */
function firstIncompleteSection(
  state: SchemaFormState,
  values: Record<string, unknown>,
): string {
  // section.fields is string[] of FIELD IDS -- declared that way in
  // types/schema.ts and stored that way in all three shipped kits. An earlier
  // version walked them as objects with .id, behind an `as unknown as` cast
  // that hid the mismatch from tsc, so this returned the fallback for EVERY
  // kit and a client who saved at question 60 restarted at question 1 -- the
  // exact outcome this function exists to prevent. Found in cross-surface
  // review, after I had already reported it fixed.
  const schema = state.schema as unknown as {
    sections?: Array<{ id?: string; fields?: string[] }>;
  };

  for (const section of schema.sections ?? []) {
    const unanswered = (section.fields ?? []).some((fieldId) => {
      if (typeof fieldId !== 'string') return false;
      // Read through the []-alias (bd polyglot-pdf-db1en).
      //
      // The drifting side is the SECTION LIST, not the payload. Resume keys are
      // bracket-stable by construction -- pdf_fill_routes.py derives every one
      // from the schema's own `field.get("id")` verbatim (only the WIDGET name
      // uses a suffix fallback). What can disagree is a `section.fields` entry
      // versus the `field.id` it names, so the id this loop iterates may carry
      // the opposite bracket form from the key the payload actually used.
      //
      // A bare read then misses a real answer, the group counts as UNANSWERED,
      // and this function lands the returning client on an EARLIER section than
      // they reached -- the precise "saved at question 60, restarted at
      // question 1" outcome the note above says this function exists to
      // prevent. (Causal direction corrected in cross-surface review, bd
      // polyglot-pdf-gob5v; the read itself was already right.)
      const entry = readFieldEntryWithAlias(
        values as Record<string, FieldValue>,
        fieldId
      ) as { value?: unknown } | undefined;
      const value = entry?.value;
      return value === undefined || value === null || value === '';
    });
    if (unanswered && section.id) return section.id;
  }
  return state.currentSectionId;
}
