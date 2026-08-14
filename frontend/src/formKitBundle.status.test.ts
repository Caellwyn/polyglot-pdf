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
  { id: "custom-names",
    metadata: '{"status":"complete","label":"Custom","schema":"n400.json","pdf":"n400.pdf"}',
    shipped: true,
    why: "published, but names its schema and PDF itself" },
  { id: "nested-name",
    metadata: '{"status":"complete","label":"Nested","schema":"sub/schema.json"}',
    shipped: true,
    why: "declares a NESTED schema -- coerced to the conventional name" },
  { id: "traversing-name",
    metadata: '{"status":"complete","label":"Traversal","schema":"../secret.json"}',
    shipped: true,
    why: "declares a TRAVERSING schema -- coerced, never escapes the kit" },
  { id: "charset-name",
    metadata: '{"status":"complete","label":"Charset","schema":"archive$secret.json"}',
    shipped: true,
    why: "declares a name only the CHARSET rule rejects -- no underscore, no slash" },
  { id: "spacey-name",
    metadata: '{"status":"complete","label":"Spacey","schema":"real schema.json"}',
    shipped: true,
    why: "declares a name with a SPACE -- fallback must not serve stale bytes silently" },
  { id: "pdf-unsafe",
    metadata: '{"status":"complete","label":"PdfUnsafe","pdf":"real form.pdf"}',
    shipped: true,
    why: "declares an unsafe PDF -- the coercion's OTHER half, which was unpinned" },
  { id: "dirtrap",
    metadata: '{"status":"complete","label":"DirTrap","pdf":"assets"}',
    shipped: true,
    why: "its declared pdf name is also a real DIRECTORY -- only the depth check refuses its contents" },
];

let publicDir: string;
let manifestIds: string[];
let buildStderr: string;

