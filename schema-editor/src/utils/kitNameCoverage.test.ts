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
 * STATUS messages naming one by its LABEL, which is ambiguous for the same
 * reason: nothing enforces label uniqueness, so two kits can legitimately share
 * one. The sharpest case was the delete success banner -- irreversible, and the
 * card it names is gone from the catalogue by the time it renders.
 *
 * WHY THERE IS NO CLEVERNESS HERE. Five earlier versions tried to INFER which
 * matches were user-facing -- excluding a line by its CSS class, then by
 * containing `title={`, then by a brace region, then by a nearby `===`, then by
 * counting backticks to guess "am I inside a template literal". A reviewer
 * defeated every one, and the last was the worst: an ordinary `//` comment
 * containing a single backtick flipped the parity and blinded the guard for the
 * rest of the file. There are 171 such comments in this source; all three
 * scanned files passed only because their totals happened to be even.
 *
 * A regex scan cannot tell a template literal from a comment, a string, or a
 * regex without tokenizing TypeScript. So it no longer tries. A legitimate bare
 * label carries an explicit `// kit-label-ok:` marker in the source, and this
 * asks one question with one answer: is the marker there? The whole exemption
 * set is FOUR lines (two tooltips, each a two-branch ternary), so the cost is
 * four comments, and nothing goes unflagged unless a human wrote the marker
 * on its own line above it. That claim is narrower than the one this docstring
 * first made ("the false-negative surface is zero"), which review falsified:
 * the check used `.includes()` and kept the offender's own line, so the marker
 * text inside a STRING LITERAL, or trailing on the offending line itself, both
 * licensed a real message. Matching text instead of asking the question -- the
 * same habit, one level up.
 *
 * The limit that REMAINS, stated because a guard that hides one reads as
 * broader assurance than it is: this matches a SHAPE, `${kit.label}`. A label
 * reaching a human another way -- through a variable, a prop, a server message,
 * or a JSX text node like `<option>{k.label}</option>` (bd polyglot-pdf-5ivqx)
 * -- is invisible to it. `kitLabel` props are deliberately out of scope: the
 * call site knows what else is on screen, so the decision belongs there.
 */
