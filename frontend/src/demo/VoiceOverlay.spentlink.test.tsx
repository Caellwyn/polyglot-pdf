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
import ts from 'typescript';

const OVERLAYS = [
  ['VoiceOverlay', resolve(process.cwd(), 'src/demo/VoiceOverlay.tsx')],
  ['VoiceOverlayMobile', resolve(process.cwd(), 'src/demo/VoiceOverlayMobile.tsx')],
] as const;

/**
 * THESE GUARDS USE THE TYPESCRIPT PARSER, after four hand-rolled versions were
 * each defeated by a shape the previous one did not anticipate:
 *
 *   1. `setError('Connection...')`  -- missed the ternary/template house style
 *   2. `[^;]*?` + `\)\s*$`          -- missed a semicolon and a trailing comment
 *   3. `[\s\S]*?`                   -- paren-unaware: a nested call hid the word
 *   4. hand-counted parens/braces   -- string- and comment-unaware: a `)` in a
 *                                      string, or a `{` in a COMMENT inside a
 *                                      guard block, miscounts
 *
 * Each round I patched the symptom and shipped a guard that was defeatable in
 * a way I had not thought of yet. That is not a tuning problem: these are TSX
 * files where braces in comments and parens in strings are ordinary, and a
 * character scan cannot tell code from prose. `typescript` is already a
 * dependency and its parser knows the difference by construction, so the
 * structural claims below ("this call", "inside this if-block") are asked of
 * an AST rather than inferred from text.
 */
function parse(source: string, file: string): ts.SourceFile {
  return ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
}

function connectionErrorArgs(source: string, file: string): string[] {
  const found: string[] = [];

  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'setError'
    ) {
      const arg = node.arguments.map((a) => a.getText()).join(', ');
      if (/connect/i.test(arg)) found.push(arg);
    }
    ts.forEachChild(node, visit);
  };

  ts.forEachChild(parse(source, file), visit);
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
function unguardedErrorStatusWrites(source: string, file: string): string[] {
  const offenders: string[] = [];

  /** Does any ANCESTOR if-statement test !== 'budget_exhausted'? */
  const guardedByAncestor = (node: ts.Node): boolean => {
    for (let p = node.parent; p; p = p.parent) {
      if (ts.isIfStatement(p) && /!==\s*['"]budget_exhausted['"]/.test(p.expression.getText())) {
        // Containment is structural: the write is in the THEN branch, not
        // merely after the guard. A write in the else branch is NOT guarded.
        if (p.thenStatement.getStart() <= node.getStart() &&
            node.getEnd() <= p.thenStatement.getEnd()) {
          return true;
        }
      }
    }
    return false;
  };

  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'setStatus' &&
      node.arguments.length === 1 &&
      ts.isStringLiteral(node.arguments[0]) &&
      node.arguments[0].text === 'error' &&
      !guardedByAncestor(node)
    ) {
      const { line } = ts.getLineAndCharacterOfPosition(
        node.getSourceFile(),
        node.getStart(),
      );
      offenders.push(`${file}:${line + 1}`);
    }
    ts.forEachChild(node, visit);
  };

  ts.forEachChild(parse(source, file), visit);
  return offenders;
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
    // MATCH THE CALL, NOT ONE SPELLING OF ITS ARGUMENT. A set defined by
    // MEANING cannot be pinned by a syntactic shape -- see the parser note at
    // the top of this file for the four versions that proved it.
    const bare = connectionErrorArgs(SOURCE, path);
    expect(bare).toEqual([]);

    // And the helper actually suppresses on the terminal status.
    const helper = SOURCE.slice(SOURCE.indexOf('const setConnectionError'));
    expect(helper.slice(0, 500)).toContain("=== 'budget_exhausted'");
  });

  it('does not overwrite the terminal STATUS either', () => {
    // Suppressing the error TEXT while still writing setStatus('error') was the
    // incomplete half (Opus cross-surface r3). FOUR surfaces key off
    // budget_exhausted -- the spend-ceiling modal, the save nudge's voiceEnding
    // gate (level-triggered, so an already-showing nudge vanishes), the
    // controls ternary (which renders Reconnect for 'error'), and
    // solState.isOffline (which makes Sol LEAVE rather than dim). Overwriting
    // the status restores the dead button this work removed, and the parent
    // cannot repair it: its sync effect keys on [sharedStatus], which never
    // changes.
    //
    // CONTAINMENT, NOT PROXIMITY: the write must be in the guard's THEN branch,
    // which is an AST question, not a text-distance one.
    expect(unguardedErrorStatusWrites(SOURCE, path)).toEqual([]);
  });
});

// The parametrized suite above asserts per file, but the STATUS test iterates
// over whatever writes each file has -- and VoiceOverlayMobile has ZERO, so its
// arm proves nothing on its own (scar #8: a loop over an empty set passes
// vacuously). This asserts the property that actually matters and cannot go
// vacuous: SOMEWHERE in the pair there is a real guarded write, so the guard
// above is exercised against live code rather than an empty list.
it('exercises the status guard against at least one real write', () => {
  const total = OVERLAYS.reduce((n, [, file]) => {
    const source = readFileSync(file, 'utf-8');
    let count = 0;
    const visit = (node: ts.Node): void => {
      if (
        ts.isCallExpression(node) &&
        ts.isIdentifier(node.expression) &&
        node.expression.text === 'setStatus' &&
        node.arguments.length === 1 &&
        ts.isStringLiteral(node.arguments[0]) &&
        node.arguments[0].text === 'error'
      ) {
        count += 1;
      }
      ts.forEachChild(node, visit);
    };
    ts.forEachChild(parse(source, file), visit);
    return n + count;
  }, 0);

  expect(total).toBeGreaterThan(0);
});
