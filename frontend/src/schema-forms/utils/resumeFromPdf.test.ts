// @vitest-environment jsdom
//
// Reading a client's saved PDF back into a resumable form (bd dft1).
//
// Every test here builds a REAL PDF with pdf-lib and reads it back, because
// the premise is about actual bytes: a test that stubbed the PDF layer would
// pass while a client's file resumed nothing.
import { describe, it, expect } from 'vitest';
import { PDFDocument } from 'pdf-lib';

import { parseResumeStamp, readResumeFromPdf, STAMP_VERSION } from './resumeFromPdf';
import type { FormSchema } from '../types/schema';

const SCHEMA = {
  form_metadata: { form_number: 'w7', version: '3' },
  sections: [
    {
      id: 'part1',
      fields: [
        { id: 'last_name', pdf_field_name: 'f1_last' },
        { id: 'first_name', pdf_field_name: 'f1_first' },
        { id: 'agrees', pdf_field_name: 'f1_agree' },
      ],
    },
  ],
} as unknown as FormSchema;

function stampJson(over: Record<string, unknown> = {}): string {
  return JSON.stringify({ v: STAMP_VERSION, fsid: 'fss_1_abc', kit: 'w7', ...over });
}

async function buildPdf(opts: {
  stamp?: string | null;
  text?: Record<string, string>;
  checked?: string[];
}): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const page = doc.addPage();
  const form = doc.getForm();
  let y = 700;
  for (const [name, value] of Object.entries(opts.text ?? {})) {
    const f = form.createTextField(name);
    f.setText(value);
    f.addToPage(page, { x: 20, y, width: 180, height: 18 });
    y -= 30;
  }
  for (const name of opts.checked ?? []) {
    const c = form.createCheckBox(name);
    c.check();
    c.addToPage(page, { x: 20, y, width: 14, height: 14 });
    y -= 30;
  }
  if (opts.stamp !== null) {
    doc.setKeywords([opts.stamp ?? stampJson()]);
  }
  return doc.save();
}

describe('parseResumeStamp', () => {
  it('reads a well-formed stamp', () => {
    const got = parseResumeStamp(stampJson({ jtis: ['jti-a', 'jti-b'] }));
    expect(got).toEqual({
      formSessionId: 'fss_1_abc',
      kitId: 'w7',
      schemaVersion: undefined,
      linkJtis: ['jti-a', 'jti-b'],
    });
  });

  it.each([
    ['absent', undefined],
    ['empty', ''],
    ['ordinary keywords', 'immigration, w7, 2026'],
    ['not an object', '[]'],
    ['no version', '{"fsid":"fss_1_abc"}'],
    ['a FUTURE version', '{"v":999,"fsid":"fss_1_abc"}'],
    ['no session id', '{"v":1}'],
  ])('declines %s rather than throwing', (_label, raw) => {
    expect(parseResumeStamp(raw as string | undefined)).toBeNull();
  });

  it.each([
    '../../../etc/passwd',
    'fss/../secret',
    'CON',
    'com1',
    'trailing.',
    '...',
  ])('refuses the hostile session id %s', (hostile) => {
    // This id would become THIS session's identity and be sent onward to a
    // backend that names a FILE from it. Refuse before adopting it.
    expect(parseResumeStamp(JSON.stringify({ v: STAMP_VERSION, fsid: hostile }))).toBeNull();
  });
});

describe('readResumeFromPdf', () => {
  it('restores the client ANSWERS and their identity from one file', async () => {
    const bytes = await buildPdf({
      text: { f1_last: 'Okonkwo', f1_first: 'Adaeze' },
      checked: ['f1_agree'],
    });

    const got = await readResumeFromPdf(bytes, SCHEMA);

    expect(got).not.toBeNull();
    expect(got!.stamp.formSessionId).toBe('fss_1_abc');
    expect(got!.fieldValues).toEqual({
      last_name: 'Okonkwo',
      first_name: 'Adaeze',
      agrees: 'true',
    });
  });

  it('maps PDF widget names to SCHEMA field ids, not to themselves', async () => {
    // The two namespaces differ. Restoring under the PDF's own name would put
    // every answer on a field the form does not have.
    const bytes = await buildPdf({ text: { f1_last: 'Okonkwo' } });
    const got = await readResumeFromPdf(bytes, SCHEMA);
    expect(Object.keys(got!.fieldValues)).toEqual(['last_name']);
  });

  it('reports PDF fields the schema does not know, without dropping the rest', async () => {
    const bytes = await buildPdf({
      text: { f1_last: 'Okonkwo', f1_mystery: 'from an older revision' },
    });
    const got = await readResumeFromPdf(bytes, SCHEMA);
    expect(got!.fieldValues).toEqual({ last_name: 'Okonkwo' });
    expect(got!.unmatchedPdfFields).toContain('f1_mystery');
  });

  it('returns null for a readable PDF that is not one of ours', async () => {
    // A different message to the client: "this does not look like a saved
    // form", not "we could not read that file".
    const bytes = await buildPdf({ stamp: null, text: { f1_last: 'Okonkwo' } });
    expect(await readResumeFromPdf(bytes, SCHEMA)).toBeNull();
  });

  it('skips EMPTY fields rather than restoring blanks over real answers', async () => {
    const bytes = await buildPdf({ text: { f1_last: 'Okonkwo', f1_first: '' } });
    const got = await readResumeFromPdf(bytes, SCHEMA);
    expect(got!.fieldValues).toEqual({ last_name: 'Okonkwo' });
  });

  it('reads an UNCHECKED box as absent, not as false', async () => {
    const doc = await PDFDocument.create();
    const page = doc.addPage();
    const form = doc.getForm();
    const c = form.createCheckBox('f1_agree');   // left unchecked
    c.addToPage(page, { x: 20, y: 700, width: 14, height: 14 });
    doc.setKeywords([stampJson()]);

    const got = await readResumeFromPdf(await doc.save(), SCHEMA);
    expect('agrees' in got!.fieldValues).toBe(false);
  });

  it('rejects a file that is not a PDF at all', async () => {
    await expect(
      readResumeFromPdf(new TextEncoder().encode('this is a photo'), SCHEMA),
    ).rejects.toBeTruthy();
  });
});
