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

// Exact identifiers (lowercased) that name a raw field-value map.
const BANNED_EXACT_IDENTIFIERS = ["fieldvalues", "current_values"];
// Substrings (lowercased) that flag a credential-shaped identifier: this
// catches `token`, `idToken`, `linkToken`, `link_token`, `authToken`,
// `client_token`, `credential`, etc. -- ANY identifier naming a
// token/credential, not a fixed list of exact spellings.
//
// NOT `\btoken\b` / `\bcredential\b`: JS `\b` is a transition between a
// `\w` char and a non-`\w` char, and `_` IS `\w` -- so `\btoken\b` matches
// NEITHER `link_token` (no boundary before `token`; `_` and `t` are both
// `\w`) NOR `linkToken` (no boundary at all; `k` and `T` are both `\w`).
// A snake_case OR camelCase identifier that merely CONTAINS the word is
// exactly the shape a real leak takes, so this substring-matches on
// extracted IDENTIFIER TOKENS instead of word-boundary regexing raw text.
const BANNED_IDENTIFIER_SUBSTRINGS = ["token", "credential"];

/** True when a lowercased identifier names a banned value/credential shape. */
function isBannedIdentifier(identifierLower: string): boolean {
  if (BANNED_EXACT_IDENTIFIERS.includes(identifierLower)) return true;
  return BANNED_IDENTIFIER_SUBSTRINGS.some((s) => identifierLower.includes(s));
}

/** Extract real identifier tokens (not string/number literals) from code text. */
function extractIdentifiers(code: string): string[] {
  return code.match(/[A-Za-z_$][\w$]*/g) ?? [];
}

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
      for (const identifier of extractIdentifiers(withoutStrings)) {
        const lower = identifier.toLowerCase();
        if (isBannedIdentifier(lower)) {
          violations.push({ file: relPath, snippet: call.slice(0, 120), identifier });
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
    const identifiers = extractIdentifiers(withoutStrings).map((i) => i.toLowerCase());
    expect(identifiers.some(isBannedIdentifier)).toBe(true);
  });

  it("does not flag a console call that only mentions 'token' in prose (self-test)", () => {
    const code = "console.warn('falling back to last-known token', error);";
    const calls = extractConsoleCalls(code);
    const withoutStrings = stripStringContents(calls[0]);
    const identifiers = extractIdentifiers(withoutStrings).map((i) => i.toLowerCase());
    expect(identifiers.some(isBannedIdentifier)).toBe(false);
  });

  // The exact regression fresh-eyes caught: `\btoken\b` / `\bcredential\b`
  // word-boundary regexing misses BOTH snake_case and camelCase identifiers,
  // because JS `\b` treats `_` as a word character (so `link_token` is one
  // contiguous \w run with no boundary before "token") and camelCase has no
  // separator at all (so `linkToken` has no boundary either). The fix
  // extracts real identifier tokens and substring-matches on them instead.
  it("flags snake_case and camelCase token identifiers, not just the bare word (self-test)", () => {
    const snakeCase = extractIdentifiers(
      stripStringContents(extractConsoleCalls("console.warn('x', link_token);")[0])
    ).map((i) => i.toLowerCase());
    const camelCase = extractIdentifiers(
      stripStringContents(extractConsoleCalls("console.warn('x', linkToken);")[0])
    ).map((i) => i.toLowerCase());
    expect(snakeCase.some(isBannedIdentifier)).toBe(true);
    expect(camelCase.some(isBannedIdentifier)).toBe(true);
  });
});
