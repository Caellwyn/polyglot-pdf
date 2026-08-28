/**
 * Pins the COMPLETE SET of auth-failure handling sites (bd polyglot-pdf-yswp3).
 *
 * WHY A SOURCE-SCANNING TEST rather than only behavioural ones:
 *
 * A 401 and a 403 need OPPOSITE remedies -- "sign in again" vs "an operator
 * must grant you access, retrying cannot help". Every place that can receive
 * one must handle both and forward the ERROR so App can tell them apart. That
 * is not one behaviour; it is an invariant over a SET of sites across six
 * files, and the set is what kept getting missed.
 *
 * This bead is the case study. Pass 1 wired the refused screen at the GATE
 * only. Pass 2 widened App (6 sites) and RemoteCatalogue (9) and called it
 * "fixed as a SET" -- and missed ValidationPanel. Pass 3 fixed that and added
 * a guard -- whose patterns could only see files that ALREADY mentioned
 * AuthError, so it was blind to ArchivedVersions and FormCatalogue, which
 * handled auth NOWHERE AT ALL and therefore matched nothing. Three rounds,
 * each finding one more member of one set: exactly the pattern CLAUDE.md scar
 * tissue #8 names as this repo's largest source of review rounds.
 *
 * That last miss is the important lesson, and it shapes this file: a guard
 * that greps for the WRONG version of a thing can only ever find files that
 * are already thinking about it. So the primary test below starts from the
 * NETWORK CALLS -- every function in remoteKitStore that goes through
 * `editorFetch` and can therefore throw -- and requires each of their callers
 * to handle auth. A brand-new component that calls the store and ignores auth
 * entirely now fails, which is the case that actually shipped twice.
 *
 * WHAT THIS FILE CANNOT DO, stated plainly so nobody trusts it too far: the
 * check is per-FILE, not per-CALL-SITE. A file that handles auth on one call
 * and swallows it on another passes -- which is exactly how App.tsx hid a
 * swallowed 403 in its readiness-stamp catch through four review rounds (the
 * file mentions AuthError many times over). Only a BEHAVIOURAL test pins an
 * individual call site; see App.local-stamp.test.ts. This guard catches the
 * whole-file omission, which is the failure that actually shipped twice, and
 * is a floor rather than a ceiling.
 *
 * The two secondary tests catch the narrower degradations of a site that IS
 * handling auth:
 *   - a narrow predicate (`instanceof AuthError` with no ForbiddenError);
 *   - a bare forward (`onAuthError?.()`), which tsc CANNOT catch, since
 *     `() => void` and `(err?: unknown) => void` are structurally compatible
 *     both ways -- so the routing silently degrades to "every 403 is a 401".
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const SRC = join(__dirname, '..');
// The store is the main network surface, but NOT the only one: localStamp.ts
// builds its own request rather than going through editorFetch, and App's call
// to it swallowed auth failures for four review rounds precisely because a
// store-only scan could not see it. Any module that talks to the editor API
// belongs here.
const NETWORK_MODULES = [
  join(SRC, 'utils', 'remoteKitStore.ts'),
  join(SRC, 'utils', 'localStamp.ts'),
];

/** Every non-test source file under schema-editor/src.
 *
 * WALKED, never hand-listed: a hand-listed set is the very bug this file
 * exists to prevent -- a new file would simply never be checked. */
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

const base = (f: string) => f.split(/[\\/]/).pop() as string;

/** Every exported network function across NETWORK_MODULES -- anything that can
 * raise AuthError/ForbiddenError at a caller. Read from the modules THEMSELVES
 * so a newly added route is covered the day it lands, and matched in both
 * declaration styles (`export async function` and `export const x = async`) so
 * a style change cannot silently shrink the set. */
function networkFunctions(): string[] {
  const names = new Set<string>();
  for (const mod of NETWORK_MODULES) {
    const src = readFileSync(mod, 'utf8');
    for (const m of src.matchAll(/^export async function (\w+)/gm)) names.add(m[1]);
    for (const m of src.matchAll(/^export const (\w+)\s*[:=][^=]*=>/gm)) names.add(m[1]);
  }
  // Not network calls -- pure local helpers exported from the same modules.
  names.delete('invalidateLocalStamp');
  return [...names];
}

