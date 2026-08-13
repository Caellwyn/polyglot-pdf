// @ts-nocheck
import { promises as fs } from "fs";
import path from "path";

import { shouldCopyKitPath } from "./kitCopyFilter";
import { isPubliclyServable } from "./kitPublishFilter";

interface KitMetadata {
  // Declared so the status gate reads a real field rather than a stray
  // property: this interface omitting `status` is WHY the bundle shipped
  // drafts and retired forms (bd polyglot-pdf-fqexm).
  status?: string;
  label?: string;
  description?: string;
  schema?: string;
  pdf?: string;
}

interface FormKitDescriptor {
  id: string;
  label: string;
  schemaFile: string;
  schemaPath: string;
  pdfFile: string;
  pdfPath: string;
  description?: string;
}

interface ManifestPayload {
  generatedAt: string;
  forms: FormKitDescriptor[];
}

const PROJECT_ROOT = process.cwd();
const REPO_ROOT = path.resolve(PROJECT_ROOT, "..");
const FORM_KITS_SOURCE_DIR = process.env.FORM_KITS_SOURCE_DIR
  ? path.resolve(process.env.FORM_KITS_SOURCE_DIR)
  : path.resolve(REPO_ROOT, "form-kits");
// Overridable like FORM_KITS_SOURCE_DIR above, so a test can drive this
// script end to end without writing into the real public bundle. Testing
// the REAL script rather than a copy of its logic is the lesson from
// formKitBundle.archive.test.ts, where a hand-copied predicate stayed
// green under the exact bug it was written for.
const FORM_KITS_PUBLIC_DIR = process.env.FORM_KITS_PUBLIC_DIR
  ? path.resolve(process.env.FORM_KITS_PUBLIC_DIR)
  : path.resolve(PROJECT_ROOT, "public", "form-kits");
const MANIFEST_PATH = path.join(FORM_KITS_PUBLIC_DIR, "index.json");

function capitalize(word: string) {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function toTitleCase(slug: string): string {
  return slug
    .split("-")
    .map((segment) =>
      segment
        .split("_")
        .filter(Boolean)
        .map(capitalize)
        .join(" ")
    )
    .join("-")
    .trim();
}

async function pathExists(entryPath: string) {
  try {
    await fs.access(entryPath);
    return true;
  } catch {
    return false;
  }
}

async function loadMetadata(dir: string): Promise<KitMetadata | null> {
  const metadataPath = path.join(dir, "metadata.json");
  if (!(await pathExists(metadataPath))) {
    return null;
  }

  const raw = await fs.readFile(metadataPath, "utf-8");
  try {
    return JSON.parse(raw) as KitMetadata;
  } catch (error) {
    throw new Error(`Invalid JSON in ${metadataPath}: ${(error as Error).message}`);
  }
}

async function validateSourceDir() {
  if (!(await pathExists(FORM_KITS_SOURCE_DIR))) {
    throw new Error(`Form kits source directory not found at ${FORM_KITS_SOURCE_DIR}`);
  }
}

async function collectKits(): Promise<FormKitDescriptor[]> {
  const entries = await fs.readdir(FORM_KITS_SOURCE_DIR, { withFileTypes: true });
  const descriptors: FormKitDescriptor[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const kitDir = path.join(FORM_KITS_SOURCE_DIR, entry.name);
    const metadata = await loadMetadata(kitDir).catch((error) => {
      console.warn(`[form-manifest] ${error}`);
      return null;
    });

    // The lifecycle gate, FAIL CLOSED: unreadable metadata, an absent
    // metadata.json, or any status other than complete withholds the kit.
    // Shared with the copy path below so the index and the shipped files
    // cannot disagree -- an index that hides a retired form whose schema.json
    // is still served at /form-kits/<id>/ looks fixed and is not.
    if (!isPubliclyServable(metadata)) {
      console.warn(
        `[form-manifest] Withholding ${entry.name}: status ` +
        `${JSON.stringify(metadata?.status ?? null)} is not "complete"`,
      );
      continue;
    }

    const schemaFile = metadata?.schema ?? "schema.json";
    const pdfFile = metadata?.pdf ?? "form.pdf";

    const schemaPathFs = path.join(kitDir, schemaFile);
    const pdfPathFs = path.join(kitDir, pdfFile);

    if (!(await pathExists(schemaPathFs))) {
      console.warn(`[form-manifest] Skipping ${entry.name}: missing ${schemaFile}`);
      continue;
    }

    if (!(await pathExists(pdfPathFs))) {
      console.warn(`[form-manifest] Skipping ${entry.name}: missing ${pdfFile}`);
      continue;
    }

    descriptors.push({
      id: entry.name,
      label: metadata?.label ?? toTitleCase(entry.name),
      description: metadata?.description,
      schemaFile,
      schemaPath: `/form-kits/${entry.name}/${schemaFile}`,
      pdfFile,
      pdfPath: `/form-kits/${entry.name}/${pdfFile}`,
    });
  }

  return descriptors;
}

async function copyKitsToPublic(publishable: Set<string>) {
  await fs.rm(FORM_KITS_PUBLIC_DIR, { recursive: true, force: true });
  await fs.mkdir(FORM_KITS_PUBLIC_DIR, { recursive: true });
  // shouldCopyKitPath keeps <kit>/_archive/** (superseded revisions, bd
  // polyglot-pdf-w3zw) out of the PUBLIC bundle. It lives in its own module so
  // this script and its test share one definition -- see kitCopyFilter.ts.
  await fs.cp(FORM_KITS_SOURCE_DIR, FORM_KITS_PUBLIC_DIR, {
    recursive: true,
    filter: (src, dest) => {
      if (!shouldCopyKitPath(src)) {
        return false;
      }
      // fs.cp's filter sees PATHS, not metadata, so the publishable set is
      // decided once by collectKits and consulted here. Only the top level is
      // a kit id; deeper paths belong to a kit already admitted, and the root
      // itself must pass or nothing is copied at all.
      const rel = path.relative(FORM_KITS_SOURCE_DIR, src);
      if (rel === "") {
        return true;
      }
      const kitId = rel.split(path.sep)[0];
      return publishable.has(kitId);
    },
  });
}

async function writeManifest(forms: FormKitDescriptor[]) {
  const manifest: ManifestPayload = {
    generatedAt: new Date().toISOString(),
    forms,
  };

  await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n", "utf-8");
  console.log(`[form-manifest] Wrote ${forms.length} form(s) to ${path.relative(PROJECT_ROOT, MANIFEST_PATH)}`);
}

async function run() {
  await validateSourceDir();
  const forms = await collectKits();

  if (!forms.length) {
    await fs.mkdir(FORM_KITS_PUBLIC_DIR, { recursive: true });
    console.warn("[form-manifest] No form kits detected. Skipping copy + manifest generation.");
    return;
  }

  // Derived from the descriptors collectKits already admitted, NOT recomputed:
  // one gate decision, consulted twice.
  await copyKitsToPublic(new Set(forms.map((form) => form.id)));
  await writeManifest(forms);
}

run().catch((error) => {
  console.error("[form-manifest] Failed to prepare form kits", error);
  process.exitCode = 1;
});
