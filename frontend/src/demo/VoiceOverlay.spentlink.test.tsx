// @vitest-environment jsdom
//
// A spent link must not show the generic connect-timeout error (bd
// polyglot-pdf-wwwa5).
//
// The backend ACCEPTS the socket before closing it 1013/budget_exhausted, so
// connect() resolves and the overlay's connect poll waits for a 'connected'
// that never arrives. It burned the full 5s and then set an untranslated
// English "Connection timed out - please try again" -- behind the translated
// spend-ceiling modal, inviting the exact retry bd cke6v exists to stop
// offering. Two messages, contradicting each other, one of them in a language
// the client may not read.
//
// Source-level, like the sibling savenudge test: these overlays drag in audio,
// WS and PDF workers to render, and what is under test is the STATUS -> error
// decision, not the rendering.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const OVERLAYS = [
  ['VoiceOverlay', resolve(process.cwd(), 'src/demo/VoiceOverlay.tsx')],
  ['VoiceOverlayMobile', resolve(process.cwd(), 'src/demo/VoiceOverlayMobile.tsx')],
] as const;

/**
 * Every BARE `setError(...)` argument that mentions a connection.
 *
 * Paren-BALANCED, because a regex cannot be. Three regex versions of this
 * guard were each defeated by a shape the previous one did not anticipate;
 * `setError(x.trim() + ' - Connection lost')` is the case that matters -- a
 * lazy pattern stops at the FIRST `)` and never sees the word.
 */
