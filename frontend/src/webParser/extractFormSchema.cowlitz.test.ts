// @ts-nocheck - TODO: Update tests to use current FormSchema format (id not fieldId, no label property)
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
  'Cowlitz Family Health Center - Nurse Practitioner Application.html',
);

describe('extractFormSchema – Cowlitz Family Health Center application', () => {
  it('should detect fields from JavaScript-rendered forms', () => {
    const html = readFileSync(fixturePath, 'utf-8');
    const dom = new JSDOM(html, {
      url: 'https://recruiting.paylocity.com/Recruiting/Jobs/Apply/3612061',
    });

    const schema = extractFormSchema(dom.window.document, {
      url: dom.window.location.href,
      title: 'Nurse Practitioner Application',
    });

    console.log('Found fields:', schema.fields.length);
    console.log('Field IDs:', schema.fields.map(f => f.fieldId));
    
    // Expected fields based on "fields to find.txt":
    // Information section
    expect(schema.fields.some(f => f.label?.includes('First Name'))).toBe(true);
    expect(schema.fields.some(f => f.label?.includes('Last') && f.label?.includes('Name'))).toBe(true);
    expect(schema.fields.some(f => f.label?.includes('Email'))).toBe(true);
    expect(schema.fields.some(f => f.label?.includes('Mobile') || f.label?.includes('Cell'))).toBe(true);
    expect(schema.fields.some(f => f.label?.includes('Home Phone'))).toBe(true);
    
    // Radio button group with options
    const radioField = schema.fields.find(f => f.fieldId === 'info.howDidYouHearAboutUs');
    expect(radioField).toBeDefined();
    expect(radioField?.type).toBe('radio');
    expect(radioField?.label).toBe('How did you hear about us?');
    expect(radioField?.options).toBeDefined();
    expect(radioField?.options?.length).toBeGreaterThan(1);
    expect(radioField?.options).toContain('Indeed');
    expect(radioField?.options).toContain('LinkedIn');
    
    // Should NOT include cookie consent fields
    expect(schema.fields.some(f => f.fieldId?.includes('ot-group'))).toBe(false);
    expect(schema.fields.some(f => f.label?.includes('Targeting Cookies'))).toBe(false);
    expect(schema.fields.some(f => f.label?.includes('Performance Cookies'))).toBe(false);
  });
});
