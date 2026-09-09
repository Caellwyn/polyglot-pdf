// Every class a console page emits must be defined, and the stylesheet must
// be reachable from that page (bd polyglot-pdf-41ay8; extended to every
// console page, not just MintLinkPage, by bd polyglot-pdf-krbol).
//
// The bug this pins: MintLinkPage shipped emitting `mint-page`,
// `mint-result` and `mint-note` with NO stylesheet defining any of them, so
// /console/links rendered as a bare browser form. Nothing failed -- the page
// worked, it just looked unfinished, which no behavioral test can see.
//
// DERIVED FROM THE FILES, never a typed list of class names -- that goes
// stale the moment someone adds a class. The PAGE_FILES list below is still a
// short hand-written list, but it is the set of *files*, not classes -- each
// new console page adds one line here, not a fragile per-class enumeration.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(process.cwd(), 'src/console');
const CSS = readFileSync(resolve(ROOT, 'styles/console.css'), 'utf-8');

/** Every console page that renders className markup and must therefore be
 * checked against the shared stylesheet. */
const PAGE_FILES = ['MintLinkPage.tsx', 'EmployeesPage.tsx'];

/** Class names the PAGE actually emits, from its className attributes. */
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

describe.each(PAGE_FILES)('console styles: %s', (fileName) => {
  const page = readFileSync(resolve(ROOT, fileName), 'utf-8');

  it('defines every class the page emits', () => {
    const emitted = emittedClasses(page);
    // Guard the guard: if the extractor stops finding classes, the assertion
    // below passes vacuously over an empty list.
    expect(emitted.length).toBeGreaterThan(0);

    const defined = definedClasses(CSS);
    const undefinedClasses = emitted.filter((name) => !defined.has(name));
    expect(undefinedClasses).toEqual([]);
  });

  it('is imported by the page, so it cannot mount unstyled', () => {
    // The page is the only consumer. Wiring the import at an entry point
    // instead would let the page be mounted somewhere that forgot it -- the
    // shape of the original bug.
    expect(page).toMatch(/import\s+['"]\.\/styles\/console\.css['"]/);
  });
});
