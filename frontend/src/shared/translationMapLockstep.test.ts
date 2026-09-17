/**
 * ONE lockstep guard over EVERY user-facing language-keyed translation map.
 *
 * bd polyglot-pdf-cnwz. `SPOKEN_LANGUAGES` (shared/languages.ts) is where a
 * language actually gets added, and the repo is heading for ~90 of them. Every
 * map below must therefore be keyed by exactly that set, or the user picks a
 * language and silently gets English for that surface.
 *
 * WHY A SHARED TEST RATHER THAN A PER-MAP ONE. The bead reports the gap on
 * DISCLAIMER_TRANSLATIONS, but enumerating the set (CLAUDE.md scar #8) found
 * FOUR unanchored maps, not one: OVERLAY, BUTTON, DISCLAIMER and RESUME. Only
 * CONNECTION_TIMEOUT and VERIFY_FIELD had a genuine `SPOKEN_LANGUAGES` anchor.
 * Fixing them one test at a time would leave the NEXT map -- and new maps get
 * added -- to be caught by a reviewer one round at a time. So this file asserts
 * over a list that a companion test proves is COMPLETE: a newly added
 * language-keyed map fails the completeness check below until it is either
 * covered here or explicitly excluded with a reason.
 *
 * THE LIMIT OF THAT GUARANTEE, stated honestly. The completeness scan matches
 * EXPORT NAMES (`*_TRANSLATIONS`, plus the `*_COPY` / `*_STRINGS` / `*_LABELS`
 * shapes a future map might plausibly use), so it enumerates over a NAMING
 * CONVENTION -- not over the underlying hazard, "any object keyed by language
 * name". A map exported under a name matching none of those suffixes would
 * still slip through. Detecting the hazard structurally is not practical from a
 * regex (a `Record<string, T>` is indistinguishable from any other dictionary
 * at the source level), so the convention IS the guarantee: keep naming
 * language-keyed maps with one of these suffixes.
 *
 * THE TRAP THIS REPLACES. DisclaimerModal.test.tsx derived its audited set from
 * the map under test, and bound it to a local named `SPOKEN_LANGUAGES` --
 * shadowing the real export. Every assertion in that file was therefore
 * self-referential: a language missing from the map was simply never audited,
 * and CI stayed green while that user saw English.
 *
 * ASCII-only source (scar #6): nothing here types a non-Latin glyph -- the maps
 * are compared by KEY, and keys are English language names.
 */
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'fs';
import { join, relative } from 'path';
import { SPOKEN_LANGUAGES } from './languages';

import { OVERLAY_TRANSLATIONS } from '../demo/overlayTranslations';
import { CONNECTION_TIMEOUT_TRANSLATIONS } from '../schema-forms/components/connectionTimeoutTranslations';
import {
  BUTTON_TRANSLATIONS,
  DISCLAIMER_TRANSLATIONS,
} from '../schema-forms/components/DisclaimerModal';
import { VERIFY_FIELD_TRANSLATIONS } from '../schema-forms/components/verifyFieldTranslations';
import { RESUME_TRANSLATIONS } from '../schema-forms/resumeStrings';

// Widened to string[]: SPOKEN_LANGUAGES' `name` carries a literal-union type,
// and comparing it against keys read off a map (plain strings) needs the wider
// one on both sides.
const EXPECTED: string[] = SPOKEN_LANGUAGES.map((l) => l.name as string).sort();

// A separator no file path contains, so a path with a space cannot
// split into a bogus (name, file) pair.
const SEP = "|::|";

// Export-name shapes a language-keyed map may plausibly carry. Built fresh per
// call: a /g regex carries `lastIndex` across uses, so sharing one instance
// between the two scans below would make the second silently skip matches.
const MAP_EXPORT_RE = () =>
  /export\s+const\s+([A-Z0-9_]*_(?:TRANSLATIONS|COPY|STRINGS|LABELS))\b/g;

