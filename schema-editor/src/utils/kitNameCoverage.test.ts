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
