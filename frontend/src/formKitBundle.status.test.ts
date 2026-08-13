/**
 * The static form-kit bundle must ship ONLY published kits (bd polyglot-pdf-fqexm).
 *
 * The kit lifecycle says a form reaches clients only at `status: complete`.
 * The backend enforces it and both deploy scripts skip everything else -- but
 * the frontend build copied the whole form-kits tree to Firebase Hosting and
 * indexed every kit that had a schema and a PDF. Drafts, kits awaiting author
 * review, and RETIRED forms were all published, and SchemaFormDemo falls back
 * to this bundled manifest whenever the backend call fails, so a retired form
 * stayed reachable there -- exactly what `unpublished` exists to prevent.
 *
 * These tests run the REAL build script against a temp tree, per the lesson in
 * formKitBundle.archive.test.ts: an earlier version of that file exercised a
 * hand-copied predicate and stayed green under the very bug it named. Driving
 * the script end to end is what makes a green run mean something.
 *
 * BOTH halves are asserted for every case. An index that omits a retired form
 * while its schema.json still sits at /form-kits/<id>/ looks fixed and is not
 * -- the file is one direct request away.
 */
import { describe, expect, it, beforeAll } from "vitest";

// Run this file ALONE. Each test here spawns a real tsx subprocess, and that
// CPU contention makes a timing-sensitive render elsewhere in the suite miss
// its window -- SchemaForm.previewEdit.test.tsx (bd polyglot-pdf-cfl28) is an
// intermittent flake on its own, and these subprocesses turn it into a
// reliable failure. The flake is worth fixing on its own merits; making the
// whole suite red from a NEIGHBOURING file is this file's problem to avoid.
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "..");
const SCRIPT = path.join(FRONTEND, "scripts", "generate-form-manifest.ts");

async function exists(p: string) {
  return fs.access(p).then(() => true).catch(() => false);
}

/**
 * Every status a kit's metadata can present to the build, and whether that kit
 * belongs in the public bundle. Parametrized over the WHOLE dimension rather
 * than a sample: a gate that drops `draft` but keeps `unpublished` is the
 * failure mode here, and checking one status cannot see it.
 */
const CASES: Array<{ id: string; metadata: string | null; shipped: boolean; why: string }> = [
  { id: "live", metadata: '{"status":"complete","label":"Live"}', shipped: true,
    why: "published -- the one status clients may see" },
  { id: "wip", metadata: '{"status":"draft","label":"WIP"}', shipped: false,
    why: "still being written" },
  { id: "in-review", metadata: '{"status":"submitted","label":"In review"}', shipped: false,
    why: "awaiting an author; never was live" },
  { id: "retired", metadata: '{"status":"unpublished","label":"Retired"}', shipped: false,
    why: "RETIRED -- the status whose entire purpose is hiding it from clients" },
  { id: "no-status", metadata: '{"label":"No status key"}', shipped: false,
    why: "fail closed: no status is not a claim of publication" },
  { id: "no-metadata", metadata: null, shipped: false,
    why: "fail closed: absent metadata proves nothing" },
  { id: "unknown-status", metadata: '{"status":"archived","label":"Future status"}', shipped: false,
    why: "fail closed: a status this build does not know is not complete" },
];

let publicDir: string;
let manifestIds: string[];

beforeAll(async () => {
  const source = await fs.mkdtemp(path.join(os.tmpdir(), "kits-status-src-"));
  const outRoot = await fs.mkdtemp(path.join(os.tmpdir(), "kits-status-out-"));

  for (const kit of CASES) {
    const dir = path.join(source, kit.id);
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(path.join(dir, "schema.json"), '{"fields":[]}');
    await fs.writeFile(path.join(dir, "form.pdf"), "%PDF-1.7");
    if (kit.metadata !== null) {
      await fs.writeFile(path.join(dir, "metadata.json"), kit.metadata);
    }
  }

  // Root-level files: authoring material that is not a kit.
  await fs.writeFile(path.join(source, "README.md"), "# how to build a kit");
  await fs.writeFile(path.join(source, "notes.txt"), "scratch");

  publicDir = path.join(outRoot, "form-kits");

  // A STALE bundle from a previous build, seeded BEFORE the script runs. The
  // withheld kits below then prove two things at once: they are not published,
  // AND a previously-published copy of them is cleared. The wipe lives inside
  // copyKitsToPublic, which an `if (!forms.length) return` used to skip
  // (Opus fresh-eyes round 1).
  for (const kit of CASES) {
    await fs.mkdir(path.join(publicDir, kit.id), { recursive: true });
    await fs.writeFile(path.join(publicDir, kit.id, "schema.json"), '{"stale":true}');
  }
  await fs.writeFile(
    path.join(publicDir, "index.json"),
    JSON.stringify({ generatedAt: "old", forms: CASES.map((c) => ({ id: c.id })) }));
  // Drive the REAL script through tsx -- the SAME runner prebuild/predev/pretest
  // use, so this exercises the real invocation rather than a different one that
  // happens to work.
  //
  // ASYNC rather than execFileSync: a synchronous subprocess blocks this
  // worker's event loop for its whole duration, which is antisocial in a
  // parallel runner even though nothing here currently depends on it.
  await promisify(execFile)(
    process.execPath,
    [path.join(FRONTEND, "node_modules", "tsx", "dist", "cli.mjs"), SCRIPT],
    {
      env: {
        ...process.env,
        FORM_KITS_SOURCE_DIR: source,
        FORM_KITS_PUBLIC_DIR: publicDir,
      },
      cwd: FRONTEND,
    },
  );

  const manifest = JSON.parse(
    await fs.readFile(path.join(publicDir, "index.json"), "utf-8"),
  );
  manifestIds = manifest.forms.map((f: { id: string }) => f.id);
}, 120_000);

