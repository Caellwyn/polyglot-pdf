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

/**
 * Pull `<NAME> = '<value>'` (TS) or `<NAME> = "<value>"` (Python).
 *
 * ANCHORED TO A REAL DECLARATION, and deliberately so. An unanchored
 * `src.match()` takes the FIRST hit anywhere in the file -- including inside a
 * COMMENT -- so a line like
 *
 *   // NOTE: was EXTRACTOR_HANDSHAKE_FILE = '.editor-extract-check.json'
 *   const EXTRACTOR_HANDSHAKE_FILE = '.editor-RENAMED.json';
 *
 * made this whole file pass green while production had genuinely drifted. That
 * is exactly the silent failure the contract exists to prevent, re-introduced
 * inside its own guard. Found by an Opus review and reproduced before fixing.
 *
 * Two defences, both load-bearing:
 *   1. Require line-start + an optional declaring keyword, so a `//` or `#`
 *      comment cannot satisfy the pattern.
 *   2. Require EXACTLY ONE match. If a constant is ever declared twice, fail
 *      loudly rather than silently picking whichever comes first.
 *   3. Require the literal to be the WHOLE right-hand side (bd
 *      polyglot-pdf-2cot). The capture used to stop at the first closing
 *      quote, so a CONCATENATION whose leading segment was unchanged compared
 *      equal on the shared prefix and passed while the sides genuinely
 *      disagreed. Reproduced before fixing: with
 *        formKitDirectory.ts   HANDSHAKE_FILE = '.editor-store-check.json' + ''
 *        editor_kit_routes.py  _HANDSHAKE_FILE = ".editor-store-check.json" + ".TOTALLY-BROKEN"
 *      this suite was GREEN 4/4 while the browser wrote one filename and the
 *      backend read another -- the exact silent degradation the file exists to
 *      prevent, re-introduced inside its own guard for the THIRD time.
 *
 *      A genuine one-piece declaration is unaffected. Anything COMPUTED (a
 *      concatenation, a template literal, an f-string, a call) now fails
 *      loudly via the exactly-one-match guard, and that is the right outcome:
 *      this test cannot evaluate an expression, so it must refuse to guess
 *      rather than compare a fragment and call it agreement.
 */
