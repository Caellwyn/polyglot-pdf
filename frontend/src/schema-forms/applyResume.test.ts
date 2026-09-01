// @vitest-environment jsdom
//
// Applying a verified resume (bd polyglot-pdf-dft1).
//
// This is the moment a client's saved work becomes their live form, so the
// things worth pinning are what they would notice if it went wrong: their
// answers coming back, landing where they stopped, and being asked to agree
// again rather than inheriting a tick from a session that ended days ago.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { applyResume } from './applyResume';

/** Existing state holds FieldValue objects, not bare strings. */
function fv(value: string) {
  return { value, confirmed: true, lastModified: 1 };
}
import type { SchemaFormState } from './state/schemaFormState';

// THE REAL SHIPPED W-7, not a fixture. The invented one used
// `fields: [{ id }]` -- a shape no kit produces -- and was the sole reason the
// section-landing tests passed while the code returned the fallback for every
// real client. A fixture you invented cannot falsify an assumption you also
// invented.
const SCHEMA = JSON.parse(
  readFileSync(
    resolve(process.cwd(), '..', 'form-kits', 'w7', 'schema.json'),
    'utf-8',
  ),
);

/** Section ids in order, from the real schema. */
const SECTIONS: Array<{ id: string; fields: string[] }> = SCHEMA.sections;

function baseState(over: Partial<SchemaFormState> = {}): SchemaFormState {
  return {
    schema: SCHEMA,
    fieldValues: {},
    currentSectionId: SECTIONS[0].id,
    completedSections: new Set<string>(),
    validationErrors: {},
    lastUpdated: 1,
    formSessionId: 'fss_CURRENT',
    loadedFieldIds: new Set<string>(),
    jitModeEnabled: false,
    validatedWindowIndices: new Set<number>(),
    validatorFindingsQueue: [],
    continuousSessionEnabled: false,
    disclaimerAccepted: true,
    disclaimerAcceptedAt: 1234,
    ...over,
  } as unknown as SchemaFormState;
}