const BARE_KIT_LABEL = /\$\{\s*(?:kit|entry|created|k)\??\.label\b/;
const ALL_BARE_KIT_LABELS = new RegExp(BARE_KIT_LABEL.source, 'g');

/** Marks a bare label as deliberate. Must sit within MARKER_REACH lines above. */
const MARKER = '// kit-label-ok:';
const MARKER_REACH = 6;

/**
 * Offending line numbers in one file's text.
 *
 * Takes TEXT, not a path, so the battery below drives THIS -- the real scan.
 * An earlier battery exercised a helper instead, and stayed green when the code
 * around the helper regressed.
 */
function scanForBareLabels(text: string): number[] {
  const lines = text.split('\n');
  const offenders: number[] = [];
  lines.forEach((line, i) => {
    if (!ALL_BARE_KIT_LABELS.test(line)) {
      ALL_BARE_KIT_LABELS.lastIndex = 0;
      return;
    }
    ALL_BARE_KIT_LABELS.lastIndex = 0;
    // The marker may sit a few lines up: it explains a whole ternary, and
    // prettier splits these across lines. Bounded so a marker cannot silently
    // license an unrelated match far below it.
    //
    // STRICTLY ABOVE, and the line must BE the comment rather than merely
    // contain its text. Two evasions otherwise, both found by review and both
    // the same old habit of matching text instead of asking the question:
    //   - `.includes()` accepted the marker inside a STRING LITERAL, so
    //     `const help = "write // kit-label-ok: first"` licensed a real
    //     offender below it;
    //   - `slice(from, i + 1)` kept the offender's OWN line, so a trailing
    //     `// kit-label-ok:` on the same line self-exempted -- which also
    //     contradicted this function's own "must sit above" docstring.
    // An author annotating a real message in place is exactly the review
    // signal the marker exists to create, so it must not be self-serve.
    const from = Math.max(0, i - MARKER_REACH);
    const covered = lines.slice(from, i)
      .some((l) => l.trim().startsWith(MARKER));
    if (!covered) offenders.push(i + 1);
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
      + `it -- nothing stops two kits sharing a label. Use kitName(kit), or add `
      + `a "${MARKER} <why>" comment above if the id is genuinely adjacent:\n  `
      + offenders.join('\n  ')).toEqual([]);
  });

  // TEST THE DETECTOR against every shape that defeated an earlier version.
  // Each of these was a live evasion a reviewer found, kept so a future
  // simplification cannot quietly reopen one (CLAUDE.md scar #8).
  it('flags a bare label unless it is explicitly marked', () => {
    const bare = 'setNotice(`"${kit.label}" was deleted permanently.`);';
    expect(scanForBareLabels(bare)).toEqual([1]);

    // The marker, and only the marker, exempts it.
    expect(scanForBareLabels([`  ${MARKER} the card's own tooltip`, bare]
      .join(String.fromCharCode(10)))).toEqual([]);

    // EVERY historical evasion. None of these can hide a message any more,
    // because none of them is a marker.
    const evasions = [
      // shared a line with a tooltip (beat the line-keyed exemption)
      '<b title={`x`} /> setNotice(`"${kit.label}" gone`);',
      // sat before one (beat the offset-keyed exemption)
      'setNotice(`"${kit.label}" gone`); const t = <b title={`x`} />;',
      // sat after one closed (beat the brace-region exemption)
      'const t = <b title={`x`} />; setNotice(`"${kit.label}" gone`);',
      // shared a line with a comparison (beat the ===/?? exemption)
      'if (x === y) setNotice(`"${kit.label}" done`);',
    ];
    for (const e of evasions) expect(scanForBareLabels(e)).toEqual([1]);

    // A multi-line template literal (beat the per-line backtick count).
    expect(scanForBareLabels(['setNotice(`Deleted', '  ${kit.label}',
      '  permanently.`);'].join(String.fromCharCode(10)))).toEqual([2]);

    // The marker must BE a comment, not merely appear in the text: its own
    // characters inside a string literal license nothing.
    expect(scanForBareLabels(['const help = "write ' + MARKER + ' first";', bare]
      .join(String.fromCharCode(10)))).toEqual([2]);

    // ...and it must sit ABOVE, not trail the offending line itself, or an
    // author could self-exempt a real message in place.
    expect(scanForBareLabels(bare + '  ' + MARKER + ' same-line trick'))
      .toEqual([1]);

    // The two guards above OVERLAP on a trailing marker (startsWith rejects it
    // whatever the slice does), so the slice bound needs its own case or it is
    // pinned by nothing: a line that BEGINS with the marker and also carries a
    // bare label. Only excluding the offender's own line catches this, and
    // without it the mutation `slice(from, i + 1)` passes every other test.
    expect(scanForBareLabels(`  ${MARKER} why  setNotice(\`"\${kit.label}" x\`);`))
      .toEqual([1]);

    // AND the one that beat whole-file backtick parity: an ordinary comment
    // containing a single backtick, of which this source has 171. Under the
    // old mechanism everything after it went unseen.
    expect(scanForBareLabels(['// see `kit.label` for the shape', bare]
      .join(String.fromCharCode(10)))).toEqual([2]);
  });

  it('does not let a marker license an unrelated match far below it', () => {
    // A marker is not a file-wide amnesty. Beyond its reach, a bare label is
    // an offender again -- otherwise one annotation would silently excuse
    // every message added after it, which is how the parity bug behaved.
    const filler = new Array(MARKER_REACH + 2).fill('  // padding');
    const lines = [`  ${MARKER} a real tooltip`, ...filler,
      'setNotice(`"${kit.label}" gone`);'];
    expect(scanForBareLabels(lines.join(String.fromCharCode(10))))
      .toEqual([lines.length]);
  });
});
