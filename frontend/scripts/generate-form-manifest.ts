// @ts-nocheck
import { promises as fs } from "fs";
import path from "path";

interface KitMetadata {
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
const FORM_KITS_PUBLIC_DIR = path.resolve(PROJECT_ROOT, "public", "form-kits");
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

async function copyKitsToPublic() {
  await fs.rm(FORM_KITS_PUBLIC_DIR, { recursive: true, force: true });
  await fs.mkdir(FORM_KITS_PUBLIC_DIR, { recursive: true });
  await fs.cp(FORM_KITS_SOURCE_DIR, FORM_KITS_PUBLIC_DIR, { recursive: true });
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

  await copyKitsToPublic();
  await writeManifest(forms);
}

run().catch((error) => {
  console.error("[form-manifest] Failed to prepare form kits", error);
  process.exitCode = 1;
});