beforeAll(async () => {
  const source = await fs.mkdtemp(path.join(os.tmpdir(), "kits-status-src-"));
  const outRoot = await fs.mkdtemp(path.join(os.tmpdir(), "kits-status-out-"));

  for (const kit of CASES) {
    const dir = path.join(source, kit.id);
    await fs.mkdir(dir, { recursive: true });
    if (kit.id === "custom-names") {
      // Declares its own filenames.
      await fs.writeFile(path.join(dir, "n400.json"), '{"fields":[]}');
      await fs.writeFile(path.join(dir, "n400.pdf"), "%PDF-1.7");
      // ...and ALSO carries an authoring leftover named schema.json, which is
      // another kit's legitimate asset. This is what separates a per-kit
      // allowlist from a global union of every kit's allowed names: under a
      // union this file ships, and every test still passed (Opus fresh-eyes
      // round 1 proved exactly that).
      await fs.writeFile(path.join(dir, "schema.json"), '{"leftover":true}');
    } else if (kit.id === "dirtrap") {
      // Its declared pdf name is ALSO a real directory. The basename must BE
      // an allowed filename exactly for the exploit to reproduce -- my first
      // attempt used `form.pdf.d`, which is not allowlisted, so the mutation
      // survived anyway (Opus round 5, and my own first fix for it).
      await fs.mkdir(path.join(dir, "assets"), { recursive: true });
      await fs.writeFile(path.join(dir, "assets", "assets"), "%PDF-nested");
      await fs.writeFile(path.join(dir, "schema.json"), '{"fields":[]}');
      await fs.writeFile(path.join(dir, "form.pdf"), "%PDF-1.7");
    } else if (kit.id === "pdf-unsafe") {
      // Declares an unsafe PDF name that EXISTS on disk. schema/pdf coercion is
      // written as a symmetric pair, but only the schema half was pinned --
      // reverting the pdf half alone left 35/35 green (Opus round 5).
      await fs.writeFile(path.join(dir, "real form.pdf"), "%PDF-DECLARED");
      await fs.writeFile(path.join(dir, "schema.json"), '{"fields":[]}');
      await fs.writeFile(path.join(dir, "form.pdf"), "%PDF-CONVENTIONAL");
    } else if (kit.id === "charset-name" || kit.id === "spacey-name") {
      // The declared file EXISTS on disk, so nothing but the charset rule
      // stops it shipping. The conventional fallback carries different content
      // so serving the wrong one is visible.
      const declared = kit.id === "charset-name" ? "archive$secret.json" : "real schema.json";
      await fs.writeFile(path.join(dir, declared), '{"DECLARED_SECRET":true}');
      await fs.writeFile(path.join(dir, "schema.json"), '{"fields":[],"conventional":true}');
      await fs.writeFile(path.join(dir, "form.pdf"), "%PDF-1.7");
    } else {
      await fs.writeFile(path.join(dir, "schema.json"), '{"fields":[]}');
      await fs.writeFile(path.join(dir, "form.pdf"), "%PDF-1.7");
    }
    if (kit.metadata !== null) {
      await fs.writeFile(path.join(dir, "metadata.json"), kit.metadata);
    }
  }

  // Inside the PUBLISHED kit: the internal working files that were being served
  // at guessable paths (bd polyglot-pdf-983wp). Named after the real ones.
  await fs.writeFile(path.join(source, "live", "schema_archived.json"), '{"old":true}');
  await fs.writeFile(path.join(source, "live", "live_schema_backup.json"), '{"bak":true}');
  await fs.writeFile(path.join(source, "live", "migration_report.json"), '{"rep":true}');
  await fs.writeFile(path.join(source, "live", "live-annotated.pdf"), "%PDF-annot");
  await fs.writeFile(path.join(source, "live", "live-instructions.pdf"), "%PDF-instr");

  // Inside the PUBLISHED kit: the underscore-excluded surfaces. These ride the
  // same script run so the COMPOSED filter is pinned, not just its status half
  // (Opus fresh-eyes round 3).
  await fs.mkdir(path.join(source, "live", "_archive", "12-2024"), { recursive: true });
  await fs.writeFile(
    path.join(source, "live", "_archive", "12-2024", "schema.json"), '{"superseded":true}');
  // A kit-shaped directory whose name starts with "_": it has a complete
  // metadata.json, so the STATUS gate would admit it and the allowlist would
  // then ship its schema/pdf. ONLY shouldCopyKitPath refuses it. This is the
  // separator my first attempt missed -- a file under <kit>/_archive is
  // already excluded by the depth check, so deleting the underscore guard
  // stayed invisible (Opus fresh-eyes round 2, and my own first fix for it).
  await fs.mkdir(path.join(source, "_staging"), { recursive: true });
  await fs.writeFile(path.join(source, "_staging", "schema.json"), '{"fields":[]}');
  await fs.writeFile(path.join(source, "_staging", "form.pdf"), "%PDF-1.7");
  await fs.writeFile(
    path.join(source, "_staging", "metadata.json"),
    '{"status":"complete","label":"Staging"}');
  await fs.mkdir(path.join(source, "_translation"), { recursive: true });
  await fs.writeFile(path.join(source, "_translation", "es.json"), '{"hola":true}');

  // A DIRECTORY whose basename is an allowed filename, inside the published
  // kit. Only the depth check refuses its contents: a basename-only match
  // admits the dir (form.pdf is allowlisted) and then admits allow-named
  // children at any depth. That mutation left 35/35 green (Opus round 5).
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
  const run = await promisify(execFile)(
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
  // Captured so the coercion WARNING is observable. It was added because
  // silent coercion served stale bytes with a clean build log -- and the fix
  // for a silent-diagnostic bug was itself unobservable, deletable with no
  // signal (Opus round 5).
  buildStderr = run.stderr.toString();

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
    // DERIVED from CASES, not retyped: this literal needed hand-editing every
    // time a case was added, which is the drift that lets a list claim more
    // coverage than it has.
    // `_staging` is excluded: it is a fixture for the underscore guard, not a
    // CASES row, and it is currently indexed (bd polyglot-pdf-v3suc).
    expect([...manifestIds].filter((id) => !id.startsWith("_")).sort())
      .toEqual(CASES.filter((c) => c.shipped).map((c) => c.id).sort());
    expect(await exists(path.join(publicDir, "live", "schema.json"))).toBe(true);
    expect(await exists(path.join(publicDir, "live", "form.pdf"))).toBe(true);
  });

  it("prunes an underscore dir the STATUS gate and ALLOWLIST would both admit", async () => {
    // _staging is a complete, schema-and-PDF-bearing kit by every other rule:
    // the status gate admits it, and the allowlist would ship its three files.
    // Only shouldCopyKitPath refuses it.
    //
    // This exists because the allowlist made the underscore guard's other
    // tests VACUOUS -- deleting the guard left all 29 green, since the
    // allowlist blocks <kit>/_archive for a different reason and the DEPTH
    // check blocks anything under it. A guard whose deletion is invisible is
    // one refactor from being deleted as dead code.
    expect(await exists(path.join(publicDir, "_staging"))).toBe(false);
    // NOT asserting it is absent from the index: the underscore rule is
    // applied to the COPY only, so an underscore kit is currently INDEXED and
    // unshipped -- the same index/copy split fqexm fixed for status, still
    // live for underscores. Pre-existing (reproduces on origin/dev), filed as
    // bd polyglot-pdf-v3suc. Pinning the copy half here is this bead's scope;
    // pinning the index half would fail today and belongs to that bead.
  });

  it("still prunes _archive inside a PUBLISHED kit", async () => {
    // This diff turned `filter: shouldCopyKitPath` into a hand-composed lambda.
    // formKitBundle.archive.test.ts drives the PREDICATE through its own fs.cp,
    // so after that change it proved the predicate correct but no longer proved
    // the SCRIPT still calls it -- deleting the underscore guard left all 17
    // tests green while republishing every superseded schema to Hosting
    // (Opus fresh-eyes round 3, verified by mutation).
    //
    // <kit>/_archive holds operator-only superseded revisions; Hosting would
    // serve them at /form-kits/<kit>/_archive/<marker>/schema.json.
    expect(await exists(path.join(publicDir, "live", "_archive"))).toBe(false);
    expect(await exists(path.join(publicDir, "_translation"))).toBe(false);
  });

  it("still prunes _archive when the underscore rule is scoped WRONG", async () => {
    // The subtler drift the kitCopyFilter docstring warns about: a filter
    // scoped to the TOP level only still looks correct and still leaks a
    // NESTED _archive. Asserting the nested path specifically is what
    // separates the two.
    expect(await exists(
      path.join(publicDir, "live", "_archive", "12-2024", "schema.json"))).toBe(false);
  });

  it.each([
    ["schema_archived.json", "a superseded revision -- the archive keeps these behind auth"],
    ["live_schema_backup.json", "a superseded revision under an ordinary name"],
    ["migration_report.json", "an authoring artifact"],
    ["live-annotated.pdf", "an authoring artifact"],
    ["live-instructions.pdf", "an EDITOR-side input for booklet extraction"],
  ])("a published kit does not ship %s (%s)", async (file) => {
    // These carry ORDINARY names, which is why bd polyglot-pdf-w3zw's
    // underscore rule never caught them. Enumerated one per case so a
    // regression names the file it leaked.
    expect(await exists(path.join(publicDir, "live", file))).toBe(false);
  });

  it("ships EXACTLY the two files a client fetches, and nothing else", async () => {
    // The allowlist stated as a complete set rather than five absences: a
    // denylist is one new filename away from leaking again, so assert what IS
    // published, not what is not.
    const shipped = (await fs.readdir(path.join(publicDir, "live"))).sort();
    expect(shipped).toEqual(["form.pdf", "schema.json"]);
  });

  it.each([
    ["charset-name", "archive$secret.json"],
    ["spacey-name", "real schema.json"],
  ])("%s: a declared name failing the CHARSET rule never ships (%s)", async (id, declared) => {
    // Both names are refused ONLY by the charset rule: no leading underscore
    // (the underscore guard's job), no slash or '..' (the traversal guard's).
    // Deleting the charset rule left 30/30 green while the declared file was
    // republished AND indexed -- once coerced past, the allowlist CONTAINS the
    // name, so it admits it.
    //
    // The first version of this fixture used "_archive_secret.json", which the
    // UNDERSCORE guard excluded before the charset rule was ever consulted --
    // so its leak assertion could not fail, and the comment claiming otherwise
    // was wrong. Second time in this bead I picked a fixture excluded for the
    // wrong reason (Opus fresh-eyes rounds 3 and 4). The test for a rule must
    // be refused by THAT rule and no other.
    expect(await exists(path.join(publicDir, id, declared))).toBe(false);
    const shipped = (await fs.readdir(path.join(publicDir, id))).sort();
    expect(shipped).toEqual(["form.pdf", "schema.json"]);
  });

  it("serves the CONVENTIONAL bytes when a declared name is refused", async () => {
    // The fallback must not silently serve different content than the manifest
    // implies. Assert the actual bytes, not just the filename.
    const served = JSON.parse(await fs.readFile(
      path.join(publicDir, "spacey-name", "schema.json"), "utf-8"));
    expect(served.conventional).toBe(true);
    expect(served.DECLARED_SECRET).toBeUndefined();
  });

  it("does NOT let one kit serve another kit's allowed filename", async () => {
    // The per-kit half of the allowlist -- the entire reason `publishable` is a
    // Map rather than a Set. custom-names carries an authoring leftover named
    // schema.json, which IS a legitimate name for a different kit. A global
    // union allowlist ships it and every other test stays green (proved in
    // round 1), so this is the only assertion that separates the two.
    expect(await exists(path.join(publicDir, "custom-names", "schema.json"))).toBe(false);
    // ...while the kit that legitimately declares it still ships it.
    expect(await exists(path.join(publicDir, "live", "schema.json"))).toBe(true);
  });

  it.each([
    ["nested-name", "sub/schema.json"],
    ["traversing-name", "../secret.json"],
  ])("coerces %s's unsafe declared schema (%s) to the conventional name", async (id) => {
    // Accepting the declared name verbatim split the two halves of the script:
    // the manifest pointed at the declared path while the copy filter refused
    // it, so the kit was LISTED and had no schema -- a silent per-form outage
    // (round 1, reproduced). Coercion happens once, before both.
    const shipped = (await fs.readdir(path.join(publicDir, id))).sort();
    expect(shipped).toContain("schema.json");
    const entry = manifestIds.includes(id);
    expect(entry).toBe(true);
  });

  it("never emits a manifest path that escapes the kit directory", async () => {
    // "../secret.json" normalises to /form-kits/secret.json -- outside the kit.
    // The backend coerces this in safe_filename for the same reason; the
    // frontend had no equivalent.
    const manifest = JSON.parse(
      await fs.readFile(path.join(publicDir, "index.json"), "utf-8"));
    for (const form of manifest.forms) {
      expect(form.schemaPath).not.toContain("..");
      expect(form.pdfPath).not.toContain("..");
      expect(form.schemaPath.startsWith(`/form-kits/${form.id}/`)).toBe(true);
    }
  });

  it("follows a kit's OWN declared schema and pdf names", async () => {
    // The allowlist is per-kit, taken from that kit's metadata. Hardcoding
    // schema.json/form.pdf would withhold the only files a custom-named kit
    // has -- publishing an empty directory and a manifest pointing at nothing.
    const shipped = (await fs.readdir(path.join(publicDir, "custom-names"))).sort();
    expect(shipped).toEqual(["n400.json", "n400.pdf"]);
  });

  it("does not publish metadata.json -- it carries editor-internal state", async () => {
    // No client fetches it (the manifest already embeds label and
    // description), and the editor writes a `readiness` block and an
    // `editing_lock` into it -- review counts and who holds the kit, served to
    // anonymous clients at a guessable path. The allowlist that exists to stop
    // exactly this was admitting it (Opus round 5).
    for (const id of ["live", "custom-names"]) {
      expect(await exists(path.join(publicDir, id, "metadata.json"))).toBe(false);
    }
  });

  it("coerces an unsafe declared PDF, not just an unsafe schema", async () => {
    // The coercion is written as a symmetric pair and only the schema half
    // could fail; reverting the pdf half alone left every test green.
    const shipped = (await fs.readdir(path.join(publicDir, "pdf-unsafe"))).sort();
    expect(shipped).toEqual(["form.pdf", "schema.json"]);
    expect(await exists(path.join(publicDir, "pdf-unsafe", "real form.pdf"))).toBe(false);
    // ...and the manifest points at the coerced name, so index and bundle agree.
    const manifest = JSON.parse(
      await fs.readFile(path.join(publicDir, "index.json"), "utf-8"));
    const entry = manifest.forms.find((f: { id: string }) => f.id === "pdf-unsafe");
    expect(entry.pdfPath).toBe("/form-kits/pdf-unsafe/form.pdf");
  });

  it("refuses the CONTENTS of a directory whose name is an allowed file", async () => {
    // The depth check, which the allowlist alone cannot enforce. `dirtrap`
    // declares its pdf as "assets" and also has a real `assets/` directory:
    // a basename-only match admits that directory (its name IS allowlisted)
    // and then its allow-named children at any depth.
    expect(await exists(path.join(publicDir, "dirtrap", "assets", "assets"))).toBe(false);
  });

  it("WARNS when a declared filename is refused", async () => {
    // The fix for a silent-diagnostic bug must itself be observable.
    expect(buildStderr).toMatch(/spacey-name: declared schema .* not a safe bare filename/);
    expect(buildStderr).toMatch(/pdf-unsafe: declared pdf .* not a safe bare filename/);
    // ...and stays quiet for a kit that declares nothing unsafe.
    expect(buildStderr).not.toMatch(/custom-names: declared/);
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

  it("wipes a withheld kit that the PREVIOUS build had published", async () => {
    // Not a restatement of the it.each above: those would pass vacuously in a
    // fresh output dir. The fixture pre-seeds every kit as if a previous build
    // had published it, so this can only pass if the wipe actually ran -- the
    // round-1 bug. (The earlier version of this test re-asserted the copy half
    // and could not fail independently; round 3 caught that.)
    for (const kit of CASES.filter((c) => !c.shipped)) {
      expect(await exists(path.join(publicDir, kit.id, "schema.json"))).toBe(false);
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
    expect(manifest.forms.map((f: { id: string }) => f.id)
      .filter((id: string) => !id.startsWith("_")).sort())
      .toEqual(CASES.filter((c) => c.shipped).map((c) => c.id).sort());
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
