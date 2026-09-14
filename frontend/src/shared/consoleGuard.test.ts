/**
 * Guard: no `console.*` call in frontend/src may pass an argument that NAMES
 * a raw field-value map or a token/credential identifier (bd polyglot-pdf-8v8i7).
 *
 * This is a NARROW source scan, not a blanket console ban -- `pure` in the
 * production vite configs strips console.log/console.debug at build time, but
 * a dev/staging build (and console.warn/error, which `pure` never touches
 * because staff read them) still executes these calls, so a value-carrying
 * argument leaks into the console of a shared device regardless of build
 * mode. The banned identifiers are deliberately narrow: `fieldValues`,
 * `current_values`, and anything naming a token/credential -- NOT `value`,
 * `message`, or `state`, which are used everywhere in this codebase for
 * things that are not raw PII (a single field's already-redacted status, an
 * error message, a connection status string) and would need an
 * ever-growing allowlist to avoid drowning in false positives.
 *
 * A call is flagged only when the banned identifier appears as a real
 * identifier in the call's ARGUMENTS (not inside a string/template literal --
 * a message that merely mentions "token" in prose, e.g. "falling back to
 * last-known token", is not a leak).
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC_ROOT = join(__dirname, "..");

/** Identifiers that name a raw value map or a credential; word-boundary matched. */
const BANNED_IDENTIFIERS = [
  "fieldValues",
  "current_values",
  // Token/credential identifiers: idToken, linkToken, authToken, token, etc.
  // Matched case-insensitively as a whole word so `token`, `idToken`,
  // `linkToken`, `sessionToken` are all caught as their OWN identifier.
  "token",
  "idToken",
  "linkToken",
  "authToken",
  "sessionToken",
  "credential",
];

/**
 * Strip string and template literal CONTENTS (keep delimiters) so prose
 * mentioning a banned word inside a message never counts as naming the
 * identifier. Does not need to be a full JS parser -- good enough to avoid
 * false positives on the message text this codebase actually writes.
 */
function stripStringContents(code: string): string {
  let out = "";
  let i = 0;
  while (i < code.length) {
    const ch = code[i];
    if (ch === "'" || ch === '"' || ch === "`") {
      const quote = ch;
      out += quote;
      i++;
      while (i < code.length && code[i] !== quote) {
        if (code[i] === "\\") {
          i += 2;
          continue;
        }
        // Keep template-literal ${...} interpolations intact -- an
        // interpolated banned identifier IS a real leak.
        if (quote === "`" && code[i] === "$" && code[i + 1] === "{") {
          let depth = 1;
          out += "${";
          i += 2;
          while (i < code.length && depth > 0) {
            if (code[i] === "{") depth++;
            if (code[i] === "}") depth--;
            if (depth > 0) out += code[i];
            i++;
          }
          out += "}";
          continue;
        }
        i++;
      }
      out += quote;
      i++;
      continue;
    }
    out += ch;
    i++;
  }
  return out;
}

/** Extract each `console.<method>(...)` call's full argument text (balanced parens). */
function extractConsoleCalls(code: string): string[] {
  const calls: string[] = [];
  const re = /console\.(log|debug|warn|error|info)\s*\(/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(code)) !== null) {
    let depth = 1;
    let i = match.index + match[0].length;
    const start = i;
    while (i < code.length && depth > 0) {
      if (code[i] === "(") depth++;
      if (code[i] === ")") depth--;
      i++;
    }
    calls.push(code.slice(start, i - 1));
  }
  return calls;
}

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

/** Find every banned-identifier hit across the whole shipped frontend/src tree. */
function findViolations(): { file: string; snippet: string; identifier: string }[] {
  const files = collectSourceFiles(SRC_ROOT);
  const violations: { file: string; snippet: string; identifier: string }[] = [];

  for (const fullPath of files) {
    const relPath = fullPath.slice(SRC_ROOT.length + 1).replace(/\\/g, "/");
    const raw = readFileSync(fullPath, "utf8");
    const codeOnly = raw
      .split("\n")
      .filter(isCode)
      .join("\n");
    const calls = extractConsoleCalls(codeOnly);
    for (const call of calls) {
      const withoutStrings = stripStringContents(call);
      for (const ident of BANNED_IDENTIFIERS) {
        const re = new RegExp(`\\b${ident}\\b`, "i");
        if (re.test(withoutStrings)) {
          violations.push({ file: relPath, snippet: call.slice(0, 120), identifier: ident });
        }
      }
    }
  }
  return violations;
}

describe("console PII guard (bd polyglot-pdf-8v8i7)", () => {
  it("has no console.* call naming fieldValues, current_values, or a token/credential identifier", () => {
    const violations = findViolations();
    if (violations.length > 0) {
      const report = violations
        .map((v) => `  ${v.file}: [${v.identifier}] ${v.snippet}`)
        .join("\n");
      throw new Error(
        `Found ${violations.length} console call(s) naming a banned identifier:\n${report}`
      );
    }
    expect(violations).toEqual([]);
  });

  // Mutation-verify the guard's OWN detection: a synthetic snippet with a
  // real leak must be caught, and prose merely mentioning "token" must not.
  it("flags a synthetic value-carrying console call (self-test)", () => {
    const code = "console.log('leak', fieldValues);";
    const calls = extractConsoleCalls(code);
    const withoutStrings = stripStringContents(calls[0]);
    expect(/\bfieldValues\b/i.test(withoutStrings)).toBe(true);
  });

  it("does not flag a console call that only mentions 'token' in prose (self-test)", () => {
    const code = "console.warn('falling back to last-known token', error);";
    const calls = extractConsoleCalls(code);
    const withoutStrings = stripStringContents(calls[0]);
    const hasBannedIdentifier = BANNED_IDENTIFIERS.some((ident) =>
      new RegExp(`\\b${ident}\\b`, "i").test(withoutStrings)
    );
    expect(hasBannedIdentifier).toBe(false);
  });
});
