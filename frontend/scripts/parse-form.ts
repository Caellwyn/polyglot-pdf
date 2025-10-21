import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

import { extractFormSchema } from "../src/webParser/extractFormSchema";

function printUsage(): void {
  console.error("Usage: npm run parse -- <path-to-html-file> [--url <page-url>] [--title <page-title>]");
}

function isFlag(value: string | undefined): value is string {
  return typeof value === "string" && value.startsWith("--");
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    printUsage();
    process.exit(1);
  }

  const params: { file?: string; url?: string; title?: string } = {};

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];

    if (!params.file && !isFlag(arg)) {
      params.file = arg;
      continue;
    }

    if (arg === "--url") {
      const value = args[i + 1];
      if (!value || isFlag(value)) {
        console.error("Missing value for --url");
        process.exit(1);
      }
      params.url = value;
      i += 1;
      continue;
    }

    if (arg === "--title") {
      const value = args[i + 1];
      if (!value || isFlag(value)) {
        console.error("Missing value for --title");
        process.exit(1);
      }
      params.title = value;
      i += 1;
      continue;
    }

    console.error(`Unknown argument: ${arg}`);
    printUsage();
    process.exit(1);
  }

  if (!params.file) {
    console.error("Missing HTML file path.");
    printUsage();
    process.exit(1);
  }

  const isRemote = params.file.startsWith("http://") || params.file.startsWith("https://");
  const htmlPath = isRemote ? params.file : resolve(process.cwd(), params.file);

  let html: string;
  if (isRemote) {
    const response = await fetch(htmlPath);
    if (!response.ok) {
      console.error(`Failed to download ${htmlPath}: ${response.status} ${response.statusText}`);
      process.exit(1);
    }
    html = await response.text();
  } else {
    html = readFileSync(htmlPath, "utf-8");
  }

  const fallbackUrl = isRemote ? htmlPath : pathToFileURL(htmlPath).href;
  const dom = new JSDOM(html, {
    url: params.url ?? fallbackUrl,
  });

  const schema = extractFormSchema(dom.window.document, {
    url: params.url ?? dom.window.location.href,
    title: params.title ?? dom.window.document.title,
  });

  process.stdout.write(`${JSON.stringify(schema, null, 2)}\n`);
}

main().catch((err) => {
  console.error("Failed to parse form:", err);
  process.exit(1);
});

