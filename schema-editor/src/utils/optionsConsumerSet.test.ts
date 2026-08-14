import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, basename } from 'node:path';

// ============================================================================
// The COMPLETE set of `field.options` consumers must stay guarded
// (bd polyglot-pdf-8bjdx, exit criterion 3)
// ============================================================================
//
// This repo's single largest source of review rounds is fixing ONE instance of
// a pattern and leaving its siblings (CLAUDE.md scar #7). That is literally
// this bead's own history: bd polyglot-pdf-93p8 guarded reviewStatus.ts's
// hasUncoveredStructuralError and left checkFieldComplete + the whole render
// chain throwing on the identical inputs.
//
// So this test pins the SET, not the instances. It derives the list of
// `field.options` reads from the SOURCE and fails when a new one appears that
// is not provably safe -- rather than trusting a hand-maintained list that
// silently goes stale.
//
// WHY A SOURCE SCAN AND NOT A BEHAVIORAL TEST: the unsafe shapes only reach
// these sites from malformed kit DATA, and most consumers are deep inside
// React render trees that would each need a full component harness. A source
// scan catches the omission at the moment it is written, which is the point.

const SRC = join(__dirname, '..');

// Line split that tolerates CRLF -- this repo is developed on Windows, and a
// trailing \r would otherwise ride along on every matched line and break
// fragment comparisons.
function splitLines(text: string): string[] {
  return text.split('\n').map(l => l.replace(/\r$/, ''));
}

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) {
      if (entry === 'node_modules' || entry === '__fixtures__') continue;
      out.push(...walk(p));
    } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      out.push(p);
    }
  }
  return out;
}

// An array METHOD call on options is the dangerous shape: it throws on a
// non-array value AND (via the callback's property read) on a null entry.
// A bare `.length` / truthiness check is safe -- verified in node:
//   ('not-a-list').length === 10, and (['a',null]).length === 2, neither throws.
//
// Matches ANY receiver, not just the literal `field` (fresh-eyes round 1): the
// first cut anchored on `field.options` and was evaded three ways --
// `trigger.options.map(...)` (a FormField under another name, which is how
// ConditionBuilder.tsx escaped the net), `const o = field.options; o.map(...)`,
// and `const {options} = field; options.map(...)`. Widening the receiver costs
// some false positives on unrelated `.options` bags; those go in
// SAFE_EXEMPTIONS with a reason, which is the trade this test wants -- a
// missed consumer is silent, an over-match is loud.
const ITERATION =
  /(?:\b\w+\.)?\boptions\b\s*(?:\?\?|\|\|)?\s*(?:\[\])?\s*\)?\s*\??\.\s*(map|filter|every|some|forEach|reduce|flatMap|sort|find)\b/;

// Reads that are provably safe, each with the reason it is exempt.
//
// An exemption must match EXACTLY ONE line in its file (enforced by the second
// test below). The first cut only required >= 1 match, which meant a NEW unsafe
// call that happened to share the fragment text -- `.map((opt, idx) => ...)` is
// a common idiom -- would silently inherit an exemption written for a different
// call's reachability argument (fresh-eyes round 1).
const SAFE_EXEMPTIONS: Array<{
  file: string; fragment: string; why: string; occurrences?: number;
}> = [
  {
    file: 'fieldGrouping.ts',
    fragment: 'field.options.map((opt, idx)',
    why: 'ungroupField -- gated by canUngroup(), which returns false for any '
       + 'malformed options (it compares safeOptions() length against the raw '
       + 'array length). Unreachable with a bad shape.',
  },
  // The widened receiver pattern (any `<x>.options.<method>`) also matches
  // LOCALS that were already normalized on the line above. Each of these is a
  // `const options = <normalizer>(field)` binding, verified by reading the
  // assignment -- the iteration is on the SAFE list, not on field.options.
  {
    file: 'validation.ts',
    fragment: 'const unmapped = options.filter(o => !o?.pdf_field_name);',
    why: 'checkFieldComplete -- `options` is safeOptionsPreservingArity(field) '
       + 'assigned a few lines above; the ?. also covers the null slots it '
       + 'deliberately preserves.',
  },
  {
    file: 'reviewStatus.ts',
    fragment: "return options.some(o => !(o && typeof o === 'object'",
    why: 'hasUncoveredStructuralError (bd polyglot-pdf-93p8) -- `options` is '
       + 'an Array.isArray-guarded local, and the callback type-checks each '
       + 'entry inline.',
  },
  {
    file: 'PreviewPane.tsx',
    fragment: 'options.map(opt => (',
    why: 'PreviewInput -- `options` is safeOptions(field), assigned once at the '
       + 'top of the function and reused by the radio/checkbox/select renders.',
    occurrences: 3,
  },
  {
    file: 'ConditionBuilder.tsx',
    fragment: 'current.filter((v: unknown) => options.some(o => o.value === v))',
    why: 'coerceAtom -- `options` is safeOptions(trigger!) assigned above, '
       + 'gated by isChoiceTrigger (bd polyglot-pdf-yb41u).',
  },
  {
    file: 'ConditionBuilder.tsx',
    fragment: 'next.value = options.some(o => o.value === atom.value)',
    why: 'coerceAtom -- same safeOptions(trigger!) local as the entry above.',
  },
];

describe('every field.options consumer is guarded (bd polyglot-pdf-8bjdx)', () => {
  it('no source file iterates field.options without safeOptions', () => {
    const offenders: string[] = [];

    for (const file of walk(SRC)) {
      const lines = readFileSync(file, 'utf8').split('\n');
      lines.forEach((line, i) => {
        const code = line.trim();
        // Skip comments -- this bead's own fix comments quote the bad pattern.
        if (code.startsWith('//') || code.startsWith('*') || code.startsWith('/*')) return;
        if (!ITERATION.test(line)) return;

        const base = basename(file);
        const exempt = SAFE_EXEMPTIONS.find(
          e => e.file === base && line.includes(e.fragment),
        );
        if (exempt) return;

        offenders.push(`${base}:${i + 1}  ${code}`);
      });
    }

    expect(
      offenders,
      'These sites iterate field.options directly. A non-array options value, '
      + 'or an array carrying null/non-object entries, throws here and blanks '
      + 'the render tree. Route the read through safeOptions() / '
      + 'safeOptionsPreservingArity() from utils/validation, or add a '
      + 'documented entry to SAFE_EXEMPTIONS explaining why it cannot be '
      + 'reached with a malformed shape.\n',
    ).toEqual([]);
  });

  it('every exemption matches its file EXACTLY the expected number of times', () => {
    // Two failure modes, both silent without this check:
    //   STALE   -- the code moved/changed, so the exemption whitelists nothing
    //              real but still sits in the list looking meaningful;
    //   WIDENED -- a NEW call appeared sharing the fragment text, inheriting an
    //              exemption written for a different call's reachability
    //              argument. Pinning the COUNT catches that; `>= 1` did not.
    for (const e of SAFE_EXEMPTIONS) {
      const expected = e.occurrences ?? 1;
      let found = 0;
      for (const f of walk(SRC)) {
        if (basename(f) !== e.file) continue;
        for (const line of splitLines(readFileSync(f, 'utf8'))) {
          if (line.includes(e.fragment)) found += 1;
        }
      }
      expect(
        found,
        `exemption for ${e.file} "${e.fragment}" matched ${found} line(s), `
        + `expected exactly ${expected}. If a NEW call added that text, it does `
        + `NOT inherit this exemption -- guard it, or give it its own entry `
        + `with its own reason. If the code moved, update or remove the entry.`,
      ).toBe(expected);
    }
  });
});
