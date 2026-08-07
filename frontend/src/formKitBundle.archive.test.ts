/**
 * The static form-kit bundle must never ship a kit's _archive/ directory
 * (bd polyglot-pdf-w3zw).
 *
 * <kit>/_archive/<marker>/ holds SUPERSEDED schemas -- an operator-only,
 * legal-retention surface read through the authenticated store by
 * scripts/read_kit_revision.py. generate-form-manifest.ts copies the kit tree
 * into frontend/public with a RECURSIVE fs.cp, and Firebase Hosting serves
 * whatever lands in the bundle, so without a filter every superseded schema
 * becomes fetchable at /form-kits/<kit>/_archive/<marker>/schema.json.
 *
 * These tests drive the REAL predicate (shouldCopyKitPath, shared with the
 * build script) rather than a copy of it. An earlier version of this file
 * grepped the script's source for keywords and exercised a hand-copied
 * duplicate -- both stayed green under a filter scoped to the TOP level only,
 * which is exactly the bug this bead fixes and exactly the mistake the deploy
 * scripts' `case "$kit_id" in _*)` guards already make (which is why a nested
 * _archive slipped past them). Testing the real thing is what closes that.
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { shouldCopyKitPath } from "../scripts/kitCopyFilter";

async function exists(p: string) {
  return fs.access(p).then(() => true).catch(() => false);
}

/** Build a kit tree, copy it exactly as the build script does, return the dest. */
async function copyFixture() {
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
  // The pre-existing TOP-level case the deploy scripts already handled.
  await fs.mkdir(path.join(source, "_translation"), { recursive: true });
  await fs.writeFile(path.join(source, "_translation", "glossary.json"), "{}");

  await fs.rm(dest, { recursive: true, force: true });
  await fs.mkdir(dest, { recursive: true });
  await fs.cp(source, dest, { recursive: true, filter: shouldCopyKitPath });
  return dest;
}

describe("static form-kit bundle", () => {
  it("excludes a NESTED <kit>/_archive from the public bundle", async () => {
    const dest = await copyFixture();

    // The load-bearing case: nested, not top level. A top-level-only filter
    // passes every other assertion here but fails this one.
    expect(await exists(path.join(dest, "w7", "_archive"))).toBe(false);
    expect(
      await exists(path.join(dest, "w7", "_archive", "12-2024", "schema.json")),
    ).toBe(false);
  });

  it("still ships the kit's live files", async () => {
    const dest = await copyFixture();

    // An inverted or over-broad filter (one that ships nothing, or only
    // underscore paths) fails here.
    expect(await exists(path.join(dest, "w7", "schema.json"))).toBe(true);
    expect(await exists(path.join(dest, "w7", "form.pdf"))).toBe(true);
  });

  it("excludes top-level underscore dirs too", async () => {
    const dest = await copyFixture();
    expect(await exists(path.join(dest, "_translation"))).toBe(false);
  });

  it("filters on the basename, so nesting depth does not matter", () => {
    // Direct predicate checks, so depth-independence stays pinned even if the
    // fixture above ever stops covering a level. NOTE the archive is excluded
    // at its OWN entry (fs.cp then prunes the subtree and never visits the
    // children), which is why "_archive" is false while a child like
    // "_archive/12-2024" -- whose basename carries no underscore -- is not
    // itself the thing being filtered.
    expect(shouldCopyKitPath(path.join("form-kits", "w7", "schema.json"))).toBe(true);
    expect(shouldCopyKitPath(path.join("form-kits", "w7", "_archive"))).toBe(false);
    expect(shouldCopyKitPath(path.join("form-kits", "_translation"))).toBe(false);
    // A DEEP underscore entry is filtered too -- the rule is per-basename, not
    // per-level, which is precisely what a top-level-only filter gets wrong.
    expect(
      shouldCopyKitPath(path.join("form-kits", "w7", "sub", "_archive")),
    ).toBe(false);
    // An absolute path must behave the same (a filter testing the whole path
    // rather than the basename would wrongly return true for everything).
    expect(shouldCopyKitPath(path.resolve("form-kits", "w7", "_archive"))).toBe(false);
  });
});
