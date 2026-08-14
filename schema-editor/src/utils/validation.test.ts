import { describe, it, expect } from 'vitest';
import {
  checkFieldComplete, safeOptions, safeOptionsPreservingArity, validateSchema,
} from './validation';
import type { FormSchema, FormField } from '../types/schema';

// Minimal valid field; override per test. read_only/pdf_field_name are the
// non-optional FormField props validateSchema does not itself require, but the
// type does.
function field(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id,
    name: id,
    type: 'text',
    pdf_field_name: id,
    read_only: false,
    section_id: 'sec-1',
    ...extra,
  };
}

function schemaWith(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Test',
      form_number: 'T-1',
      total_widgets: fields.length,
      total_fields: fields.length,
      version: '1',
      language: 'en',
    },
    parts: [],
    sections: [{ id: 'sec-1', label: 'Section 1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  };
}

describe('validateSchema conditional-reference checks (bd polyglot-pdf-y61i)', () => {
  it('does NOT flag a show_if that targets a field declared LATER (forward ref)', () => {
    // trigger appears AFTER the field that references it -- the incremental-set bug
    // falsely flagged this as "references non-existent field".
    const schema = schemaWith([
      field('dependent', { show_if: { field: 'trigger', operator: 'equals', value: 'yes' } }),
      field('trigger'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('show_if references non-existent field'))).toBe(false);
  });

  it('flags composite show_if and require_if atoms referencing non-existent fields (bd h76m.8)', () => {
    const schema = schemaWith([
      field('dependent', {
        show_if: { all_of: [{ field: 'ghost_a', operator: 'is_not_empty' }] },
        require_if: { field: 'ghost_b', operator: 'is_checked' },
      }),
      field('trigger'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('show_if references non-existent field: ghost_a'))).toBe(true);
    expect(errors.some(e => e.message.includes('require_if references non-existent field: ghost_b'))).toBe(true);
  });

  it('does NOT flag composite/require_if references that resolve (incl. forward refs)', () => {
    const schema = schemaWith([
      field('dependent', {
        show_if: { any_of: [{ field: 'trigger', operator: 'is_not_empty' }] },
        require_if: { none_of: [{ field: 'later', operator: 'is_checked' }] },
      }),
      field('trigger'),
      field('later'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('references non-existent field'))).toBe(false);
  });

  it('STILL flags a show_if that targets a field that does not exist anywhere', () => {
    const schema = schemaWith([
      field('dependent', { show_if: { field: 'ghost', operator: 'equals', value: 'yes' } }),
      field('trigger'),
    ]);

    const errors = validateSchema(schema);

    const warn = errors.find(e => e.message.includes('show_if references non-existent field'));
    expect(warn).toBeDefined();
    expect(warn?.message).toContain('ghost');
    expect(warn?.type).toBe('warning');
  });

  it('still detects a genuine duplicate field ID (incremental seen-set preserved)', () => {
    const schema = schemaWith([field('dup'), field('dup')]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message === 'Duplicate field ID' && e.field_id === 'dup')).toBe(true);
  });
});

describe("validateSchema 'To review' gate mirror (bd polyglot-pdf-6cfu.3)", () => {
  it("errors on a field still filed in a sec_to_review section", () => {
    const schema = {
      form_metadata: { title: 'T', version: '1' },
      sections: [
        { id: 'sec_real', label: 'Real', order: 1, fields: [] },
        { id: 'sec_to_review_p1', label: 'To review', order: 2, fields: ['f1'] },
      ],
      fields: [
        { id: 'f1', name: 'F1', type: 'text', section_id: 'sec_to_review_p1' },
      ],
    } as unknown as FormSchema;
    const errs = validateSchema(schema).filter(e =>
      e.message.includes("'To review'"));
    expect(errs).toHaveLength(1);
    expect(errs[0]).toMatchObject({ field_id: 'f1', type: 'error' });
  });

  it('stays quiet once the field is re-filed', () => {
    const schema = {
      form_metadata: { title: 'T', version: '1' },
      sections: [
        { id: 'sec_real', label: 'Real', order: 1, fields: ['f1'] },
        { id: 'sec_to_review_p1', label: 'To review', order: 2, fields: [] },
      ],
      fields: [
        { id: 'f1', name: 'F1', type: 'text', section_id: 'sec_real' },
      ],
    } as unknown as FormSchema;
    expect(validateSchema(schema).filter(e =>
      e.message.includes("'To review'"))).toHaveLength(0);
  });
});

// checkFieldComplete PDF-mapping + reasons (bd polyglot-pdf-0x10.6): a
// CONSOLIDATED choice field (per-option pdf_field_name, none at field level)
// is legitimately mapped -- the old blanket "Missing PDF field name" marked
// every merged group red with nothing actually wrong. And the status now
// carries plain-language reasons the UI can show.
describe('checkFieldComplete PDF mapping on consolidated groups (bd 0x10.6)', () => {
  const complete = { spoken_name: 'spoken', help: { instructions: 'Done.' } };

  it('accepts a consolidated group whose options each carry pdf_field_name', () => {
    const status = checkFieldComplete(field('gender', {
      ...complete,
      type: 'radio',
      pdf_field_name: undefined,
      options: [
        { value: 'male', label: 'Male', pdf_field_name: 'g[0]' },
        { value: 'female', label: 'Female', pdf_field_name: 'g[1]' },
      ],
    } as Partial<FormField>));
    expect(status.errors).toEqual([]);
    expect(status.isComplete).toBe(true);
  });

  it('names the specific unmapped options of a partially-mapped group', () => {
    const status = checkFieldComplete(field('race', {
      ...complete,
      type: 'checkbox_group',
      pdf_field_name: undefined,
      options: [
        { value: 'white', label: 'White', pdf_field_name: 'r[0]' },
        { value: 'black', label: 'Black' },
      ],
    } as Partial<FormField>));
    expect(status.errors).toEqual(['Options missing a PDF widget mapping: Black']);
  });

  it('flags a group with NO mapping anywhere (field or options)', () => {
    const status = checkFieldComplete(field('race', {
      ...complete,
      type: 'checkbox_group',
      pdf_field_name: undefined,
      options: [
        { value: 'white', label: 'White' },
        { value: 'black', label: 'Black' },
      ],
    } as Partial<FormField>));
    expect(status.errors).toEqual([
      'No PDF mapping: neither the field nor its options name a PDF widget',
    ]);
  });

  it('still requires pdf_field_name on a plain (non-group) field', () => {
    const status = checkFieldComplete(field('name', {
      ...complete,
      pdf_field_name: undefined,
    } as Partial<FormField>));
    expect(status.errors).toEqual(['Missing PDF field name']);
  });

  it('names the review reasons so the UI can say WHY a field is amber', () => {
    const status = checkFieldComplete(field('bare', {} as Partial<FormField>));
    expect(status.needsReview).toBe(true);
    expect(status.reviewReasons).toEqual([
      'Help instructions are missing or a placeholder',
      'Missing spoken name',
      // bd g63j: the helper's fields name a widget but carry no position, so
      // the un-highlightable reason is named too (it was silent before).
      'PDF widget "bare": No position recorded for this field, so it cannot be '
        + 'highlighted on the form preview',
    ]);
    const clean = checkFieldComplete(field('done', {
      ...complete, pdf_position: { page: 1, x: 10, y: 10, width: 50, height: 12 },
    } as Partial<FormField>));
    expect(clean.reviewReasons).toEqual([]);
    expect(clean.isComplete).toBe(true);
  });
});

describe('checkFieldComplete position diagnostics (bd g63j)', () => {
  const complete = { spoken_name: 'spoken', help: { instructions: 'Done.' } };
  const rect = { page: 1, x: 10, y: 10, width: 50, height: 12 };

  it('never says "Missing PDF field name" for a field that HAS one', () => {
    // The misleading message that made two correctly-named W-7 fields read as
    // phantoms. A named-but-unlocatable field is amber, never that error.
    const status = checkFieldComplete(field('named', complete as Partial<FormField>));
    expect(status.errors).toEqual([]);
    expect(status.reviewReasons.join(' ')).not.toContain('Missing PDF field name');
    expect(status.reviewReasons.join(' ')).toContain('named');
  });

  it('distinguishes a degenerate rect from an absent one', () => {
    const zero = checkFieldComplete(field('zero', {
      ...complete, pdf_position: { page: 1, x: 5, y: 5, width: 0, height: 12 },
    } as Partial<FormField>));
    expect(zero.reviewReasons.join(' ')).toContain('zero size');
  });

  it('flags a page the PDF does not have -- only when a page count is known', () => {
    const offDoc = field('off', {
      ...complete, pdf_position: { ...rect, page: 7 },
    } as Partial<FormField>);
    // With a page count: its own distinct wording, naming both numbers.
    const known = checkFieldComplete(offDoc, 3);
    expect(known.needsReview).toBe(true);
    expect(known.reviewReasons.join(' ')).toContain('claims page 7');
    expect(known.reviewReasons.join(' ')).toContain('3 page(s)');
    // Without one (schema-only context, no PDF loaded): silent, never an error.
    expect(checkFieldComplete(offDoc).reviewReasons).toEqual([]);
  });

  it('page 0 is out of range, not page one (1-based schema convention)', () => {
    const status = checkFieldComplete(field('zeroth', {
      ...complete, pdf_position: { ...rect, page: 0 },
    } as Partial<FormField>), 3);
    expect(status.reviewReasons.join(' ')).toContain('claims page 0');
  });

  it('a properly positioned field on a real page is clean', () => {
    const status = checkFieldComplete(field('good', {
      ...complete, pdf_position: rect,
    } as Partial<FormField>), 3);
    expect(status.reviewReasons).toEqual([]);
    expect(status.isComplete).toBe(true);
  });

  it('does not fire on a consolidated choice field (identity is per-option)', () => {
    // No field-level position AND no field-level name: its rects live on the
    // options, so there is nothing at this level to diagnose.
    const status = checkFieldComplete(field('grp', {
      ...complete,
      type: 'radio',
      pdf_field_name: undefined,
      options: [
        { value: 'a', label: 'A', pdf_field_name: 'a[0]' },
        { value: 'b', label: 'B', pdf_field_name: 'b[0]' },
      ],
    } as Partial<FormField>), 3);
    expect(status.reviewReasons).toEqual([]);
  });

  it('DOES fire on a choice field that carries its own bad position', () => {
    // Fresh-eyes catch: single-widget radios with a real field-level rect
    // exist in the shipped i-90, and PDFViewer draws overlays from
    // field.pdf_position for ANY field that has one -- so skipping the check
    // for choice types reproduced this bead's own target bug for that family.
    const status = checkFieldComplete(field('single_radio', {
      ...complete,
      type: 'radio',
      pdf_field_name: 'r[0]',
      pdf_position: { page: 99, x: 1, y: 1, width: 10, height: 10 },
      options: [
        { value: 'a', label: 'A' },
        { value: 'b', label: 'B' },
      ],
    } as Partial<FormField>), 3);
    expect(status.reviewReasons.join(' ')).toContain('claims page 99');
  });

  it('names the field id when a positioned choice field has no field-level name', () => {
    const status = checkFieldComplete(field('nameless_grp', {
      ...complete,
      type: 'checkbox_group',
      pdf_field_name: undefined,
      pdf_position: { page: 42, x: 1, y: 1, width: 10, height: 10 },
      options: [
        { value: 'a', label: 'A', pdf_field_name: 'a[0]' },
        { value: 'b', label: 'B', pdf_field_name: 'b[0]' },
      ],
    } as Partial<FormField>), 3);
    expect(status.reviewReasons.join(' ')).toContain('Field "nameless_grp"');
    expect(status.reviewReasons.join(' ')).toContain('claims page 42');
  });

  it('stays silent for a NAMED choice field with no field-level rect', () => {
    // A true shared-name AcroForm radio group: one name, rects per option.
    // PDFViewer never draws option rects, so flagging this would fire on every
    // real radio group rather than name a defect (fresh-eyes: pin the cell the
    // scoping comment now spells out).
    const status = checkFieldComplete(field('shared_radio', {
      ...complete,
      type: 'radio',
      pdf_field_name: 'g[0]',
      pdf_position: undefined,
      options: [
        { value: 'a', label: 'A', pdf_on_value: '1' },
        { value: 'b', label: 'B', pdf_on_value: '2' },
      ],
    } as Partial<FormField>), 3);
    expect(status.reviewReasons).toEqual([]);
  });

  it('flags a fractional page -- it can never match a rendered page', () => {
    const status = checkFieldComplete(field('fractional', {
      ...complete, pdf_position: { ...rect, page: 1.5 },
    } as Partial<FormField>), 3);
    expect(status.reviewReasons.join(' ')).toContain('claims page 1.5');
  });

  it('treats a page count of 0 as unknown (PDF still loading)', () => {
    // PDFViewer reports 0 while a document loads, including right after a kit
    // switch -- the new kit's fields must not be judged against the old kit's
    // count, so 0 means "skip the page-range half" (fresh-eyes).
    const offDoc = field('off', {
      ...complete, pdf_position: { ...rect, page: 7 },
    } as Partial<FormField>);
    expect(checkFieldComplete(offDoc, 0).reviewReasons).toEqual([]);
  });
});

// ============================================================================
// Malformed `options` must DEGRADE, never throw (bd polyglot-pdf-8bjdx)
// ============================================================================
//
// Two shapes a hand-edited or script-drifted kit can carry escape the ordinary
// `?? []` / `|| []` guards, because both are TRUTHY and both have a `.length`:
//   1. a NON-ARRAY value (e.g. "not-a-list") -- array methods throw
//      "is not a function";
//   2. an array with NULL / non-object entries -- `o.pdf_field_name` throws
//      "Cannot read properties of null".
//
// bd polyglot-pdf-93p8 fixed ONE member of this set (reviewStatus.ts's
// hasUncoveredStructuralError). This bead is the REMAINDER: checkFieldComplete
// and the render/edit paths that call it. A throw here is not a wrong number,
// it is a BLANK SCREEN -- checkFieldComplete sits on the per-field render path
// (FieldList rows + tooltips, FieldOverlay boxes, FieldEditor's panel), so one
// malformed field took down the whole list rather than degrading its own row.
describe('malformed options degrade instead of throwing (bd polyglot-pdf-8bjdx)', () => {
  const MALFORMED: Array<[string, unknown]> = [
    ['a non-array options value', 'not-a-list'],
    ['an array whose FIRST entry is null', [null, { label: 'ok', value: 'ok' }]],
    ['an array whose LAST entry is null', [{ label: 'ok', value: 'ok' }, null]],
    ['an array of non-object junk', ['junk', 42, null]],
    ['a numeric options value', 7],
    ['an object (non-array) options value', { label: 'x' }],
  ];

  // Every CHOICE type reaches the options branch in checkFieldComplete; a
  // non-choice type skips it. Both must survive.
  const TYPES = ['select', 'radio', 'checkbox_group', 'text'] as const;

  for (const [shapeName, options] of MALFORMED) {
    for (const type of TYPES) {
      it(`checkFieldComplete survives ${shapeName} on a ${type} field`, () => {
        // pdf_field_name MUST be cleared: the options branch is nested inside
        // `if (!field.pdf_field_name)`, so a field carrying a field-level
        // widget name short-circuits before the throwing .filter/.map and the
        // test would be vacuous (measured -- an earlier cut of this test kept
        // the fixture's default pdf_field_name and passed against the
        // UNFIXED code).
        const f = field('malformed', {
          type, options, pdf_field_name: undefined,
        } as unknown as Partial<FormField>);
        // The assertion is "does not throw" -- the exact status is a
        // degradation detail, but it must be a real FieldStatus.
        const status = checkFieldComplete(f);
        expect(status).toBeDefined();
        expect(Array.isArray(status.errors)).toBe(true);
        expect(Array.isArray(status.reviewReasons)).toBe(true);
      });
    }
  }

  it('a WELL-FORMED choice field still reports its unmapped options (no regression)', () => {
    // The degradation must not blunt the real check: a genuine partially-mapped
    // choice field still names which options lack a widget.
    const f = field('partly', {
      type: 'radio',
      pdf_field_name: undefined,
      options: [
        { label: 'Mapped', value: 'a', pdf_field_name: 'A[0]' },
        { label: 'Unmapped', value: 'b' },
      ],
    } as unknown as Partial<FormField>);
    const status = checkFieldComplete(f);
    expect(status.errors.join(' ')).toContain('Unmapped');
  });

  it('a choice field with NO mapped option anywhere still reports the hard error', () => {
    const f = field('none', {
      type: 'select',
      pdf_field_name: undefined,
      options: [{ label: 'A', value: 'a' }, { label: 'B', value: 'b' }],
    } as unknown as Partial<FormField>);
    const status = checkFieldComplete(f);
    expect(status.errors.join(' ')).toContain('No PDF mapping');
  });
});

// ============================================================================
// The two index spaces must not diverge (bd polyglot-pdf-8bjdx, fresh-eyes r1)
// ============================================================================
//
// safeOptions DROPS malformed entries; safeOptionsPreservingArity KEEPS them as
// null placeholders. Mixing the two over one field inside a single component is
// a silent correctness bug, not a crash: FieldEditor built its lint-finding
// anchor map from the arity-preserving list (raw indices) while rendering rows
// from the dropping list (compacted indices), so with options=[null, a, b] a
// finding anchored to option 'a' (raw index 1) was looked up at 'b's row.
//
// These pin the PROPERTY that makes the two interchangeable-looking helpers
// actually different, so the next person choosing between them sees it stated.
describe('safeOptions vs safeOptionsPreservingArity index spaces', () => {
  const field = {
    options: [null, { label: 'A', value: 'a' }, { label: 'B', value: 'b' }],
  };

  it('preserving keeps RAW indices; dropping COMPACTS them', () => {
    const preserving = safeOptionsPreservingArity(field);
    const dropping = safeOptions(field);

    expect(preserving.length).toBe(3);
    expect(preserving[0]).toBeNull();
    expect(preserving[1]?.value).toBe('a');

    expect(dropping.length).toBe(2);
    expect(dropping[0].value).toBe('a');   // 'a' moved from index 1 -> 0

    // The divergence, stated as an assertion: the SAME option has different
    // indices in the two views. Anything that indexes one must not be read
    // with an index derived from the other.
    expect(preserving.findIndex(o => o?.value === 'a'))
      .not.toBe(dropping.findIndex(o => o.value === 'a'));
  });

  it('both agree exactly when every entry is well-formed', () => {
    const clean = { options: [{ label: 'A', value: 'a' }, { label: 'B', value: 'b' }] };
    expect(safeOptions(clean)).toEqual(safeOptionsPreservingArity(clean));
  });

  it('an option index is only meaningful in ONE space -- raw', () => {
    // The cross-component contract (fresh-eyes round 2). FieldList hands an
    // option's row index to onMoveOption; App.tsx then indexes `options` with
    // it. Both must use the SAME space, and it must be RAW, because App.tsx
    // writes back a rebuilt options array.
    //
    // The round-1 fix moved App.tsx to arity-preserving while FieldList still
    // rendered from the dropping view -- which RELOCATED the bug instead of
    // fixing it: with [null, a, b], dragging 'a' (dropped idx 0) selected
    // preserving[0] === null (silent no-op), and dragging 'b' (dropped idx 1)
    // selected preserving[1] === 'a', moving the WRONG option.
    const preserving = safeOptionsPreservingArity(field);
    const dropping = safeOptions(field);

    // What the buggy pairing did, stated so it cannot silently come back:
    expect(preserving[dropping.findIndex(o => o.value === 'b')]?.value)
      .toBe('a');            // dropped-space idx read in raw space -> WRONG option
    expect(preserving[dropping.findIndex(o => o.value === 'a')])
      .toBeNull();           // ...or nothing at all

    // The contract: a raw index round-trips to the same option.
    const rawIdxOfA = preserving.findIndex(o => o?.value === 'a');
    expect(preserving[rawIdxOfA]?.value).toBe('a');
  });

  it('a real-option COUNT must come from safeOptions, not the raw length', () => {
    // FieldEditor's atFloor guard ("a choice field needs >= 2 real options")
    // read field.options.length, which counts the malformed entry: 3 > 2, so
    // Remove stayed enabled and one click produced a single-option choice
    // field the v2 backend rejects.
    expect(field.options.length).toBe(3);        // the misleading raw count
    expect(safeOptions(field).length).toBe(2);   // the count the guard needs
  });
});
