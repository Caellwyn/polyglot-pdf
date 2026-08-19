/**
 * The static form-kit bundle must ship PUBLIC kits only (bd polyglot-pdf-kkos,
 * closing the bd polyglot-pdf-17opi exposure).
 *
 * The firm tier (bd polyglot-pdf-vccy) made kit visibility firm-scoped on
 * every backend read -- but the frontend build still copied every COMPLETE
 * kit into the world-readable Firebase Hosting bundle, so a firm's private
 * kit's schema (field ids, labels, pdf mappings) and blank PDF were one
 * direct request away for anyone, defeating the 404s the routes enforce.
 *
 * These tests run the REAL build script against a temp tree (the
 * formKitBundle.status.test.ts harness -- a hand-copied predicate once stayed
 * green under the exact bug it named). BOTH halves are asserted per case: the
 * index AND the shipped files.
 *
 * The visibility dimension is parametrized WHOLE, not sampled: the gate
 * withholds on ANYTHING except an absent key or the exact string "public" --
 * deliberately stricter than the backend routes' anything-but-"private"
 * coercion, because this surface's failure direction is an irreversible
 * public leak, not a reversible service break (see kitPublishFilter.ts).
 */
import { describe, expect, it, beforeAll } from "vitest";

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
 * Every visibility a COMPLETE kit's metadata can present, and whether that
 * kit belongs in the public bundle. Mutation targets: revert the visibility
 * gate in isPubliclyServable entirely -- every withheld row goes red; weaken
 * it to `!== "private"` (the backend's coercion) -- the typo/case/null rows
 * go red.
 */
const CASES: Array<{ id: string; metadata: string; shipped: boolean; why: string }> = [
  { id: "legacy-public", metadata: '{"status":"complete","label":"Legacy"}', shipped: true,
    why: "no visibility key -- existing kits are public by absence" },
  { id: "explicit-public",
    metadata: '{"status":"complete","label":"Public","visibility":"public"}', shipped: true,
    why: "explicitly public" },
  { id: "private-kit",
    metadata: '{"status":"complete","label":"Private","visibility":"private","owner_firm_id":"firm-a"}',
    shipped: false,
    why: "a firm's PRIVATE kit -- the 17opi exposure this gate closes" },
  { id: "case-variant",
    metadata: '{"status":"complete","label":"Case","visibility":"Private"}', shipped: false,
    why: "fail closed: a case variant is not demonstrably public" },
  { id: "typo-private",
    metadata: '{"status":"complete","label":"Typo","visibility":"prvate"}', shipped: false,
    why: "fail closed: a typo INTENDING private must not ship publicly" },
  { id: "null-visibility",
    metadata: '{"status":"complete","label":"Null","visibility":null}', shipped: false,
    why: "fail closed: JSON null is present-but-not-public" },
  { id: "draft-private",
    metadata: '{"status":"draft","label":"DraftPrivate","visibility":"private"}', shipped: false,
    why: "the exit criterion's seeded pair: BOTH gates withhold it" },
];

let publicDir: string;
let manifestIds: string[];

beforeAll(async () => {
  const source = await fs.mkdtemp(path.join(os.tmpdir(), "kits-vis-src-"));
  const outRoot = await fs.mkdtemp(path.join(os.tmpdir(), "kits-vis-out-"));

  for (const kit of CASES) {
    const dir = path.join(source, kit.id);
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(path.join(dir, "schema.json"), '{"fields":[]}');
    await fs.writeFile(path.join(dir, "form.pdf"), "%PDF-1.7");
    await fs.writeFile(path.join(dir, "metadata.json"), kit.metadata);
  }

  publicDir = path.join(outRoot, "form-kits");

  // A STALE bundle seeded BEFORE the script runs: the private kit was
  // "published" by a pre-kkos build. The withheld rows then prove both that
  // they are not published AND that a previously-shipped copy is cleared.
  for (const kit of CASES) {
    await fs.mkdir(path.join(publicDir, kit.id), { recursive: true });
    await fs.writeFile(path.join(publicDir, kit.id, "schema.json"), '{"stale":true}');
  }
  await fs.writeFile(
    path.join(publicDir, "index.json"),
    JSON.stringify({ generatedAt: "old", forms: CASES.map((c) => ({ id: c.id })) }));

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

describe("the static bundle ships public kits only", () => {
  it.each(CASES)("$id ($why)", async ({ id, shipped }) => {
    expect(manifestIds.includes(id)).toBe(shipped);
    // The other half: the FILES. An index-only fix leaves the schema and PDF
    // one direct request away.
    expect(await exists(path.join(publicDir, id))).toBe(shipped);
  });

  it("the shipped set is exactly the public complete kits (derived, not retyped)", () => {
    expect([...manifestIds].sort())
      .toEqual(CASES.filter((c) => c.shipped).map((c) => c.id).sort());
  });
});
