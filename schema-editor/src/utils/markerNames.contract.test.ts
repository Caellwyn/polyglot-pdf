/**
 * The handshake marker filenames are a CROSS-LANGUAGE contract
 * (bd polyglot-pdf-kesf).
 *
 * Two same-folder handshakes prove the editor and a server are looking at one
 * directory. Each is a browser WRITER paired with a server READER, and the pair
 * agrees only if both spell the marker filename identically:
 *
 *   backend channel  (bd s2bf)  formKitDirectory.ts HANDSHAKE_FILE
 *                               <-> editor_kit_routes.py _HANDSHAKE_FILE
 *   extractor channel (bd ball) formKitDirectory.ts EXTRACTOR_HANDSHAKE_FILE
 *                               <-> extractEndpoint.ts HANDSHAKE_FILE
 *
 * NOTHING in either type system couples them: the Vite plugin sits outside the
 * src/ tsconfig scope (tsconfig.json "include": ["src"]), and the backend is
 * Python. Worse, the failure is SILENT -- a reader that cannot find the marker
 * treats it as "nothing observed", which is indistinguishable from a genuinely
 * wrong folder. So renaming one side permanently refuses a folder that agrees:
 * for the backend channel that switches off Repair all, Regenerate divisions,
 * Rewrite guidance and the widget picker, with no error anywhere.
 *
 * Each language's own tests hardcode the literal, so the natural self-consistent
 * refactor (rename the constant AND that language's test literals) leaves both
 * suites green while the feature is dead. This file is the only thing that reads
 * the declarations ACROSS the boundary and fails when they drift apart.
 *
 * It scrapes source text rather than importing, because importing the Python is
 * impossible and importing the Vite plugin from src/ is out of tsconfig scope --
 * the same reason the coupling is unprotected in the first place.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(__dirname, '../../..');

function read(rel: string): string {
  const p = path.join(REPO, rel);
  const src = fs.readFileSync(p, 'utf8');
  // A missing/renamed FILE must fail loudly here rather than silently yielding
  // no match and passing a vacuous comparison.
  expect(src.length, `${rel} is empty or unreadable`).toBeGreaterThan(0);
  return src;
}

/** Pull `<NAME> = '<value>'` (TS) or `<NAME> = "<value>"` (Python). */
function declared(src: string, rel: string, name: string): string {
  const m = src.match(new RegExp(`\\b${name}\\s*=\\s*['"]([^'"]+)['"]`));
  // Never return null into an equality assertion -- two nulls would "match".
  expect(m, `${name} not found in ${rel} (renamed? then fix this test too)`).toBeTruthy();
  return (m as RegExpMatchArray)[1];
}

const BROWSER = 'schema-editor/src/utils/formKitDirectory.ts';
const VITE_HOST = 'schema-editor/vite-plugins/extractEndpoint.ts';
const BACKEND = 'backend/routes/editor_kit_routes.py';

describe('handshake marker filenames stay coupled across languages', () => {
  it('backend channel: the browser writer and the Python reader agree', () => {
    const writer = declared(read(BROWSER), BROWSER, 'HANDSHAKE_FILE');
    const reader = declared(read(BACKEND), BACKEND, '_HANDSHAKE_FILE');
    expect(reader).toBe(writer);
  });

  it('extractor channel: the browser writer and the Vite host reader agree', () => {
    const writer = declared(read(BROWSER), BROWSER, 'EXTRACTOR_HANDSHAKE_FILE');
    const reader = declared(read(VITE_HOST), VITE_HOST, 'HANDSHAKE_FILE');
    expect(reader).toBe(writer);
  });

  it('the two channels use DIFFERENT names (bd polyglot-pdf-bagn)', () => {
    // Not cosmetic: the channels run unserialized against the same folder, so a
    // shared name lets either one's cleanup delete the other's in-flight marker
    // and refuse a folder that agrees. Distinct names make that impossible.
    const src = read(BROWSER);
    expect(declared(src, BROWSER, 'EXTRACTOR_HANDSHAKE_FILE'))
      .not.toBe(declared(src, BROWSER, 'HANDSHAKE_FILE'));
  });

  it('both markers are gitignored (they are transient, never committed)', () => {
    const ignored = read('.gitignore');
    const src = read(BROWSER);
    for (const name of ['HANDSHAKE_FILE', 'EXTRACTOR_HANDSHAKE_FILE']) {
      expect(ignored, `${declared(src, BROWSER, name)} missing from .gitignore`)
        .toContain(declared(src, BROWSER, name));
    }
  });
});
