/**
 * Pins the COMPLETE SET of auth-failure catch sites (bd polyglot-pdf-yswp3).
 *
 * WHY A SOURCE-SCANNING TEST rather than more behavioural ones:
 *
 * A 401 and a 403 need OPPOSITE remedies -- "sign in again" vs "an operator
 * must grant you access, retrying cannot help". Every place that catches one
 * must therefore catch the other and forward the ERROR so App can tell them
 * apart. That is not one behaviour; it is an invariant over a SET of ~16 catch
 * sites spread across four files.
 *
 * This bead proved the set is exactly what gets missed. The first pass wired
 * the refused screen at the GATE only. The second widened App (6 sites) and
 * RemoteCatalogue (9) and CALLED IT "fixed as a SET" -- and still missed
 * ValidationPanel, whose lintSchema call is the highest-frequency remote call
 * in the editor. Two review rounds, each finding one more member of the same
 * set: exactly the pattern CLAUDE.md scar tissue #8 names as this repo's single
 * largest source of review rounds.
 *
 * Behavioural tests cannot close that: they pin the sites that EXIST, and a
 * future component added with a bare `instanceof AuthError` would ship green.
 * So this asserts the property over the source itself -- the next omission
 * fails CI instead of costing a review round.
 *
 * TWO FAILURE MODES, both caught here and both silent otherwise:
 *   1. A narrow predicate -- `instanceof AuthError` with no ForbiddenError.
 *   2. A bare forward -- `onAuthError?.()` with no argument. tsc CANNOT catch
 *      this: `() => void` and `(err?: unknown) => void` are structurally
 *      compatible in both directions, so the routing silently degrades to
 *      "always treat it as a 401".
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..');

/** Every non-test source file under schema-editor/src.
 *
 * Walked rather than hand-listed: a hand-listed set is exactly what this test
 * exists to prevent (a new file would simply never be checked). */
function sourceFiles(dir: string = SRC): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === 'test' || name === 'node_modules') continue;
      out.push(...sourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(name)) continue;
    if (/\.(test|spec)\.tsx?$/.test(name)) continue;
    out.push(full);
  }
  return out;
}

/** Catch sites that legitimately name AuthError alone.
 *
 * SignInGate branches on ForbiddenError FIRST (its dedicated refused screen)
 * and reaches the AuthError arm only for a genuine 401, so a bare
 * `instanceof AuthError` is correct there -- widening it would send a refused
 * account round the sign-in form, the very bug this set exists to prevent.
 *
 * An ALLOWLIST, so adding a new exemption is a deliberate, reviewable edit
 * rather than something a broad pattern silently absorbs. */
const ALLOWED_NARROW = new Set(['SignInGate.tsx']);

describe('auth-failure routing (the SET, not an instance)', () => {
  it('every catch site accepts ForbiddenError, not only AuthError', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      const src = readFileSync(file, 'utf8');
      const base = file.split(/[\\/]/).pop() as string;
      if (ALLOWED_NARROW.has(base)) continue;

      src.split('\n').forEach((line, i) => {
        if (!line.includes('instanceof AuthError')) return;
        if (line.includes('ForbiddenError')) return;
        offenders.push(`${base}:${i + 1}: ${line.trim()}`);
      });
    }

    expect(offenders,
      'These catch a 401 but let a 403 fall through to a generic error banner, '
      + 'so an editor whose role was revoked gets a message they cannot act on '
      + 'instead of the refused screen. Widen to '
      + '`err instanceof AuthError || err instanceof ForbiddenError`:\n'
      + offenders.join('\n')).toEqual([]);
    // The set is non-empty in reality -- an empty scan would mean the walker
    // is broken and this test is vacuous.
    expect(sourceFiles().length).toBeGreaterThan(10);
  });

  it('every onAuthError forward carries the error', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      const src = readFileSync(file, 'utf8');
      const base = file.split(/[\\/]/).pop() as string;
      src.split('\n').forEach((line, i) => {
        // A call with EMPTY parens: the error never reaches App, so a 403 is
        // indistinguishable from a 401 downstream.
        if (!/onAuthError\??\.?\(\s*\)/.test(line)) return;
        offenders.push(`${base}:${i + 1}: ${line.trim()}`);
      });
    }

    expect(offenders,
      'These call onAuthError with NO argument, so App cannot tell a 403 from '
      + 'a 401 and routes both to the sign-in form. tsc does not catch this '
      + '(the two signatures are structurally compatible). Pass the error:\n'
      + offenders.join('\n')).toEqual([]);
  });

  it('every onAuthError prop is typed to RECEIVE the error', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      const src = readFileSync(file, 'utf8');
      const base = file.split(/[\\/]/).pop() as string;
      src.split('\n').forEach((line, i) => {
        const decl = /onAuthError\??\s*:\s*\(([^)]*)\)\s*=>/.exec(line);
        if (!decl) return;
        if (decl[1].trim() !== '') return; // takes a parameter: fine
        offenders.push(`${base}:${i + 1}: ${line.trim()}`);
      });
    }

    expect(offenders,
      'These declare onAuthError as taking no parameter, which invites a bare '
      + 'call at every site that uses them. Type it `(err?: unknown) => void`:\n'
      + offenders.join('\n')).toEqual([]);
  });
});