function connectionErrorArgs(source: string): string[] {
  const found: string[] = [];
  const CALL = /(?<!Connection)\bsetError\(/g;
  let match: RegExpExecArray | null;

  while ((match = CALL.exec(source)) !== null) {
    let depth = 1;
    let i = match.index + match[0].length;
    const start = i;
    while (i < source.length && depth > 0) {
      const ch = source[i];
      if (ch === '(') depth += 1;
      else if (ch === ')') depth -= 1;
      i += 1;
    }
    // Unbalanced to EOF means the extractor lost track. Surface it rather than
    // skipping, which would pass vacuously -- the failure mode this whole
    // family of guards keeps hitting.
    if (depth !== 0) {
      found.push('<unbalanced setError( -- extractor failed>');
      break;
    }
    const arg = source.slice(start, i - 1);
    if (/connect/i.test(arg)) found.push(arg);
  }
  return found;
}

/**
 * Is `index` inside the BLOCK of a `!== 'budget_exhausted'` guard?
 *
 * Brace-balanced, not proximity-based. A reviewer defeated the previous
 * "is the guard text within 300 chars before it?" version by leaving an empty
 * guard and moving the write past its closing brace -- adjacent to a guard,
 * not guarded by one, suite still green.
 */
function isInsideBudgetGuard(source: string, index: number): boolean {
  const GUARD = /!== 'budget_exhausted'\)\s*\{/g;
  let match: RegExpExecArray | null;

  while ((match = GUARD.exec(source)) !== null) {
    const blockStart = match.index + match[0].length;
    if (blockStart > index) break; // guards from here on start after the write

    let depth = 1;
    let i = blockStart;
    while (i < source.length && depth > 0) {
      const ch = source[i];
      if (ch === '{') depth += 1;
      else if (ch === '}') depth -= 1;
      i += 1;
    }
    if (depth === 0 && index >= blockStart && index < i - 1) return true;
  }
  return false;
}

/**
 * The connect-poll block: from the wait loop to the timeout error.
 *
 * Anchored on `setConnectionError('Connection timed out` -- NOT on the bare
 * `setError(`, which the helper refactor removed and which silently emptied
 * this extractor (caught by the length guard below, which is why it is there).
 * If that English string is ever translated, this returns '' and the tests go
 * RED rather than silently green -- the safe direction.
 */
function connectPollBlock(source: string): string {
  const start = source.indexOf('const maxWaitMs');
  const end = source.indexOf("setConnectionError('Connection timed out", start);
  if (start === -1 || end === -1) return '';
  return source.slice(start, end + 80);
}

describe.each(OVERLAYS)('%s: a spent link', (_name, path) => {
  const SOURCE = readFileSync(path, 'utf-8');

  it('stops waiting instead of polling out the full timeout', () => {
    const block = connectPollBlock(SOURCE);
    // Guard the guard: if the block cannot be located the assertions below
    // would pass over an empty string.
    expect(block.length).toBeGreaterThan(100);

    // The loop breaks on the terminal status rather than waiting 5s for a
    // 'connected' that a closed socket will never report.
    expect(block).toContain("=== 'budget_exhausted'");
  });

  it('routes EVERY connection error through the suppressing helper', () => {
    // PIN THE SET, NOT THE INSTANCES (CLAUDE.md scar #7). My first fix guarded
    // the two timeout sites with an inline `if`; the cross-surface review
    // found four MORE -- 'Connection lost - please click Reconnect' on the
    // disclaimer-agree reconnect, which is the DEFAULT production path (the
    // intro clip is off by default) and names a button bd cke6v removed.
    //
    // So the assertion is not "these two are guarded" but "no connection-path
    // setError bypasses the helper". A seventh site added later fails here
    // instead of shipping the same contradiction again.
    //
    // MATCH THE CALL, NOT ONE SPELLING OF ITS ARGUMENT. My first version keyed
    // on setError('Connection...') -- single-quoted string literals only -- and
    // a second review pointed out that MISSES the house style: 7 of the 9 other
    // setError calls in these files are
    // `setError(err instanceof Error ? err.message : 'Connection failed')`,
    // plus template literals and double quotes. A set defined by MEANING cannot
    // be pinned by one syntactic shape; that is the same error as grepping a
    // bead id instead of the claim.
    //
    // So: find every bare setError(, then keep the ones whose argument mentions
    // a connection at all, however it is written.
    //
    // THREE regex versions of this failed, each to a shape the last did not
    // anticipate: `[^;]*?` could not cross a semicolon; `\)\s*$` died on a
    // trailing comment; and `[\s\S]*?` is paren-UNAWARE, so
    // `setError(x.trim() + ' - Connection lost')` captured only up to the
    // FIRST `)` and the filter never saw the word. A reviewer defeated that
    // last one with a realistic regression and the suite stayed green.
    //
    // A regex cannot match balanced parens. So this scans forward counting
    // depth -- a tiny parser, which is the right tool for a structural claim.
    const bare = connectionErrorArgs(SOURCE);
    expect(bare).toEqual([]);

    // And the helper actually suppresses on the terminal status.
    const helper = SOURCE.slice(SOURCE.indexOf('const setConnectionError'));
    expect(helper.slice(0, 500)).toContain("=== 'budget_exhausted'");
  });

  it('does not overwrite the terminal STATUS either', () => {
    // Suppressing the error TEXT while still writing setStatus('error') was the
    // incomplete half (Opus cross-surface r3). FOUR surfaces key off
    // budget_exhausted -- the spend-ceiling modal, the save nudge's voiceEnding
    // gate (level-triggered, so an already-showing nudge vanishes), and the
    // controls ternary, which renders Reconnect for 'error' -- plus solState.isOffline, which makes Sol LEAVE rather than dim. Overwriting the
    // status therefore restores the dead button this work removed, and the
    // parent cannot repair it (its sync effect keys on [sharedStatus], which
    // never changes).
    //
    // Only the desktop overlay writes a status in its connect catch; mobile
    // never did, so it was already immune -- assert per file rather than
    // assuming symmetry.
    //
    // CONTAINMENT, NOT PROXIMITY. An earlier version scanned 300 chars BEFORE
    // each write for the guard text, and a reviewer defeated it by leaving an
    // empty `if (... !== 'budget_exhausted') { }` and putting the write AFTER
    // the closing brace: near the guard, not inside it, and the suite stayed
    // green. Being adjacent to a guard is not being guarded by it.
    const writes = [...SOURCE.matchAll(/setStatus\('error'\)/g)];
    for (const write of writes) {
      expect(
        isInsideBudgetGuard(SOURCE, write.index!),
        `setStatus('error') at index ${write.index} is not INSIDE a budget_exhausted guard`,
      ).toBe(true);
    }
  });
});
