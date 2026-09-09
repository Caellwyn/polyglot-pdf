// @vitest-environment jsdom
//
// The save nudge must fire when the SPEND CEILING ends voice (bd
// polyglot-pdf-cke6v, Opus cross-surface r1 finding 1).
//
// WHY THIS EXISTS: giving the budget close its own terminal status silently
// REMOVED this. A budget close used to land on `reconnect_failed`, which the
// overlay's voiceEnding gate names -- so the nudge fired by accident. Routing
// it to `budget_exhausted` dropped the one case that gate's own comment lists
// FIRST, and nothing went red: the fix was unpinned until this file, which a
// mutation check caught (removing the fix left 121 tests green).
//
// It matters most for exactly this population: a client-link session's saved
// PDF is their only copy, and the ending nudge is also what triggers the free
// spoken read-out of the same message.
import { describe, it, expect } from 'vitest';

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// The gate is one expression inside a large overlay component that drags in
// audio, WS and PDF workers to render. What is under test is the STATUS ->
// voiceEnding mapping, so this asserts on that expression directly rather than
// standing up the whole surface -- the same reason AppRoutes.test.tsx reads
// the route table instead of booting the app.
const SOURCE = readFileSync(
  resolve(process.cwd(), 'src/demo/VoiceOverlay.tsx'),
  'utf-8',
);

/** The terminal statuses the voiceEnding gate lists. */
function voiceEndingStatuses(source: string): string[] {
  const start = source.indexOf('voiceEnding: status.toLowerCase()');
  if (start === -1) return [];
  // The expression ends at the next property in the hook's options object.
  const end = source.indexOf('enabled:', start);
  const expr = source.slice(start, end === -1 ? start + 400 : end);
  return [...expr.matchAll(/'([a-z_]+)'/g)].map((m) => m[1]).sort();
}

describe('the save nudge on a spend-ceiling close', () => {
  it('fires for budget_exhausted, not only the older terminal statuses', () => {
    const statuses = voiceEndingStatuses(SOURCE);
    // Guard the guard: an extractor that finds nothing would pass vacuously.
    expect(statuses.length).toBeGreaterThan(1);

    expect(statuses).toContain('budget_exhausted');
    // And the cases that already worked must not have been traded away.
    expect(statuses).toContain('idle_timeout');
    expect(statuses).toContain('reconnect_failed');
  });

  it('does not show the button-less modal while the save nudge is up', () => {
    // Opus cross-surface r2. Both dialogs carry the SAME words (the ending
    // nudge and the budget modal are both the lifted voiceEnding copy), but
    // the modal is position:fixed z-index 10000 with a 75% scrim and NO
    // buttons, while the nudge underneath holds the working "Save my form"
    // button -- and the nudge has no CSS of its own to compete with. Showing
    // both told the client to save and then covered the only control that
    // saves.
    //
    // Source-level for the same reason as the gate above: the overlay drags in
    // audio/WS/PDF workers. Scoped to the modal's own JSX element so a
    // neighbouring isOpen cannot satisfy it.
    const start = SOURCE.indexOf('variant="budget_exhausted"');
    expect(start).toBeGreaterThan(-1);
    const element = SOURCE.slice(start, SOURCE.indexOf('/>', start));
    expect(element).toContain('saveNudge.variant === null');
  });

  it('keeps the comment and the code in agreement', () => {
    // The comment above the gate names the spend ceiling FIRST. It said so
    // while the code no longer covered it -- which is how the regression hid.
    // FORWARD from the call, not backward from it: the comment sits INSIDE the
    // options object, above the gate. Slicing backwards picked up an unrelated
    // neighbour and the assertion failed for the wrong reason -- the same
    // evidence-region trap this repo has hit before, caught here by the test
    // failing rather than passing.
    const start = SOURCE.indexOf('const saveNudge = useSaveNudge({');
    const block = SOURCE.slice(start, SOURCE.indexOf('enabled:', start));
    // "spend ceiling" WRAPS across two comment lines, so the gap contains a
    // newline, tabs and `//`. Matching on \s+ alone failed twice here -- the
    // words are adjacent on screen, not in the source.
    expect(block).toMatch(/spend[\s/]+ceiling/i);
    expect(block).toContain('budget_exhausted');
  });
});
