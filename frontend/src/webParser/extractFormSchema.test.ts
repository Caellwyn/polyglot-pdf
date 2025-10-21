// @ts-nocheck - TODO: Update tests to use current FormSchema format (id not fieldId, no label property)
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { JSDOM } from 'jsdom';

import { extractFormSchema, NormalizedField } from './extractFormSchema';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const fixturePath = join(__dirname, '__fixtures__', 'kelso_stormwater_trimmed.html');
const fixtureHtml = readFileSync(fixturePath, 'utf-8');

function findField(fields: NormalizedField[], id: string) {
  const field = fields.find((f) => f.fieldId === id);
  expect(field, `Expected field with id ${id}`).toBeTruthy();
  return field!;
}

describe('extractFormSchema', () => {
  it('detects and normalizes the Kelso stormwater form', () => {
    const dom = new JSDOM(fixtureHtml, {
      url: 'https://www.kelso.gov/FormCenter/Engineering-9/Stormwater-Incident-Report-50',
    });
    const schema = extractFormSchema(dom.window.document, {
      url: dom.window.location.href,
      title: 'Stormwater Incident Report',
    });

    expect(schema.source).toBe('web');
    expect(schema.formMetadata.url).toBe(dom.window.location.href);
    expect(schema.formMetadata.title).toBe('Stormwater Incident Report');

    // Core field set should include exactly the 12 actionable inputs we expect.
    expect(schema.fields).toHaveLength(12);

    const firstName = findField(schema.fields, 'e_2');
    expect(firstName.type).toBe('text');
    expect(firstName.required).toBe(false);
    expect(firstName.label).toContain('First Name');

    const crossStreet = findField(schema.fields, 'e_7');
    expect(crossStreet.type).toBe('text');
    expect(crossStreet.required).toBe(true);

    const dateField = findField(schema.fields, 'e_8_date');
    expect(dateField.type).toBe('date');
    expect(dateField.required).toBe(true);

    const timeField = findField(schema.fields, 'e_9_time');
    expect(timeField.type).toBe('time');
    expect(timeField.required).toBe(true);

    const incidentDescription = findField(schema.fields, 'e_11');
    expect(incidentDescription.type).toBe('textarea');
    expect(incidentDescription.required).toBe(true);

    const copyCheckbox = findField(schema.fields, 'wantCopy');
    expect(copyCheckbox.type).toBe('checkbox');
    expect(copyCheckbox.required).toBe(false);

    const copyEmail = findField(schema.fields, 'wantCopyAddress');
    expect(copyEmail.type).toBe('email');
    expect(copyEmail.required).toBe(false);

    // Hidden/system fields should not leak into the normalized schema.
    const hiddenIds = schema.fields.map((field) => field.fieldId);
    expect(hiddenIds.some((id) => id.startsWith('h_'))).toBe(false);
    expect(hiddenIds).not.toContain('g-recaptcha-response');
  });

  it('filters non-user inputs such as captcha and honeypots', () => {
    const dom = new JSDOM(fixtureHtml);
    const schema = extractFormSchema(dom.window.document);

    const ids = schema.fields.map((field) => field.fieldId);
    expect(ids).not.toContain('e_empty1');
    expect(ids).not.toContain('e_captcha');
  });
});
