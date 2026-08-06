/**
 * The static form-kit bundle must never ship a kit's _archive/ directory
 * (bd polyglot-pdf-w3zw).
 *
 * <kit>/_archive/<marker>/ holds SUPERSEDED schemas -- an operator-only,
 * legal-retention surface read through the authenticated store by
 * scripts/read_kit_revision.py. frontend/scripts/generate-form-manifest.ts
 * copies the kit tree into frontend/public with a RECURSIVE fs.cp, and Firebase
 * Hosting serves whatever lands in the bundle, so without a filter every
 * superseded schema becomes fetchable at
 * /form-kits/<kit>/_archive/<marker>/schema.json.
 *
 * The deploy scripts' own `case "$kit_id" in _*)` guards only skip TOP-LEVEL
 * underscore entries (form-kits/_translation), which is why a nested _archive
 * slipped past them.
 *
 * The script runs on import (it calls run() at module scope), so it cannot be
 * imported here. These tests therefore do two things: assert the SOURCE still
 * carries a copy filter (so deleting it fails, which a behavior-only test using
 * a local copy of the logic could never catch), and exercise the filter's
 * semantics against a real directory tree.
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../scripts/generate-form-manifest.ts",
);

async function exists(p: string) {
  return fs.access(p).then(() => true).catch(() => false);
}

describe("static form-kit bundle", () => {
  it("the copy step still filters underscore-prefixed entries", async () => {
    const source = await fs.readFile(SCRIPT, "utf-8");
    const copyFn = source.slice(source.indexOf("async function copyKitsToPublic"));
    const body = copyFn.slice(0, copyFn.indexOf("\n}"));

    // fs.cp is recursive here; a filter is the only thing keeping _archive out.
    expect(body).toContain("fs.cp");
    expect(body).toMatch(/filter:/);
    expect(body).toMatch(/startsWith\(["']_["']\)/);
  });

  it("that filter excludes a kit's _archive but still ships its live files", async () => {
    // The exact predicate the script passes to fs.cp.
    const filter = (src: string) => !path.basename(src).startsWith("_");

    const source = await fs.mkdtemp(path.join(os.tmpdir(), "kits-src-"));
    const dest = await fs.mkdtemp(path.join(os.tmpdir(), "kits-dst-"));

    await fs.mkdir(path.join(source, "w7", "_archive", "12-2024"), {
      recursive: true,
    });
    await fs.writeFile(path.join(source, "w7", "schema.json"), '{"live":true}');
    await fs.writeFile(path.join(source, "w7", "form.pdf"), "%PDF");
    await fs.writeFile(
      path.join(source, "w7", "_archive", "12-2024", "schema.json"),
      '{"superseded":true}',
    );
    // The pre-existing top-level case the deploy scripts already handled.
    await fs.mkdir(path.join(source, "_translation"), { recursive: true });
    await fs.writeFile(path.join(source, "_translation", "glossary.json"), "{}");

    await fs.cp(source, dest, { recursive: true, filter });

    // The superseded revision must NOT be publicly fetchable.
    expect(await exists(path.join(dest, "w7", "_archive"))).toBe(false);
    expect(await exists(path.join(dest, "_translation"))).toBe(false);
    // ...while the kit itself still ships.
    expect(await exists(path.join(dest, "w7", "schema.json"))).toBe(true);
    expect(await exists(path.join(dest, "w7", "form.pdf"))).toBe(true);
  });
});
