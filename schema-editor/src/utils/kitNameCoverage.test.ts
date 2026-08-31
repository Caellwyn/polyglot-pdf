import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

/**
 * Every user-facing string that names a kit goes through kitName()
 * (bd polyglot-pdf-kztlr).
 *
 * WHY A SOURCE SCAN. The bug is not in any one message; it is that messages
 * and the catalogue disagreed about what a kit is CALLED. A behavioural test
 * pins the messages it was written for, which is precisely the set that is
 * already correct -- the next one added is the one that regresses.
 *
 * WHAT THIS CANNOT SEE, stated plainly because a guard that hides its limits
 * is worse than none: it matches the `"${kit.id}"` / `"${entry.id}"` SHAPE. A
 * message assembling an id some other way -- a variable holding one, a
 * concatenation, an id arriving inside a server `detail` -- is invisible here.
 * The backend half of this rule has its own (ast-based) guard, and the server
 * strings it governs are what reach the user through `err.message`.
 *
 * The first version of the BACKEND guard was blind in exactly this way: it
 * enumerated the names it expected an id to live under, and so could not see
 * the delete route naming a kit through a local called `label`. That is the
 * failure mode to keep in mind when extending this one.
 */

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, '..');

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) { out.push(...sourceFiles(full)); continue; }
    if (!/\.tsx?$/.test(e.name)) continue;
    if (/\.test\.tsx?$/.test(e.name)) continue;
    out.push(full);
  }
  return out;
}

/**
 * A quoted, interpolated KIT id -- the shape every fixed site used.
 *
 * Scoped to the three names that hold a catalogue entry. A bare `${id}` is
 * deliberately NOT matched: `field.id` is quoted the same way all over the
 * validation and rename code, and flagging those would make this guard noisy
 * enough to be suppressed -- which is how a detector dies.
 */
const QUOTED_KIT_ID = /"\$\{(?:kit|entry|created)\.id\}"/;

describe('kit naming coverage (bd polyglot-pdf-kztlr)', () => {
  const files = sourceFiles(SRC);

  it('finds the editor source at all', () => {
    // A finder that silently narrows makes every check below vacuous.
    expect(files.length).toBeGreaterThan(20);
    expect(files.some((f) => f.endsWith('RemoteCatalogue.tsx'))).toBe(true);
    expect(files.some((f) => f.endsWith('formKitDirectory.ts'))).toBe(true);
  });

  it('no user-facing string quotes a raw kit id', () => {
    const offenders: string[] = [];
    for (const f of files) {
      const text = fs.readFileSync(f, 'utf8');
      text.split('\n').forEach((line, i) => {
        if (!QUOTED_KIT_ID.test(line)) return;
        // NO carve-out for the card subtitle. It renders {kit.id} UNQUOTED
        // beside the label -- deliberately, it is the one place the id is the
        // point -- and the pattern above requires quotes, so it never matched.
        // An earlier draft excluded any line containing 'text-gray-500', which
        // keyed the exemption on an unrelated Tailwind class: a future line
        // pairing that class with a genuinely raw id would have been waved
        // through silently. An exemption nothing needs is pure attack surface.
        // kitName.ts IS the formatter -- it necessarily writes the raw form.
        if (f.endsWith('kitName.ts')) return;
        offenders.push(`${path.relative(SRC, f)}:${i + 1}  ${line.trim()}`);
      });
    }
    expect(offenders, `These name a kit by its raw id where a human reads it. `
      + `Use kitName(kit), which shows the label the catalogue shows:\n  `
      + offenders.join('\n  ')).toEqual([]);
  });
});

