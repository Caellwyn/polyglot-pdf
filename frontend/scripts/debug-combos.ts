import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const path = process.argv[2];
if (!path) {
  console.error('Usage: node scripts/debug-combos.ts <html-file>');
  process.exit(1);
}

const html = readFileSync(path, 'utf-8');
const dom = new JSDOM(html, { url: 'https://example.com' });
const document = dom.window.document;

const comboSelectors = '[role="combobox"], button[aria-haspopup="listbox"], div[role="listbox"], div[data-automation-id="select"]';
const combos = Array.from(document.querySelectorAll(comboSelectors));
console.log('combos', combos.length);
for (const el of combos) {
  const labelId = el.getAttribute('aria-labelledby');
  let labelText = el.getAttribute('aria-label') || '';
  if (!labelText && labelId) {
    const labelNode = document.getElementById(labelId);
    if (labelNode) labelText = labelNode.textContent.trim();
  }
  if (!labelText) {
    const label = el.closest('[data-automation-id]')?.querySelector('label');
    if (label) labelText = label.textContent.trim();
  }
  console.log({
    tag: el.tagName,
    id: el.id,
    class: el.getAttribute('class'),
    name: el.getAttribute('name'),
    label: labelText,
    text: el.textContent.trim().slice(0, 100)
  });
}
