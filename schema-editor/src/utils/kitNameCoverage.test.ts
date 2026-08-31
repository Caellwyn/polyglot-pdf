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
 * invisible here. `kitLabel` props in particular are deliberately out of
 * scope: a component receiving one has no id to pair with it, so the decision
 * belongs at the call site that has both.
 */
const BARE_KIT_LABEL = /\$\{\s*(?:kit|entry|created|k)\??\.label\b/;

describe('kit label coverage (bd polyglot-pdf-nsz2d)', () => {
  const files = sourceFiles(SRC);

  it('no user-facing string names a kit by label alone', () => {
    const offenders: string[] = [];
    for (const f of files) {
      // kitName.ts IS the formatter -- it necessarily reads the raw label.
      if (f.endsWith('kitName.ts')) continue;
      const text = fs.readFileSync(f, 'utf8');
      // A `title={...}` tooltip can span several lines (it is usually a
      // ternary), so membership is tracked by BRACE DEPTH across lines.
      //
      // Crucially the exemption covers the OFFSET of the matched label, not
      // the whole line: keying it to the line lets a genuine offender hide by
      // merely SHARING a line with a tooltip. That is not hypothetical -- I
      // wrote that version, then defeated it with
      // `setNotice(\`"${kit.label}" gone\`); const t = <b title={\`x\`} />;`
      // and watched it pass. Same shape as the `text-gray-500` exemption
      // deleted in bd kztlr: an exemption keyed on something ADJACENT to the
      // thing it means to excuse will eventually excuse something else.
      let depthBefore = 0;
      text.split('\n').forEach((line, i) => {
        const openedAt = line.indexOf('title={');
        // Where the tooltip region covers this line, as [start, end) offsets.
        let regionStart = depthBefore > 0 ? 0 : (openedAt >= 0 ? openedAt : -1);
        let depth = depthBefore;
        let regionEnd = -1;
        for (let c = 0; c < line.length; c += 1) {
          const inRegion = depth > 0 || (openedAt >= 0 && c >= openedAt);
          if (!inRegion) continue;
          if (line[c] === '{') depth += 1;
          else if (line[c] === '}') {
            depth = Math.max(0, depth - 1);
            if (depth === 0) regionEnd = c;
          }
        }
        if (regionStart >= 0 && regionEnd < 0) regionEnd = line.length;
        depthBefore = depth;

        const at = line.search(BARE_KIT_LABEL);
        if (at < 0) return;
        const inTooltip = regionStart >= 0 && at >= regionStart && at < regionEnd;
        // A comparison is not a message: `label === kit.label` guards a no-op
        // rename, and `?? kit.id` is a fallback, not prose.
        if (/===|!==|\?\?/.test(line)) return;
        // A card's own hover tooltip is the ONE place label-only is right: it
        // is attached to the card, whose subtitle renders the id three lines
        // below, so both identities are already side by side. Keyed on the
        // `title={` attribute that MAKES it a tooltip (and the continuation
        // lines of that same ternary), not on styling that happens to sit
        // nearby -- an exemption keyed on something unrelated is how a guard
        // silently widens.
        if (inTooltip) return;
        offenders.push(`${path.relative(SRC, f)}:${i + 1}  ${line.trim()}`);
      });
    }
    expect(offenders, `These name a kit by label alone, which does not identify `
      + `it -- nothing stops two kits sharing a label. Use kitName(kit):\n  `
      + offenders.join('\n  ')).toEqual([]);
  });
});
