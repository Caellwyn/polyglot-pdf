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

/** The connect-poll block: from the wait loop to the timeout error. */
function connectPollBlock(source: string): string {
  const start = source.indexOf('const maxWaitMs');
  const end = source.indexOf("setError('Connection timed out - please try again')", start);
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

  it('does not set the contradictory English timeout error', () => {
    const block = connectPollBlock(SOURCE);
    expect(block.length).toBeGreaterThan(100);

    // The setError is guarded so a spent link falls through it. Scoped to the
    // final-status check, so the loop's own break cannot satisfy this.
    const finalCheck = block.slice(block.indexOf('const finalStatus'));
    expect(finalCheck).toContain("finalStatus !== 'budget_exhausted'");
  });
});