function declared(src: string, rel: string, name: string): string {
  const pattern = new RegExp(
    `^[ \\t]*(?:export\\s+)?(?:const|let|var)?[ \\t]*${name}\\s*(?::[^=]+)?=\\s*['"]([^'"]+)['"]`
      // The literal must be the WHOLE right-hand side (bd polyglot-pdf-2cot):
      // allow only a semicolon, trailing whitespace and a trailing comment
      // before end-of-line, so a `+ '...'` tail does not match at all.
      + `[ \\t]*;?[ \\t]*(?://[^\\n]*|#[^\\n]*)?$`,
    'gm',
  );
  const hits = [...src.matchAll(pattern)];
  // Never return null into an equality assertion -- two nulls would "match".
  expect(hits.length, `${name}: expected exactly 1 declaration in ${rel}, found ${hits.length}`)
    .toBe(1);
  return hits[0][1];
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

  // bd polyglot-pdf-o6io. The scrape pins a declaration at a fixed PATH, which
  // is robust against a rename or a value change (both verified by mutation)
  // but not against RELOCATION. If someone moves a constant into a shared
  // module and re-imports it, the scrape goes red with "not found" -- loud, so
  // not silent degradation. But the natural repair is to repoint the test's
  // path constant, and nothing then checks that the file being scraped is the
  // one the RUNTIME READER actually uses: the test would happily pin a stale
  // literal left behind at the old path while production used a different one.
  //
  // The available anchor is that each scraped file both DECLARES its constant
  // and USES it. Requiring a use site in the same file means a relocation
  // cannot be "repaired" by repointing the path alone -- the constant and its
  // consumer have to stay together, or this fails and names the file.
  it('each scraped declaration is USED in the file it is scraped from', () => {
    const uses: Array<[string, string]> = [
      [BROWSER, 'HANDSHAKE_FILE'],
      [BROWSER, 'EXTRACTOR_HANDSHAKE_FILE'],
      [VITE_HOST, 'HANDSHAKE_FILE'],
      [BACKEND, '_HANDSHAKE_FILE'],
    ];
    for (const [rel, name] of uses) {
      const src = read(rel);
      // Occurrences that are NOT the declaration and NOT a comment. The
      // declaration itself is excluded so a constant nobody reads cannot
      // satisfy its own pin.
      //
      // COMMENTS ARE STRIPPED STRUCTURALLY, not by a per-line startsWith test.
      // A line-prefix test only recognises a comment whose FIRST character
      // says so, which misses a `/* ... */` continuation line and a mention
      // inside a string -- both of which then count as a "use" and let a
      // genuinely dead constant satisfy this very pin. Fresh-eyes caught that
      // in the first version of this guard, which is the same class of hole
      // the rest of this file exists to close (a scan that reads prose as
      // code). Strip block comments, line comments and string literals from
      // the whole source first, then look for what remains.
      // ORDER MATTERS: strings BEFORE line comments. Stripping `#`/`//` first
      // lets a `#` or `//` INSIDE a string literal eat the rest of that line,
      // deleting a genuine use that follows it -- e.g.
      //   path = root / "#weird" / _HANDSHAKE_FILE
      // loses the use and the guard fails spuriously, blocking a legitimate
      // refactor. (Found by fresh-eyes; an earlier comment here claimed this
      // direction "fails closed", which was wrong -- it fails OPEN in the
      // sense that matters, by manufacturing a failure on correct code.)
      // Removing the strings first makes their contents unable to look like
      // a comment opener.
      const stripped = src
        // Block comments (TS) -- non-greedy, across lines.
        .replace(/\/\*[\s\S]*?\*\//g, '')
        // String literals, escape-aware, so a name mentioned in prose inside
        // quotes is not a use and a `\'` does not end the literal early.
        .replace(/'(?:[^'\\\n]|\\.)*'/g, "''")
        .replace(/"(?:[^"\\\n]|\\.)*"/g, '""')
        .replace(/`(?:[^`\\]|\\.)*`/g, '``')
        // Line comments: `//` (TS) and `#` (Python), to end of line.
        .replace(/\/\/[^\n]*/g, '')
        .replace(/#[^\n]*/g, '');
      const live = stripped
        .split(/\r?\n/)
        .filter((line) => {
          // A starred JSDoc body line survives block-stripping when the
          // comment is unterminated in the sliced region, so keep the cheap
          // prefix test as a SECOND line of defence rather than replacing it.
          if (line.trim().startsWith('*')) return false;
          if (!new RegExp(`\\b${name}\\b`).test(line)) return false;
          return !new RegExp(`^[ \\t]*(?:export\\s+)?(?:const|let|var)?[ \\t]*${name}\\s*(?::[^=]+)?=`)
            .test(line);
        });
      expect(
        live.length,
        `${name} is declared in ${rel} but never USED there -- if it moved to a ` +
          `shared module, this test is now pinning a stale literal. Point the ` +
          `scrape at the file the runtime reader imports, and keep the ` +
          `declaration with its consumer.`,
      ).toBeGreaterThan(0);
    }
  });

  it('both markers are gitignored (they are transient, never committed)', () => {
    // Whole-LINE match, not a substring. `toContain` would be satisfied by a
    // commented-out `# .editor-store-check.json` or by a longer entry such as
    // `.editor-store-check.json.bak` -- neither of which actually ignores the
    // marker. The marker is written into the user's own form-kits/ folder, so a
    // missed rule means transient scratch gets committed into a form kit.
    const rules = read('.gitignore')
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#'));
    const src = read(BROWSER);
    for (const name of ['HANDSHAKE_FILE', 'EXTRACTOR_HANDSHAKE_FILE']) {
      const marker = declared(src, BROWSER, name);
      expect(rules, `${marker} has no active .gitignore rule`).toContain(marker);
    }
  });
});
