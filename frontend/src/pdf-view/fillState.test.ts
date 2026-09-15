import { describe, it, expect } from 'vitest';
import { fillStateFor } from './PDFViewer';

const wrap = (value: unknown, confirmed = false) => ({ value, confirmed });

describe('fillStateFor', () => {
  it('treats empty-ish raw values as empty', () => {
    expect(fillStateFor('f', wrap(null), null)).toBe('empty');
    expect(fillStateFor('f', wrap(''), '')).toBe('empty');
    expect(fillStateFor('f', wrap(false), false)).toBe('empty');
    expect(fillStateFor('f', undefined, undefined)).toBe('empty');
  });

  it('treats a cleared checkbox_group selection ([]) as empty', () => {
    expect(fillStateFor('f', wrap([]), [])).toBe('empty');
    expect(fillStateFor('f', wrap([], true), [])).toBe('empty');
  });

  it('distinguishes filled from confirmed', () => {
    expect(fillStateFor('f', wrap('x'), 'x')).toBe('filled');
    expect(fillStateFor('f', wrap('x', true), 'x')).toBe('confirmed');
    expect(fillStateFor('f', wrap(['a'], true), ['a'])).toBe('confirmed');
  });

  it('current wins over every other state', () => {
    expect(fillStateFor('f', wrap('x', true), 'x', 'f')).toBe('current');
    expect(fillStateFor('f', wrap(null), null, 'f')).toBe('current');
    expect(fillStateFor('f', wrap('x'), 'x', 'other')).toBe('filled');
  });

  // --- skipped (bd polyglot-pdf-c9dfo) ------------------------------------
  //
  // markFieldSkipped stores {value: null, skipped: true, confirmed: true}. The
  // empty check fires on that null, so before this branch existed a deliberate
  // skip painted as 'empty' -- identical to a field the user never touched,
  // which schemaFormState.ts's docstring says must never happen ("NOT a silent
  // blank"). The form view had always shown a Skipped badge; the PDF surface
  // silently had not.
  describe('a skipped field is not a blank one', () => {
    it('reports skipped even though the stored value is null', () => {
      expect(fillStateFor('f', { value: null, skipped: true, confirmed: true }, null))
        .toBe('skipped');
    });

    it('reports skipped for the other empty-ish shapes a skip can leave behind', () => {
      // markFieldSkipped writes null today, but the skipped FLAG is the
      // contract -- not the particular emptiness it pairs with. Pinning the
      // whole set means a future change to what a skip stores cannot silently
      // reopen this.
      for (const value of [null, undefined, '', false, []]) {
        expect(
          fillStateFor('f', { value, skipped: true, confirmed: true }, value),
          `a skipped field holding ${JSON.stringify(value)} must not read as blank`,
        ).toBe('skipped');
      }
    });

    it('does NOT report skipped for an ordinary empty field', () => {
      // The other half: the state must stay rare enough to mean something. An
      // untouched field, and a merely-confirmed-empty optional one, are blank.
      expect(fillStateFor('f', wrap(null), null)).toBe('empty');
      expect(fillStateFor('f', { value: '', confirmed: true }, '')).toBe('empty');
      expect(fillStateFor('f', { value: null, skipped: false }, null)).toBe('empty');
    });

    it('the skipped FLAG outranks a stored value, and that is unreachable today', () => {
      // NAME MATCHES THE ASSERTION. The first version of this test was called
      // "still paints a skipped field that HOLDS a value by its value" and its
      // comment argued the value should win -- while asserting the exact
      // opposite. A reader would have trusted the prose and "fixed"
      // fillStateFor to match a rule it never implemented (found by
      // fresh-eyes).
      //
      // What actually holds: the flag wins. That combination cannot arise in
      // the app -- schemaFormState.ts's updateField DROPS `skipped` on a fresh
      // write, so answering a skipped field clears the flag and the field
      // paints by its value through the ordinary path. This pins the
      // precedence for the synthetic shape rather than claiming a behaviour
      // the app can reach.
      expect(fillStateFor('f', { value: 'x', skipped: true }, 'x')).toBe('skipped');
    });

    it('current still wins over skipped', () => {
      // The field the assistant is asking about right now outranks the fact it
      // was skipped earlier -- switch_to_field can re-pin a skipped field.
      expect(
        fillStateFor('f', { value: null, skipped: true, confirmed: true }, null, 'f'),
      ).toBe('current');
    });

    it('tolerates a non-object entry without claiming skipped', () => {
      // fillStateFor is called with whatever readFieldEntryWithAlias returns,
      // including a bare value for legacy/unwrapped entries.
      expect(fillStateFor('f', 'x', 'x')).toBe('filled');
      expect(fillStateFor('f', null, null)).toBe('empty');
    });
  });
});
