import React from 'react';

interface PageIntroProps {
  /** The one-sentence "what this page is for" line (bd polyglot-pdf-dp1zq).
   * Keep it to one sentence -- see the bead's own instruction, "keep each
   * to one sentence" -- so this is a purpose statement, not a help page. */
  children: React.ReactNode;
}

/**
 * Shared one-sentence purpose header (bd polyglot-pdf-dp1zq), rendered at
 * the top of every page under src/pages/ right after the page's <h2>
 * title. Maintainer feedback 2026-09-15 after first console sign-in ("not
 * sure what the 'users' tab does") is why this exists: every tab now says,
 * in one sentence, what it is for.
 *
 * ONE COMPONENT, deliberately (CLAUDE.md scar #8, "enumerate the set before
 * fixing any of it"): the fix here is not "add a paragraph to nine files"
 * but "give every page purpose-line the SAME markup", so
 * pageIntroCoverage.test.tsx's enumeration test (every file in src/pages/
 * renders exactly one `data-testid="page-intro"` node) can never be
 * defeated by one page writing its own differently-shaped <p> that happens
 * to look right.
 */
export const PageIntro: React.FC<PageIntroProps> = ({ children }) => (
  <p data-testid="page-intro" className="mt-1 text-sm text-gray-600">
    {children}
  </p>
);