/**
 * A bare, interpolated KIT label -- the other half of the same rule
 * (bd polyglot-pdf-nsz2d).
 *
 * bd kztlr fixed every message naming a kit by its ID. It left the SUCCESS and
 * STATUS messages naming one by its LABEL, which is ambiguous in exactly the
 * same way and for the same reason: nothing enforces label uniqueness, so two
 * kits can legitimately share one. The sharpest case was the delete success
 * banner -- irreversible, and the card it names is gone from the catalogue by
 * the time it renders.
 *
 * Scoped to `kit`/`entry`/`created`/`k`, the four names that hold a catalogue
 * entry. `field.label`, `section.label`, `source.label` and `target.label` are
 * NOT kits, and flagging them would make this guard noisy enough to be
 * suppressed.
 *
 * The same limit as the id half applies: this matches a SHAPE. A label reached
 * some other way -- through a variable, a prop, a server message -- is
 * invisible here, and so is a JSX TEXT node (`<option>{k.label}</option>`),
 * which is a real gap tracked as bd polyglot-pdf-5ivqx.
 *
 * `kitLabel` props are deliberately out of scope: the decision belongs at the
 * call site, which knows what else is on screen. (DeleteKitDialog does also
 * receive `kitId` -- it stays label-only in its heading for the reason its own
 * comment gives, not because no id was available.)
 */
