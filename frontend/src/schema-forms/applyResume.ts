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
import type { SchemaFormState } from './state/schemaFormState';

export interface ResumePayload {
  fieldValues: Record<string, string>;
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
  const sections =
    (state.schema as unknown as { sections?: Array<{ id?: string; fields?: Array<{ id?: string }> }> })
      .sections ?? [];

  for (const section of sections) {
    const fields = section.fields ?? [];
    const unanswered = fields.some((field) => {
      if (!field.id) return false;
      const entry = values[field.id] as { value?: unknown } | undefined;
      const value = entry?.value;
      return value === undefined || value === null || value === '';
    });
    if (unanswered && section.id) return section.id;
  }
  return state.currentSectionId;
}
