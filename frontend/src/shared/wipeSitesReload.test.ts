/**
 * Guard: every call to `SchemaFormStateManager.clearAllClientState()` in
 * frontend/src must be followed, within a few lines of the same block, by
 * `window.location.reload()` (bd polyglot-pdf-8v8i7).
 *
 * WHY A SOURCE-LEVEL GUARD, NOT A HAND-WRITTEN LIST. This is the THIRD
 * fresh-eyes round to find the same shape: a wipe site that clears
 * sessionStorage but leaves the component mounted with its stale in-memory
 * state, so the next field edit re-persists exactly what the wipe erased.
 * Round 2 fixed the two automatic triggers and the "Done -- clear now"
 * button in SchemaForm.tsx; round 3 found the SAME bug in StaffHeader.tsx's
 * logout handler, missed because nobody enumerated the whole set. Per this
 * repo's own scar tissue ("enumerate the set before fixing any of it" --
 * CLAUDE.md scar #8), the fix here is not a fourth patched site plus a
 * memory of "don't forget the reload" -- it is a test that DERIVES the set
 * by scanning, so a fifth call site added later without its reload fails
 * here instead of shipping and waiting for a fourth review round.
 *
 * Deliberately hardcodes NO file names or a count of "3 in SchemaForm.tsx,
 * 1 in StaffHeader.tsx" as an allowlist -- it just finds every call and
 * checks each one has a nearby reload. (The docstring elsewhere may state
 * the current count for a human reader; this test does not depend on it.)
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC_ROOT = join(__dirname, "..");

// How many CODE lines (comments excluded -- see isCode below) after the
// clearAllClientState() call to look for the reload. Comments don't count
// against this budget because the real sites carry a multi-line explanatory
// comment BETWEEN the two calls (up to ~10 comment lines observed) that says
// nothing about how far away the reload actually is in real code terms; a
// budget on raw lines would have to grow every time someone adds a sentence
// to that comment. A handful of CODE lines (an early return, a state update)
// is a reasonable "nearby" without accepting a reload three functions away.
const LOOKAHEAD_CODE_LINES = 4;

function isCode(line: string): boolean {
  return !/^\s*(\/\/|\*|\/\*)/.test(line);
}

/** Every .ts/.tsx source file under SRC_ROOT, excluding tests and .d.ts. */
function collectSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== "node_modules") collectSourceFiles(full, out);
      continue;
    }
    if (!/\.tsx?$/.test(entry)) continue;
    if (entry.includes(".test.") || entry.endsWith(".d.ts")) continue;
    out.push(full);
  }
  return out;
}

interface WipeSite {
  file: string;
  line: number;
  hasReload: boolean;
}

/** Find every clearAllClientState() call and whether a reload follows it nearby. */
function findWipeSites(): WipeSite[] {
  const files = collectSourceFiles(SRC_ROOT);
  const sites: WipeSite[] = [];

  for (const fullPath of files) {
    // The method's own definition lives here (`static clearAllClientState()
    // {`) -- not a CALL through `SchemaFormStateManager.`, so it would not
    // match the call regex below anyway; excluded explicitly too so a
    // future refactor of the definition's own shape can't accidentally
    // start matching it.
    if (fullPath.endsWith(join("schema-forms", "state", "schemaFormState.ts"))) continue;

    const relPath = fullPath.slice(SRC_ROOT.length + 1).replace(/\\/g, "/");
    const raw = readFileSync(fullPath, "utf8");
    const lines = raw.split("\n");

    for (let i = 0; i < lines.length; i++) {
      if (!isCode(lines[i])) continue;
      if (!/SchemaFormStateManager\.clearAllClientState\s*\(\s*\)/.test(lines[i])) continue;

      // Walk forward counting only CODE lines against the budget; comment
      // lines are free (see LOOKAHEAD_CODE_LINES).
      let hasReload = false;
      let codeLinesSeen = 0;
      for (let j = i + 1; j < lines.length && codeLinesSeen < LOOKAHEAD_CODE_LINES; j++) {
        if (!isCode(lines[j])) continue;
        codeLinesSeen++;
        if (/window\.location\.reload\s*\(\s*\)/.test(lines[j])) {
          hasReload = true;
          break;
        }
      }
      sites.push({ file: relPath, line: i + 1, hasReload });
    }
  }
  return sites;
}

describe("every clearAllClientState() call reloads nearby (bd polyglot-pdf-8v8i7)", () => {
  it("finds every wipe site and confirms each is followed by a reload", () => {
    const sites = findWipeSites();
    expect(sites.length).toBeGreaterThan(0);

    const missing = sites.filter((s) => !s.hasReload);
    if (missing.length > 0) {
      const report = missing.map((s) => `  ${s.file}:${s.line}`).join("\n");
      throw new Error(
        `Found ${missing.length} clearAllClientState() call(s) with no ` +
          `window.location.reload() within ${LOOKAHEAD_CODE_LINES} code lines:\n${report}\n\n` +
          `All ${sites.length} site(s) found:\n` +
          sites.map((s) => `  ${s.file}:${s.line} (reload: ${s.hasReload})`).join("\n")
      );
    }
  });

  // Self-test: confirms the scanner actually finds the known set today,
  // so a future refactor that accidentally stops matching (e.g. someone
  // renames the call, or wraps it in a helper) is caught here rather than
  // by the main assertion silently passing on zero sites.
  //
  // 7 = the original 4 (SchemaForm.tsx x3, StaffHeader.tsx) plus 3 added by
  // bd polyglot-pdf-ylokf: the three manual Clear-form/Start-Fresh buttons
  // (SchemaFormDemo.tsx, VoiceOverlay.tsx, VoiceOverlayMobile.tsx) switched
  // from a bare clear()+clearOnboardingState() -- which left the client-link
  // token behind -- to the composed clearAllClientState().
  it("currently finds exactly 7 wipe sites", () => {
    const sites = findWipeSites();
    expect(sites.length).toBe(7);
  });
});
