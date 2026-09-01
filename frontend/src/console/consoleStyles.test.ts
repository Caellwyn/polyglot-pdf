// Every class the console page emits must be defined, and the stylesheet must
// be reachable from the page (bd polyglot-pdf-41ay8).
//
// The bug this pins: MintLinkPage shipped emitting `mint-page`,
// `mint-result` and `mint-note` with NO stylesheet defining any of them, so
// /console/links rendered as a bare browser form. Nothing failed -- the page
// worked, it just looked unfinished, which no behavioral test can see.
//
// DERIVED FROM BOTH FILES, never a typed list. A hand-written list of class
// names is the same bug one level up: it goes stale the moment someone adds a
// class, and this repo has paid for hand-listed sets repeatedly.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(process.cwd(), 'src/console');
const PAGE = readFileSync(resolve(ROOT, 'MintLinkPage.tsx'), 'utf-8');
const CSS = readFileSync(resolve(ROOT, 'styles/console.css'), 'utf-8');

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

describe('console styles', () => {
  it('defines every class the page emits', () => {
    const emitted = emittedClasses(PAGE);
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
    expect(PAGE).toMatch(/import\s+['"]\.\/styles\/console\.css['"]/);
  });
});
