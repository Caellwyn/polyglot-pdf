import { describe, it, expect } from 'vitest';
import { kitName, kitOptionName } from './kitName';

/**
 * These cases are the SHARED CONTRACT with the backend's `_kit_name`.
 * The same rows appear as _PARITY_CASES in
 * backend/tests/unit/test_kit_refusals_name_the_label.py. The two formatters
 * cannot share code across the language boundary, so they share this table:
 * change the rule on one side without the other and that side goes red.
 */

describe('kitName -- naming a kit in prose (bd polyglot-pdf-kztlr)', () => {
  it('names a human-labelled kit by BOTH label and id', () => {
    // The maintainer's actual case: a card reading "W-7" whose id is `form-2`.
    // A refusal saying only "form-2" could not be matched to that card.
    expect(kitName({ id: 'form-2', label: 'W-7' })).toBe('"W-7" (form-2)');
  });

  it('omits a label that merely restates the id', () => {
    // Both catalogues synthesise "Form 2" from `form-2` when metadata carries
    // no label. Rendering '"Form 2" (form-2)' shows one fact twice.
    expect(kitName({ id: 'form-2', label: 'Form 2' })).toBe('"form-2"');
    expect(kitName({ id: 'i-90', label: 'I 90' })).toBe('"i-90"');
    expect(kitName({ id: 'w7', label: 'W7' })).toBe('"w7"');
  });

  it('keeps a label that only LOOKS like the id but adds words', () => {
    // The real w7 kit: the label carries the form's purpose, so it is not a
    // restatement even though it starts with the id.
    expect(kitName({ id: 'w7', label: 'W-7 (ITIN Application)' }))
      .toBe('"W-7 (ITIN Application)" (w7)');
  });

  it('falls back to the id when the label is missing or blank', () => {
    expect(kitName({ id: 'form-2' })).toBe('"form-2"');
    expect(kitName({ id: 'form-2', label: null })).toBe('"form-2"');
    expect(kitName({ id: 'form-2', label: '   ' })).toBe('"form-2"');
  });

  it('is case- and separator-insensitive when judging a restatement', () => {
    expect(kitName({ id: 'my_form', label: 'My Form' })).toBe('"my_form"');
    expect(kitName({ id: 'MY-FORM', label: 'my form' })).toBe('"MY-FORM"');
  });

  /**
   * NON-ASCII rows (bd polyglot-pdf-th60w). The shared table was all-ASCII, so
   * it could not see that `\s` and `.trim()`/`.strip()` mean DIFFERENT things
   * in the two languages. Measured across the whole code space on both
   * runtimes, they disagree on SIX characters in BOTH directions:
   *
   *   Python strips, JS does not:  U+001C U+001D U+001E U+001F U+0085
   *   JS strips, Python does not:  U+FEFF
   *
   * Every ASCII row passed throughout. These are the rows that would not have.
   */
  it('agrees with the backend on characters the two languages dispute', () => {
    // U+FEFF -- JS whitespace, Python's is not. An ordinary paste artifact
    // from a spreadsheet or a UTF-8-BOM file; the backend's _safe_label lets
    // it through (it rejects only quotes, backslashes and ord < 32).
    expect(kitName({ id: 'form-2', label: 'Form\ufeff2' })).toBe('"form-2"');
    expect(kitName({ id: 'form-2', label: '\ufeffW-7' })).toBe('"W-7" (form-2)');
    expect(kitName({ id: 'form-2', label: 'W-7\ufeff' })).toBe('"W-7" (form-2)');

    // U+0085 (NEL) -- the MIRROR case, and the one the bead reported as
    // agreeing. Python's whitespace, JavaScript's is not, so the shared class
    // is what makes this row hold here.
    expect(kitName({ id: 'form-2', label: 'Form\u00852' })).toBe('"form-2"');
    expect(kitName({ id: 'form-2', label: '\u0085W-7' })).toBe('"W-7" (form-2)');
  });

  it('leaves alone characters NEITHER language treats as space', () => {
    // The class must not quietly grow past what it claims. U+200B is the trap:
    // it LOOKS like whitespace and is not, on either side.
    expect(kitName({ id: 'form-2', label: 'Form\u200b2' }))
      .toBe('"Form\u200b2" (form-2)');
    expect(kitName({ id: 'form-2', label: 'Form\u2013 2' }))
      .toBe('"Form\u2013 2" (form-2)');
  });

  it('treats characters BOTH languages strip like a plain space', () => {
    expect(kitName({ id: 'form-2', label: 'Form\u00a02' })).toBe('"form-2"');
    expect(kitName({ id: 'form-2', label: 'Form\u30002' })).toBe('"form-2"');
  });
});