describe('auth-failure routing (the SET, not an instance)', () => {
  // THE primary guard. Starts from the network calls, so it sees a file that
  // handles auth NOWHERE -- the case that shipped twice and that a
  // grep-for-AuthError guard is structurally blind to.
  it('every caller of a store network function handles auth failure', () => {
    const net = networkFunctions();
    // A vacuous scan would pass silently; both inputs must be real.
    expect(net.length).toBeGreaterThan(10);
    const files = sourceFiles();
    expect(files.length).toBeGreaterThan(10);

    const offenders: string[] = [];
    for (const file of files) {
      if (NETWORK_MODULES.includes(file)) continue;
      const src = readFileSync(file, 'utf8');
      const called = net.filter((fn) => new RegExp(`\\b${fn}\\s*\\(`).test(src));
      if (called.length === 0) continue;
      // Either it routes auth itself, or it hands the decision to a host.
      if (src.includes('AuthError') || src.includes('onAuthError')) continue;
      offenders.push(
        `${relative(SRC, file)} calls ${called.join(', ')} but never mentions `
        + 'AuthError/ForbiddenError/onAuthError');
    }

    expect(offenders,
      'These call the editor API but do nothing about a 401/403, so a signed-out '
      + 'or role-revoked editor gets a raw error string instead of being routed '
      + 'to sign-in or the refused screen. Either handle both error types, or '
      + 'take an `onAuthError?: (err?: unknown) => void` prop and forward:\n'
      + offenders.join('\n')).toEqual([]);
  });

  // SignInGate branches on ForbiddenError FIRST (its dedicated refused screen)
  // and reaches the AuthError arm only for a genuine 401, so a bare
  // `instanceof AuthError` is correct there -- widening it would send a refused
  // account round the sign-in form, the very bug this set exists to prevent.
  // An ALLOWLIST, so a new exemption is a deliberate, reviewable edit.
  const ALLOWED_NARROW = new Set(['SignInGate.tsx']);

  it('every catch site accepts ForbiddenError, not only AuthError', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      if (ALLOWED_NARROW.has(base(file))) continue;
      const src = readFileSync(file, 'utf8');
      src.split('\n').forEach((line, i) => {
        if (!line.includes('instanceof AuthError')) return;
        if (line.includes('ForbiddenError')) return;
        offenders.push(`${base(file)}:${i + 1}: ${line.trim()}`);
      });
    }

    expect(offenders,
      'These catch a 401 but let a 403 fall through to a generic error banner, '
      + 'so an editor whose role was revoked gets a message they cannot act on '
      + 'instead of the refused screen. Widen to '
      + '`err instanceof AuthError || err instanceof ForbiddenError`:\n'
      + offenders.join('\n')).toEqual([]);
  });

  it('every onAuthError forward carries the error, and every prop receives it', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      const src = readFileSync(file, 'utf8');
      src.split('\n').forEach((line, i) => {
        // A call with EMPTY parens: the error never reaches the host, so a 403
        // is indistinguishable from a 401 downstream.
        if (/onAuthError\??\.?\(\s*\)/.test(line)) {
          offenders.push(`${base(file)}:${i + 1}: bare call -- ${line.trim()}`);
        }
        // A prop declared to take nothing invites exactly that bare call.
        const decl = /onAuthError\??\s*:\s*\(([^)]*)\)\s*=>/.exec(line);
        if (decl && decl[1].trim() === '') {
          offenders.push(`${base(file)}:${i + 1}: bare type -- ${line.trim()}`);
        }
      });
    }

    expect(offenders,
      'The error must travel: App tells a 403 (refused screen) from a 401 (sign '
      + 'in again) BY ITS TYPE, and tsc cannot catch this -- `() => void` and '
      + '`(err?: unknown) => void` are structurally compatible both ways, so the '
      + 'routing silently degrades to treating every 403 as a 401:\n'
      + offenders.join('\n')).toEqual([]);
  });
});