describe("the static bundle ships published kits only", () => {
  it.each(CASES)("$id ($why)", async ({ id, shipped }) => {
    expect(manifestIds.includes(id)).toBe(shipped);
    // The other half: the FILES. An index-only fix leaves the schema and PDF
    // one direct request away.
    expect(await exists(path.join(publicDir, id))).toBe(shipped);
  });

  it("ships the published kit intact -- the gate must not break the good case", async () => {
    expect(manifestIds).toEqual(["live"]);
    expect(await exists(path.join(publicDir, "live", "schema.json"))).toBe(true);
    expect(await exists(path.join(publicDir, "live", "form.pdf"))).toBe(true);
  });

  it("does not publish root-level files like the authoring README", async () => {
    // form-kits/README.md is authoring notes for whoever builds kits, and it
    // was being served at /form-kits/README.md. Only kit directories belong in
    // the bundle. Pinned because this fell out of the kit-id lookup rather
    // than being asked for -- an unpinned side effect is one refactor from
    // silently reverting (Opus fresh-eyes round 2).
    expect(await exists(path.join(publicDir, "README.md"))).toBe(false);
    expect(await exists(path.join(publicDir, "notes.txt"))).toBe(false);
  });

  it("withholds every unpublished kit's FILES, not just its index entry", async () => {
    // Stated as its own assertion because the index and the copy are separate
    // code paths in the script, and fixing one is the plausible partial fix.
    for (const kit of CASES.filter((c) => !c.shipped)) {
      expect(await exists(path.join(publicDir, kit.id))).toBe(false);
    }
  });
});

describe("a stale bundle from a previous build is cleared", () => {
  it("removes a withheld kit that WAS published in the previous build", async () => {
    // Seeded stale, must be gone -- not merely absent from the index.
    expect(await exists(path.join(publicDir, "retired"))).toBe(false);
    expect(await exists(path.join(publicDir, "wip"))).toBe(false);
  });

  it("rewrites the stale index rather than leaving it", async () => {
    const manifest = JSON.parse(
      await fs.readFile(path.join(publicDir, "index.json"), "utf-8"));
    expect(manifest.generatedAt).not.toBe("old");
    expect(manifest.forms.map((f: { id: string }) => f.id)).toEqual(["live"]);
  });
});

describe("retiring the LAST published kit empties the bundle", () => {
  /**
   * This needs its OWN script run, and that is not negotiable: the bug is in
   * the `forms.length === 0` path, and the shared fixture above always has one
   * publishable kit, so it never reaches it.
   *
   * I learned that the expensive way -- I folded this case into the shared run
   * to save a subprocess, all 12 tests stayed green, and the mutation that
   * restores the bug ALSO stayed green. Cheaper tests that cannot fail are not
   * cheaper.
   */
  it("wipes a stale bundle when EVERY kit is withheld", async () => {
    const source = await fs.mkdtemp(path.join(os.tmpdir(), "kits-empty-src-"));
    const outRoot = await fs.mkdtemp(path.join(os.tmpdir(), "kits-empty-out-"));
    const out = path.join(outRoot, "form-kits");

    const kit = path.join(source, "retired");
    await fs.mkdir(kit, { recursive: true });
    await fs.writeFile(path.join(kit, "schema.json"), '{"fields":[]}');
    await fs.writeFile(path.join(kit, "form.pdf"), "%PDF-1.7");
    await fs.writeFile(
      path.join(kit, "metadata.json"), '{"status":"unpublished","label":"Retired"}');

    await fs.mkdir(path.join(out, "retired"), { recursive: true });
    await fs.writeFile(path.join(out, "retired", "schema.json"), '{"stale":true}');
    await fs.writeFile(
      path.join(out, "index.json"),
      JSON.stringify({ generatedAt: "old", forms: [{ id: "retired" }] }));

    await promisify(execFile)(
      process.execPath,
      [path.join(FRONTEND, "node_modules", "tsx", "dist", "cli.mjs"), SCRIPT],
      { env: { ...process.env, FORM_KITS_SOURCE_DIR: source, FORM_KITS_PUBLIC_DIR: out },
        cwd: FRONTEND },
    );

    expect(await exists(path.join(out, "retired"))).toBe(false);
    const manifest = JSON.parse(await fs.readFile(path.join(out, "index.json"), "utf-8"));
    expect(manifest.forms).toEqual([]);
    expect(manifest.generatedAt).not.toBe("old");
  }, 120_000);
});
