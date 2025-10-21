// @ts-nocheck - TODO: Update tests to use current FormSchema format
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { JSDOM } from 'jsdom';

import { extractFormSchema } from './extractFormSchema';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const fixturePath = join(
  __dirname,
  '..',
  '..',
  '..',
  'example_webforms',
  'DAISY Award Nomination _ PeaceHealth.html',
);

describe('extractFormSchema – Daisy Award nomination page', () => {
  it('prints the normalized schema for manual inspection', () => {
    const html = readFileSync(fixturePath, 'utf-8');
    const dom = new JSDOM(html, {
      url: 'https://www.peacehealth.org/about-peacehealth/recognize-a-caregiver/daisy-award',
    });
    const schema = extractFormSchema(dom.window.document, {
      url: dom.window.location.href,
      title: dom.window.document.title,
    });

    // eslint-disable-next-line no-console
    console.log('Daisy Award schema JSON:\n', JSON.stringify(schema, null, 2));

    expect(schema.fields.length).toBeGreaterThan(0);
  });
});