describe('kitOptionName -- naming a kit inside a control (bd polyglot-pdf-5ivqx)',
  () => {
    it('lets a human tell apart two kits that share a label', () => {
      // THE BUG. Nothing enforces label uniqueness, so two kits can both read
      // "W-7" in the catalogue-switcher dropdown. value={k.id} disambiguates
      // what the select SUBMITS, but not what the human reads before choosing
      // -- and choosing the wrong form is how you edit the wrong form.
      const a = { id: 'form-2', label: 'W-7' };
      const b = { id: 'form-9', label: 'W-7' };
      expect(kitOptionName(a)).not.toBe(kitOptionName(b));
      expect(kitOptionName(a)).toBe('W-7 (form-2)');
      expect(kitOptionName(b)).toBe('W-7 (form-9)');
    });

    it('does NOT quote, unlike the prose form', () => {
      // An <option> is not a sentence, and the strip appends "-- draft, 42%"
      // right after this, so quotes would read as part of the label itself.
      expect(kitOptionName({ id: 'form-2', label: 'W-7' })).toBe('W-7 (form-2)');
      expect(kitName({ id: 'form-2', label: 'W-7' })).toBe('"W-7" (form-2)');
    });

    it('drops the id when the label merely restates it', () => {
      // Shares labelRestatesId with kitName: whenever kitName judges a label
      // to be noise, this suppresses the parenthesised id too, so the dropdown
      // and the messages about it agree on what a kit is called.
      for (const kit of [
        { id: 'form-2', label: 'Form 2' },   // synthesised from the id
        { id: 'w7', label: 'W7' },
        { id: 'my_form', label: 'My Form' }, // separator- and case-insensitive
      ]) {
        expect(kitOptionName(kit)).not.toContain('(');
        // kitName agrees the label adds nothing -- it falls back to the id.
        expect(kitName(kit)).toBe(`"${kit.id}"`);
      }
    });

    it('KEEPS the label the human typed, rather than the folder name', () => {
      // Where it deliberately differs from kitName. A kit labelled "I-90" in a
      // folder called `i-90` is a restatement, so no id is appended -- but the
      // option must still read "I-90", not the lowercase folder name. Both are
      // the same string bar spelling, so neither disambiguates better and only
      // one is what the human wrote. Returning kit.id here reddens a shipped
      // strip test, which is how this was caught.
      expect(kitOptionName({ id: 'i-90', label: 'I-90' })).toBe('I-90');
      expect(kitOptionName({ id: 'my_form', label: 'My Form' })).toBe('My Form');
      // Prose still quotes the identifier, and that stays correct there.
      expect(kitName({ id: 'i-90', label: 'I-90' })).toBe('"i-90"');
    });

    it('falls back to the id only when there is no label at all', () => {
      expect(kitOptionName({ id: 'form-2' })).toBe('form-2');
      expect(kitOptionName({ id: 'form-2', label: null })).toBe('form-2');
      expect(kitOptionName({ id: 'form-2', label: '   ' })).toBe('form-2');
    });

    it('keeps a label that adds words to the id', () => {
      expect(kitOptionName({ id: 'w7', label: 'W-7 (ITIN Application)' }))
        .toBe('W-7 (ITIN Application) (w7)');
    });
  });