describe('applyResume', () => {
  it('brings the client ANSWERS back', () => {
    const next = applyResume(baseState(), {
      fieldValues: { last_name: 'Okonkwo', first_name: 'Adaeze' },
      linkJtis: [],
    });
    expect(next.fieldValues.last_name.value).toBe('Okonkwo');
    expect(next.fieldValues.first_name.value).toBe('Adaeze');
  });

  it('wraps restored answers as FIELD VALUE OBJECTS, not bare strings', () => {
    // tsc caught this and the tests did not: writing raw strings into
    // fieldValues corrupts every reader of .value / .confirmed / .lastModified.
    const next = applyResume(baseState(), {
      fieldValues: { last_name: 'Okonkwo' },
      linkJtis: [],
    });
    const entry = next.fieldValues.last_name;
    expect(entry.value).toBe('Okonkwo');
    expect(entry.confirmed).toBe(true);
    expect(typeof entry.lastModified).toBe('number');
    // From the client's own FILE, not from something the assistant heard.
    expect(entry.confirmationMethod).toBe('manual_edit');
  });

  it('lets the UPLOAD win over a half-typed remnant in this tab', () => {
    // The client saved, walked away, and came back with a file. That file is
    // their real work; whatever is still sitting in this tab is not.
    const next = applyResume(
      baseState({ fieldValues: { last_name: fv('half-typed') } }),
      { fieldValues: { last_name: 'Okonkwo' }, linkJtis: [] },
    );
    expect(next.fieldValues.last_name.value).toBe('Okonkwo');
  });

  it('keeps values the upload does not mention', () => {
    const next = applyResume(
      baseState({ fieldValues: { note: fv('kept') } }),
      { fieldValues: { last_name: 'Okonkwo' }, linkJtis: [] },
    );
    expect(next.fieldValues.note.value).toBe('kept');
  });

  it('RE-ACCEPTS the disclaimer', () => {
    // A new working session should say the client agreed in THIS one, not
    // inherit a tick from a session that ended who knows when.
    const next = applyResume(baseState(), { fieldValues: {}, linkJtis: [] });
    expect(next.disclaimerAccepted).toBe(false);
    expect(next.disclaimerAcceptedAt).toBeUndefined();
  });

  it('lands the client where they STOPPED, not at question one', () => {
    // Answer every field of the FIRST section, from the real schema, and the
    // client should land on the second -- not back at the start.
    const answered: Record<string, string> = {};
    for (const fieldId of SECTIONS[0].fields) answered[fieldId] = 'x';

    const next = applyResume(baseState(), { fieldValues: answered, linkJtis: [] });

    expect(next.currentSectionId).toBe(SECTIONS[1].id);
    expect(next.currentSectionId).not.toBe(SECTIONS[0].id);
  });

  it('stays put when every field is answered', () => {
    const answered: Record<string, string> = {};
    for (const section of SECTIONS) {
      for (const fieldId of section.fields) answered[fieldId] = 'x';
    }
    const last = SECTIONS[SECTIONS.length - 1].id;

    const next = applyResume(baseState({ currentSectionId: last }), {
      fieldValues: answered,
      linkJtis: [],
    });

    expect(next.currentSectionId).toBe(last);
  });

  it('CARRIES the session id so one form stays one record', () => {
    // bd polyglot-pdf-1uyof: a client who burned through two links should
    // still aggregate as a single piece of work.
    const next = applyResume(baseState(), {
      fieldValues: {},
      formSessionId: 'fss_CARRIED',
      linkJtis: ['jti-a', 'jti-b'],
    });
    expect(next.formSessionId).toBe('fss_CARRIED');
  });

  it('keeps the current session id when the file carried none', () => {
    // Some viewers strip metadata on save. The answers are the point; losing
    // the stamp must not cost the client their resume.
    const next = applyResume(baseState(), { fieldValues: { last_name: 'X' }, linkJtis: [] });
    expect(next.formSessionId).toBe('fss_CURRENT');
    expect(next.fieldValues.last_name.value).toBe('X');
  });

  it('brings back a checkbox_group answer as an ARRAY, not a stringified list (bd polyglot-pdf-8ewxs)', () => {
    // /api/resume-form returns Dict[str, str | list[str]] -- a checkbox_group
    // answer comes back as a real list, not a scalar. ResumePayload.fieldValues
    // (and FieldValue.value) were declared Record<string, string> even though
    // the array shape already survived the round-trip at runtime; this pins
    // the declaration matches reality AND that applyResume's merge does not
    // coerce/collapse the array along the way (e.g. String(value), or a
    // .join(',') "normalization" that looked harmless on scalar strings).
    const next = applyResume(baseState(), {
      fieldValues: { last_name: 'Okonkwo', race: ['white', 'asian'] },
      linkJtis: [],
    });
    expect(next.fieldValues.race.value).toEqual(['white', 'asian']);
    expect(Array.isArray(next.fieldValues.race.value)).toBe(true);
    // The scalar sibling in the SAME payload must be unaffected -- this is
    // not a fix that only works when every value is an array.
    expect(next.fieldValues.last_name.value).toBe('Okonkwo');
  });

  it('brings back a standalone checkbox answer as a BOOLEAN, not a stringified "true" (bd polyglot-pdf-8ewxs, Opus cross-surface finding 1)', () => {
    // /api/resume-form's actual return shape is
    // Dict[str, str | list[str] | bool] -- pdf_fill_routes.py restores a
    // standalone checkbox as the client's own `True`, not the PDF's
    // on-state. The first version of this bead's fix only widened the
    // union to string|string[], still refusing the bool this shape
    // actually needs -- caught by the Opus cross-surface review (a tsc
    // probe: `{fieldValues: {agrees: true}, linkJtis: []}` failed
    // TS2322 against the pre-fix union).
    const next = applyResume(baseState(), {
      fieldValues: { last_name: 'Okonkwo', agrees: true },
      linkJtis: [],
    });
    expect(next.fieldValues.agrees.value).toBe(true);
    expect(typeof next.fieldValues.agrees.value).toBe('boolean');
    expect(next.fieldValues.last_name.value).toBe('Okonkwo');
  });

  it('does not mutate the state handed in', () => {
    const before = baseState({ fieldValues: { last_name: fv('old') } });
    applyResume(before, { fieldValues: { last_name: 'new' }, linkJtis: [] });
    expect(before.fieldValues.last_name.value).toBe('old');
    expect(before.disclaimerAccepted).toBe(true);
  });

  it('survives a schema with no sections', () => {
    const next = applyResume(
      baseState({ schema: { form_metadata: {} } as never, currentSectionId: 'x' }),
      { fieldValues: { a: '1' }, linkJtis: [] },
    );
    expect(next.currentSectionId).toBe('x');
    expect(next.fieldValues.a.value).toBe('1');
  });
});