const BARE_KIT_LABEL = /\$\{\s*(?:kit|entry|created|k)\??\.label\b/;

/** The same pattern, global -- the scan must see EVERY match on a line. */
const ALL_BARE_KIT_LABELS = new RegExp(BARE_KIT_LABEL.source, 'g');

/**
 * Character offsets of every `title={...}` tooltip expression in a file.
 *
 * WHY WHOLE-FILE RATHER THAN PER-LINE. Three per-line attempts were each
 * defeated, and the third failure is the instructive one: after `title={...}`
 * closed mid-line, the region kept extending, so an offender LATER on that
 * same line was swallowed. Tracking "am I inside a region" while walking one
 * line at a time meant re-deriving that state at every line boundary, and each
 * fix repaired one boundary case and opened the next.
 *
 * Computing the spans ONCE over the whole file removes the class: a span opens
 * at `title={` and closes when its braces balance, wherever that lands. There
 * is no per-line state left to get wrong, and "is this match inside a span" is
 * then a plain interval test.
 *
 * (This is still not a JSX parser: a `title={` inside a comment or a string
 * literal opens a phantom span. Where that phantom BALANCES it exempts a
 * little text it should not -- narrow, and the battery below pins the shapes
 * that matter. Where it does NOT balance the span is DISCARDED rather than
 * run to EOF, because a span that swallowed the rest of the file would
 * disable the guard everywhere downstream: maximum blast radius, zero
 * signal.)
 */
function tooltipSpans(text: string): Array<[number, number]> {
  const spans: Array<[number, number]> = [];
  const OPEN = 'title={';
  let at = text.indexOf(OPEN);
  while (at >= 0) {
    let depth = 0;
    let i = at + OPEN.length - 1; // the '{' itself
    for (; i < text.length; i += 1) {
      if (text[i] === '{') depth += 1;
      else if (text[i] === '}') {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    // AN UNBALANCED `title={` EXEMPTS NOTHING. Running off the end means the
    // braces never closed -- a phantom opened by a `title={` inside a comment
    // or a string literal. Extending such a span to EOF would silently
    // disable this guard for the whole rest of the file, which is the worst
    // possible failure for a check: maximum blast radius, zero signal. An
    // exemption we cannot delimit is not an exemption we can trust, so it is
    // dropped and the offenders after it are reported.
    if (i < text.length) spans.push([at, i]);
    at = text.indexOf(OPEN, (i < text.length ? i : at + OPEN.length) + 1);
  }
  return spans;
}

/**
 * The guard itself, over one file's text -- returns the offending line numbers.
 *
 * EXTRACTED SO THE BATTERY DRIVES THE REAL SCAN. An earlier battery exercised
 * `tooltipSpans` directly on synthetic strings, which felt equivalent and was
 * not: reverting the caller from `matchAll` back to a single-match `.search()`
 * left every one of those cases GREEN, because the helper was still correct and
 * only its consumer had regressed. A battery that tests a helper cannot see a
 * bug in the code around it -- so this takes text, not a path, and the battery
 * feeds it the same adversarial inputs the real files would contain.
 */
function scanForBareLabels(text: string): number[] {
  const offenders: number[] = [];
  const spans = tooltipSpans(text);
  const lineStarts: number[] = [0];
  text.split('\n').forEach((l) => lineStarts.push(
    lineStarts[lineStarts.length - 1] + l.length + 1));

  text.split('\n').forEach((line, i) => {
    // A comparison is not a message: `label === kit.label` guards a no-op
    // rename, and `?? kit.id` is a fallback, not prose.
    if (/===|!==|\?\?/.test(line)) return;
    // EVERY match on the line, not just the first.
    for (const m of line.matchAll(ALL_BARE_KIT_LABELS)) {
      const abs = lineStarts[i] + (m.index ?? 0);
      // A card's own hover tooltip is the ONE place label-only is right: it is
      // attached to the card, whose subtitle renders the id three lines below,
      // so both identities are already side by side.
      if (spans.some(([a, b]) => abs >= a && abs <= b)) continue;
      offenders.push(i + 1);
    }
  });
  return offenders;
}

describe('kit label coverage (bd polyglot-pdf-nsz2d)', () => {
  const files = sourceFiles(SRC);

  it('no user-facing string names a kit by label alone', () => {
    const offenders: string[] = [];
    for (const f of files) {
      // kitName.ts IS the formatter -- it necessarily reads the raw label.
      if (f.endsWith('kitName.ts')) continue;
      const text = fs.readFileSync(f, 'utf8');
      const lines = text.split('\n');
      for (const ln of scanForBareLabels(text)) {
        offenders.push(`${path.relative(SRC, f)}:${ln}  ${lines[ln - 1].trim()}`);
      }
    }
    expect(offenders, `These name a kit by label alone, which does not identify `
      + `it -- nothing stops two kits sharing a label. Use kitName(kit):\n  `
      + offenders.join('\n  ')).toEqual([]);
  });

  // TEST THE DETECTOR. Every one of these is an evasion that actually defeated
  // an earlier version of this guard, kept as a battery so a future
  // simplification cannot quietly reopen one (CLAUDE.md scar #8: when the same
  // defect class survives twice, pin every earlier escape at once).
  it('exempts a real tooltip but nothing beside it', () => {
    // Driven through scanForBareLabels -- the REAL guard -- not through
    // tooltipSpans alone. An earlier battery tested the helper directly and
    // stayed green when the caller regressed from matchAll back to a
    // single-match .search(): the helper was still right, and only the code
    // around it was wrong. A battery aimed one layer below the bug proves
    // nothing about the bug.

    // A label INSIDE a tooltip is exempt.
    expect(scanForBareLabels(
      'title={kit.hasSchema ? `Open ${kit.label}` : `no`}')).toEqual([]);

    // The offender AFTER a same-line tooltip closes -- the evasion that beat
    // attempt three.
    expect(scanForBareLabels(
      '<b title={`x`} /> setNotice(`"${kit.label}" gone`);')).toEqual([1]);

    // ...and BEFORE it opens -- the evasion that beat attempt two.
    expect(scanForBareLabels(
      'setNotice(`"${kit.label}" gone`); const t = <b title={`x`} />;'))
      .toEqual([1]);

    // TWO labels on one line, the first exempted: the second must still be
    // seen. A single-match scan skipped the whole line.
    expect(scanForBareLabels(
      '<b title={`${kit.label}`} /> setNotice(`"${entry.label}" x`);'))
      .toEqual([1]);

    // An UNBALANCED `title={` (a phantom from a comment or string literal)
    // must exempt NOTHING rather than run to EOF.
    expect(scanForBareLabels(['title={ // never closes',
      'setNotice(`"${kit.label}" x`);'].join(String.fromCharCode(10)))).toEqual([2]);

    // A multi-line tooltip still covers a label on its continuation line.
    expect(scanForBareLabels(['title={a', '  ? `Open ${kit.label}`',
      '  : `no`}', 'setNotice(1);'].join(String.fromCharCode(10)))).toEqual([]);
  });
});
