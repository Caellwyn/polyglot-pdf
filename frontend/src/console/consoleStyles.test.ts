// Every class a console page emits must be defined, and the stylesheet must
// be reachable from the page (bd polyglot-pdf-41ay8).
//
// The bug this pins: MintLinkPage shipped emitting `mint-page`,
// `mint-result` and `mint-note` with NO stylesheet defining any of them, so
// /console/links rendered as a bare browser form. Nothing failed -- the page
// worked, it just looked unfinished, which no behavioral test can see.
//
// DERIVED FROM ALL FILES, never a typed list. A hand-written list of page
// names is the same bug one level up: it goes stale the moment someone adds
// a page, which is exactly what happened here -- this test named only
// MintLinkPage.tsx until LinkHistoryPage.tsx shipped a second consumer of
// console.css with no guard covering it (x22hm cross-surface review finding
// 2). Glob src/console/*.tsx instead of hand-listing so the NEXT page is
// covered the moment it exists, with no edit to this file required.
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(process.cwd(), 'src/console');
const CSS = readFileSync(resolve(ROOT, 'styles/console.css'), 'utf-8');

/** Every page component in src/console/ -- every top-level *.tsx that is not
 * itself a test file. Test files (*.test.tsx) never emit production
 * className markup and would only add noise (or false failures) here. */
function consolePageFiles(): string[] {
  return readdirSync(ROOT)
    .filter((name) => name.endsWith('.tsx') && !name.endsWith('.test.tsx'))
    .sort();
}

/** Class names a PAGE actually emits, from its className attributes. */
function emittedClasses(source: string): string[] {
  const found = new Set<string>();
  for (const match of source.matchAll(/className="([^"]+)"/g)) {
    for (const name of match[1].split(/\s+/)) {
      if (name) found.add(name);
    }
  }
  return [...found].sort();
}

/** Class names the STYLESHEET defines, from its selectors. */
function definedClasses(css: string): Set<string> {
  const found = new Set<string>();
  // Strip comments first: a class named only inside a comment is not defined.
  const live = css.replace(/\/\*[\s\S]*?\*\//g, '');
  for (const match of live.matchAll(/\.([A-Za-z][\w-]*)/g)) {
    found.add(match[1]);
  }
  return found;
}

describe('console styles', () => {
  const pageFiles = consolePageFiles();

  it('guards more than zero pages', () => {
    // Guard the guard: if the directory listing or filter breaks, every
    // per-page check below passes vacuously over an empty set.
    expect(pageFiles.length).toBeGreaterThan(0);
  });

  it.each(pageFiles)('%s: defines every class it emits', (fileName) => {
    const source = readFileSync(resolve(ROOT, fileName), 'utf-8');
    const emitted = emittedClasses(source);
    // Guard the guard: if the extractor stops finding classes, the assertion
    // below passes vacuously over an empty list.
    expect(emitted.length).toBeGreaterThan(0);

    const defined = definedClasses(CSS);
    const undefinedClasses = emitted.filter((name) => !defined.has(name));
    expect(undefinedClasses).toEqual([]);
  });

  it.each(pageFiles)('%s: imports the stylesheet, so it cannot mount unstyled', (fileName) => {
    const source = readFileSync(resolve(ROOT, fileName), 'utf-8');
    // Imported IN THE PAGE, not at an entry point: a page mounted elsewhere
    // must not silently pull this CSS in without also importing it (the
    // shape of the original bug).
    expect(source).toMatch(/import\s+['"]\.\/styles\/console\.css['"]/);
  });
});
