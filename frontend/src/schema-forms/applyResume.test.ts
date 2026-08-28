// @vitest-environment jsdom
//
// Applying a verified resume (bd polyglot-pdf-dft1).
//
// This is the moment a client's saved work becomes their live form, so the
// things worth pinning are what they would notice if it went wrong: their
// answers coming back, landing where they stopped, and being asked to agree
// again rather than inheriting a tick from a session that ended days ago.
import { describe, it, expect } from 'vitest';

import { applyResume } from './applyResume';

/** Existing state holds FieldValue objects, not bare strings. */
function fv(value: string) {
  return { value, confirmed: true, lastModified: 1 };
}
import type { SchemaFormState } from './state/schemaFormState';

const SCHEMA = {
  form_metadata: { form_number: 'w7', version: '3' },
  sections: [
    { id: 'part1', fields: [{ id: 'last_name' }, { id: 'first_name' }] },
    { id: 'part2', fields: [{ id: 'address' }] },
    { id: 'part3', fields: [{ id: 'signature' }] },
  ],
};

function baseState(over: Partial<SchemaFormState> = {}): SchemaFormState {
  return {
    schema: SCHEMA,
    fieldValues: {},
    currentSectionId: 'part1',
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
    // A client who saved at part 3 restarting at part 1 would conclude the
    // resume did not work.
    const next = applyResume(baseState(), {
      fieldValues: { last_name: 'Okonkwo', first_name: 'Adaeze' },
      linkJtis: [],
    });
    expect(next.currentSectionId).toBe('part2');
  });

  it('stays put when every field is answered', () => {
    const next = applyResume(baseState({ currentSectionId: 'part3' }), {
      fieldValues: {
        last_name: 'Okonkwo',
        first_name: 'Adaeze',
        address: '1 Road',
        signature: 'AO',
      },
      linkJtis: [],
    });
    expect(next.currentSectionId).toBe('part3');
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