const MAPS: Record<string, Record<string, unknown>> = {
  OVERLAY_TRANSLATIONS,
  CONNECTION_TIMEOUT_TRANSLATIONS,
  BUTTON_TRANSLATIONS,
  DISCLAIMER_TRANSLATIONS,
  VERIFY_FIELD_TRANSLATIONS,
  RESUME_TRANSLATIONS,
};

describe('every translation map is keyed by exactly SPOKEN_LANGUAGES', () => {
  it.each(Object.keys(MAPS))('%s covers exactly the SPOKEN_LANGUAGES names', (name) => {
    const actual = Object.keys(MAPS[name]).sort();
    const missing = EXPECTED.filter((l) => !actual.includes(l));
    const extra = actual.filter((l) => !EXPECTED.includes(l));

    expect(
      { missing, extra },
      `${name} is out of lockstep with SPOKEN_LANGUAGES. A language in ` +
        `SPOKEN_LANGUAGES but missing here renders ENGLISH for that user; an ` +
        `extra key is dead copy that no language selector can reach.`
    ).toEqual({ missing: [], extra: [] });
  });

  it.each(Object.keys(MAPS))('%s has no blank entry for any language', (name) => {
    // A present-but-empty entry passes the key check while still rendering
    // nothing (or falling back to English), so key parity alone is not enough.
    const blanks: string[] = [];
    for (const [lang, copy] of Object.entries(MAPS[name])) {
      const values =
        copy && typeof copy === 'object'
          ? Object.values(copy as Record<string, unknown>)
          : [copy];
      const hasBlank = values.some(
        (v) => typeof v === 'string' && v.trim() === ''
      );
      if (hasBlank || values.length === 0) blanks.push(lang);
    }
    expect(blanks, `${name} has blank copy for: ${blanks.join(', ')}`).toEqual([]);
  });
});

/**
 * THE SET IS COMPLETE (scar #8).
 *
 * Without this, MAPS above is a hand-typed list and the seventh map ships
 * unguarded exactly as the first six did.
 */
describe('the guarded set covers every translation map in the frontend', () => {
  // Maps that are deliberately NOT language-keyed, with the reason.
  const EXCLUDED: Record<string, string> = {};

  it('every exported language-map export is guarded above or explicitly excluded', () => {
    const srcRoot = join(__dirname, '..');
    const found: string[] = [];

    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir)) {
        if (entry === 'node_modules' || entry === 'dist') continue;
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue;
        const text = readFileSync(full, 'utf-8');
        for (const m of text.matchAll(
          MAP_EXPORT_RE()
        )) {
          found.push(`${m[1]}${SEP}${relative(srcRoot, full)}`);
        }
      }
    };
    walk(srcRoot);

    const unguarded = found
      .map((f) => f.split(SEP))
      .filter(([name]) => !(name in MAPS) && !(name in EXCLUDED))
      .map(([name, file]) => `${name} (${file})`);

    expect(
      unguarded.sort(),
      'A language-keyed translation map is not covered by the lockstep guard ' +
        'above. Import it into MAPS, or add it to EXCLUDED with the reason it ' +
        'is not language-keyed (bd polyglot-pdf-cnwz).'
    ).toEqual([]);
  });

  it('every guarded map name was actually found in source (no stale entry)', () => {
    // A renamed or deleted map must leave MAPS, or the guard quietly shrinks
    // while still reporting a full green row per remaining entry.
    const srcRoot = join(__dirname, '..');
    const names: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir)) {
        if (entry === 'node_modules' || entry === 'dist') continue;
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue;
        for (const m of readFileSync(full, 'utf-8').matchAll(
          MAP_EXPORT_RE()
        )) {
          names.push(m[1]);
        }
      }
    };
    walk(srcRoot);
    for (const guarded of Object.keys(MAPS)) {
      expect(names, `stale MAPS entry: ${guarded}`).toContain(guarded);
    }
  });
});
