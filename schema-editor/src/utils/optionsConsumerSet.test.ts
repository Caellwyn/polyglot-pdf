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
const ITERATION = /field\.options\s*(?:\?\?|\|\|)?\s*(?:\[\])?\s*\)?\s*\.\s*(map|filter|every|some|forEach|reduce|flatMap|sort|find)\b/;

// Reads that are provably safe, each with the reason it is exempt. Keyed by
// `basename:line-content-fragment` so a MOVE does not silently re-exempt a
// DIFFERENT read.
const SAFE_EXEMPTIONS: Array<{ file: string; fragment: string; why: string }> = [
  {
    file: 'fieldGrouping.ts',
    fragment: 'field.options.map((opt, idx)',
    why: 'ungroupField -- gated by canUngroup(), which returns false for any '
       + 'malformed options (it compares safeOptions() length against the raw '
       + 'array length). Unreachable with a bad shape.',
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

  it('the exemption list itself is live -- each entry still matches real code', () => {
    // A stale exemption is worse than none: it silently whitelists whatever
    // moves into that filename+fragment later.
    for (const e of SAFE_EXEMPTIONS) {
      const hits = walk(SRC).filter(f => {
        if (basename(f) !== e.file) return false;
        return readFileSync(f, 'utf8').includes(e.fragment);
      });
      expect(hits.length, `stale exemption: ${e.file} no longer contains "${e.fragment}"`)
        .toBeGreaterThan(0);
    }
  });
});
