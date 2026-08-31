import { describe, it, expect } from 'vitest';
import { kitName, kitTitle } from './kitName';

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
});

describe('kitTitle -- naming a kit in a heading', () => {
  it('uses the label alone, with no id', () => {
    expect(kitTitle({ id: 'form-2', label: 'W-7' })).toBe('W-7');
  });

  it('falls back to the id when there is no label', () => {
    expect(kitTitle({ id: 'form-2' })).toBe('form-2');
    expect(kitTitle({ id: 'form-2', label: '  ' })).toBe('form-2');
  });
});
