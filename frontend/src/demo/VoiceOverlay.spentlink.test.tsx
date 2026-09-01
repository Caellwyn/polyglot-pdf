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
    const bare = [...SOURCE.matchAll(/(?<!Connection)\bsetError\(([^;]*?)\)\s*$/gm)]
      .map((m) => m[1])
      .filter((arg) => /connect/i.test(arg));
    expect(bare).toEqual([]);

    // And the helper actually suppresses on the terminal status.
    const helper = SOURCE.slice(SOURCE.indexOf('const setConnectionError'));
    expect(helper.slice(0, 500)).toContain("=== 'budget_exhausted'");
  });
});
