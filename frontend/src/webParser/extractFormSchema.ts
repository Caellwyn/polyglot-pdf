import { enhanceField } from './formEnhancements';
import type { FormSchema } from '../webFormState';

export interface ExtractFormSchemaOptions {
  url?: string;
  title?: string;
}

export type FieldType =
  | 'text'
  | 'textarea'
  | 'checkbox'
  | 'radio'
  | 'select'
  | 'date'
  | 'time'
  | 'email'
  | 'tel'
  | 'number';

/**
 * Extract form schema from DOM and return in FormSchema format.
 * This is the unified schema format used throughout the application.
 */
export function extractFormSchema(
  document: Document,
  options: ExtractFormSchemaOptions = {}
): FormSchema {
  const metadata = {
    title: options.title ?? document.title ?? 'Untitled Form',
    url: options.url ?? (document.defaultView?.location?.href ?? ''),
  };

  // Temporary storage for parsed fields (will convert to FormSchema format at the end)
  interface ParsedField {
    fieldId: string;
    name: string;
    label?: string;
    type: FieldType;
    required: boolean;
    options?: string[];
    placeholder?: string | null;
    helpText?: string | null;
    constraints?: Record<string, string | number | boolean>;
    selector?: string;
  }

  const fields: ParsedField[] = [];
  const seenIds = new Set<string>();

  const mainForm = selectPrimaryForm(document);

  const escapeForSelector = (value: string) =>
    value.replace(/([\\/:*?"<>|\[\]().#\s])/g, '\\$1');

  const shouldSkip = (element: Element): boolean => {
    const tag = element.tagName.toLowerCase();
    if (tag === 'input') {
      const input = element as HTMLInputElement;
      const type = (input.getAttribute('type') || '').toLowerCase();
      if (!type || ['text', 'checkbox', 'radio', 'email', 'tel', 'number', 'date', 'time', 'password', 'search'].includes(type)) {
        // allowed types fall through
      } else {
        return true;
      }
    }

    if ((element as HTMLInputElement).type === 'hidden') return true;
    if (element.hasAttribute('disabled')) return true;
    if (element.hasAttribute('data-vff-ignore')) return true; // Skip elements marked with data-vff-ignore
    if (element.getAttribute('aria-hidden') === 'true') return true;
    if (element.closest('[aria-hidden="true"]')) return true;
    if (element.closest('[data-vff-ignore]')) return true; // Skip elements inside containers marked with data-vff-ignore
    if (element.closest('.FormCaptcha')) return true;
    if (element.closest('.recaptcha')) return true;
    
    // Skip OneTrust cookie consent fields
    const elemId = element.id || '';
    if (elemId.startsWith('ot-') || elemId.startsWith('onetrust-') || elemId.includes('-handler')) return true;
    if (element.closest('#onetrust-consent-sdk') || element.closest('#onetrust-banner-sdk') || element.closest('#onetrust-pc-sdk')) return true;
    
    const classList = (element as HTMLElement).classList;
    if (classList.contains('picker__input') || classList.contains('cp_input_datetime')) return true;
    const role = element.getAttribute('role');
    if (role === 'presentation') return true;
    const tabIndex = element.getAttribute('tabindex');
    if (tabIndex === '-1' && classList.contains('picker__input')) return true;
    if (elementMatchesDisplayNone(element)) return true;
    if (hasHiddenAncestor(element)) return true;
    return false;
  };

  const getLabelText = (element: HTMLElement): string | undefined => {
    const id = element.id;
    if (id) {
      const selector = `label[for="${escapeForSelector(id)}"]`;
      const label = document.querySelector(selector);
      if (label?.textContent) {
        // Try to get just the label span, not the entire content which might include selected values
        const labelSpan = label.querySelector('[data-automation-id$="-label-span"]');
        if (labelSpan?.textContent) {
          return labelSpan.textContent.trim();
        }
        return label.textContent.trim();
      }
    }
    
    // Check data-for attribute (used by some form builders)
    const dataFor = element.getAttribute('data-for');
    if (dataFor) {
      return dataFor.trim();
    }
    
    const labelledBy = element.getAttribute('aria-labelledby');
    if (labelledBy) {
      const labelNode = document.getElementById(labelledBy);
      if (labelNode?.textContent) {
        return labelNode.textContent.trim();
      }
    }
    const ariaLabel = element.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel.trim();
    const parentLabel = element.closest('label');
    if (parentLabel?.textContent) {
      return parentLabel.textContent.trim();
    }
    const containerLabel = element.closest('.formFieldContainer, li');
    if (containerLabel) {
      const label = containerLabel.querySelector('.labelForFieldElement');
      if (label?.textContent) return label.textContent.trim();
    }
    return undefined;
  };

  const getHelpText = (element: HTMLElement): string | undefined => {
    const describedBy = element.getAttribute('aria-describedby');
    if (describedBy) {
      const help = document.getElementById(describedBy);
      if (help?.textContent) return help.textContent.trim();
    }
    const container = element.closest('.formFieldContainer, li');
    if (container) {
      const tip = container.querySelector('.tip');
      if (tip?.textContent) return tip.textContent.trim();
    }
    return undefined;
  };

  const normalizeLabel = (label?: string): string | undefined => {
    if (!label) return undefined;
    let cleaned = label.replace(/\s+/g, ' ').trim();
    cleaned = cleaned.replace(/\s*\*$/, '').trim();
    cleaned = cleaned.replace(/\s*Required$/i, '').trim();
    cleaned = cleaned.replace(/\s*\(required\)\s*$/i, '').trim();
    cleaned = cleaned.replace(/\s*\(optional\)\s*$/i, '').trim();
    
    // Remove common placeholder text that got included in labels
    cleaned = cleaned.replace(/^(Select a |Choose a |Pick a )/, '');
    cleaned = cleaned.replace(/(Select a state|Choose an option|--)\s*$/, '').trim();
    
    return cleaned.length ? cleaned : undefined;
  };

  const inferType = (element: HTMLElement, label?: string): FieldType => {
    const tag = element.tagName.toLowerCase();
    if (tag === 'textarea') return 'textarea';
    if (tag === 'select') return 'select';

    const input = element as HTMLInputElement;
    const rawType = (input.getAttribute('type') || 'text').toLowerCase();
    if (rawType === 'checkbox' || rawType === 'radio') return rawType;
    if (rawType === 'email' || rawType === 'tel' || rawType === 'number' || rawType === 'date' || rawType === 'time') {
      return rawType;
    }

    const id = (input.id || '').toLowerCase();
    const name = (input.name || '').toLowerCase();
    const labelText = (label || '').toLowerCase().replace(/-/g, '');

    const indicates = (value: string, needles: string[]) =>
      needles.some((needle) => value.includes(needle));

    // Check label first for more accurate typing
    if (indicates(labelText, ['email'])) return 'email';
    if (indicates(labelText, ['phone', 'tel', 'mobile', 'cell'])) return 'tel';
    if (indicates(labelText, ['date of', 'start date', 'end date', 'birth', 'graduation'])) return 'date';
    if (indicates(labelText, ['time'])) return 'time';

    // Then check id/name, but be more specific to avoid false positives
    // Only match if 'date' appears at word boundaries or with separators
    if (/(^|[._-])date([._-]|$)/.test(id) || /(^|[._-])date([._-]|$)/.test(name)) {
      return 'date';
    }
    if (/(^|[._-])time([._-]|$)/.test(id) || /(^|[._-])time([._-]|$)/.test(name)) {
      return 'time';
    }
    if (indicates(id, ['email']) || indicates(name, ['email'])) {
      return 'email';
    }
    if (indicates(id, ['phone', 'tel']) || indicates(name, ['phone', 'tel'])) {
      return 'tel';
    }

    return 'text';
  };

  const collectOptions = (element: HTMLElement): string[] | undefined => {
    if (element.tagName.toLowerCase() === 'select') {
      const select = element as HTMLSelectElement;
      return Array.from(select.options).map((option) => option.textContent?.trim() || '').filter(Boolean);
    }
    return undefined;
  };

  const scope: ParentNode = mainForm ?? document;
  const elements = Array.from(scope.querySelectorAll('input, textarea, select')) as HTMLElement[];
  
  // Group radio buttons by name attribute
  const radioGroups = new Map<string, HTMLInputElement[]>();

  for (const element of elements) {
    if (shouldSkip(element)) continue;

    const input = element as HTMLInputElement;
    const inputType = (input.getAttribute('type') || '').toLowerCase();
    
    // Collect radio buttons into groups
    if (inputType === 'radio') {
      const name = input.getAttribute('name');
      if (name) {
        if (!radioGroups.has(name)) {
          radioGroups.set(name, []);
        }
        radioGroups.get(name)!.push(input);
      }
      continue; // Skip individual radio button processing
    }

    const fieldId = element.id || element.getAttribute('name') || undefined;
    if (!fieldId) continue;
    if (seenIds.has(fieldId)) continue;

    const label = normalizeLabel(getLabelText(element));
    const type = inferType(element, label);
    const rawName = element.getAttribute('name');
    const nameAttribute = rawName || label || fieldId;
    if (!label && !rawName) {
      continue;
    }
    if (isLikelyHoneypot(label, nameAttribute)) {
      continue;
    }
    const placeholder = element.getAttribute('placeholder');
    const helpText = getHelpText(element);
    const required = element.hasAttribute('required') || element.getAttribute('aria-required') === 'true';
    const optionsList = collectOptions(element) || undefined;
    const selector = element.id ? `#${escapeForSelector(element.id)}` : `[name="${escapeForSelector(nameAttribute)}"]`;

    // Apply form-specific enhancements for demo forms
    const enhanced = enhanceField(fieldId, metadata.url, optionsList, buildConstraints(element, type));

    fields.push({
      fieldId,
      name: nameAttribute,
      label,
      type,
      required,
      options: enhanced.options,
      placeholder: placeholder ?? null,
      helpText: helpText ?? null,
      constraints: enhanced.constraints,
      selector,
    });

    seenIds.add(fieldId);
  }
  
  // Process radio groups
  for (const [name, radios] of radioGroups.entries()) {
    if (radios.length === 0) continue;
    if (seenIds.has(name)) continue;
    
    // For radio groups, look for a label with for="name"
    let label: string | undefined;
    const groupLabelSelector = `label[for="${escapeForSelector(name)}"]`;
    const groupLabel = document.querySelector(groupLabelSelector);
    if (groupLabel?.textContent) {
      const labelSpan = groupLabel.querySelector('[data-automation-id$="-label-span"]');
      label = normalizeLabel(labelSpan?.textContent || groupLabel.textContent);
    }
    
    // Fallback: use the first radio's label if no group label found
    if (!label) {
      const firstRadio = radios[0];
      label = normalizeLabel(getLabelText(firstRadio));
    }
    
    if (!label) continue; // Skip if we can't determine a label
    if (isLikelyHoneypot(label, name)) continue;
    
    // Collect all option values
    const options = radios
      .map(radio => radio.getAttribute('value') || '')
      .filter(value => value.trim().length > 0);
    
    const required = radios.some(radio => 
      radio.hasAttribute('required') || radio.getAttribute('aria-required') === 'true'
    );
    
    const selector = `[name="${escapeForSelector(name)}"]`;
    
    // Apply form-specific enhancements for demo forms
    const radioOptions = options.length > 0 ? options : undefined;
    const enhanced = enhanceField(name, metadata.url, radioOptions, undefined);
    
    fields.push({
      fieldId: name,
      name,
      label,
      type: 'radio',
      required,
      options: enhanced.options,
      placeholder: null,
      helpText: getHelpText(radios[0]) ?? null,
      constraints: enhanced.constraints,
      selector,
    });
    
    seenIds.add(name);
  }

  const comboElements = Array.from(
    scope.querySelectorAll('button[aria-haspopup="listbox"], [role="combobox"]'),
  ) as HTMLElement[];

  for (const element of comboElements) {
    if (shouldSkip(element)) continue;
    if (mainForm && !mainForm.contains(element)) continue;

    const fieldId = element.id || element.getAttribute('name') || undefined;
    if (!fieldId || seenIds.has(fieldId)) continue;

    const rawLabel = getLabelText(element);
    const label = normalizeLabel(rawLabel);
    const rawName = element.getAttribute('name');
    const nameAttribute = rawName || label || fieldId;
    if (!label && !rawName) continue;

    if (isLikelyHoneypot(label, nameAttribute)) {
      continue;
    }

    const required = element.getAttribute('aria-required') === 'true'
      || /required/i.test(rawLabel || '')
      || element.getAttribute('data-required') === 'true';

    const placeholder = element.textContent?.trim() || null;

    const selector = element.id
      ? `#${escapeForSelector(element.id)}`
      : undefined;

    // Apply form-specific enhancements for demo forms
    const enhanced = enhanceField(fieldId, metadata.url, undefined, undefined);

    fields.push({
      fieldId,
      name: nameAttribute,
      label,
      type: 'select',
      required,
      options: enhanced.options,
      placeholder,
      helpText: null,
      constraints: enhanced.constraints,
      selector,
    });

    seenIds.add(fieldId);
  }

  // Convert parsed fields to FormSchema format
  return {
    source: 'web' as const,
    form_metadata: metadata,
    fields: fields.map(f => ({
      id: f.fieldId,
      name: f.name,
      type: f.type,
      required: f.required,
      options: f.options,
      value: f.placeholder,
      meta: f.constraints,
    })),
  };
}

function buildConstraints(element: HTMLElement, type: FieldType): Record<string, string | number | boolean> | undefined {
  const constraints: Record<string, string | number | boolean> = {};

  if (type === 'date') {
    const format = element.getAttribute('data-cp-datetimepicker-format') || element.getAttribute('placeholder');
    if (format) constraints.format = format;
  }
  if (type === 'time') {
    const interval = element.getAttribute('data-cp-datetimepicker-interval');
    if (interval) constraints.interval = Number(interval);
    const placeholder = element.getAttribute('placeholder');
    if (placeholder) constraints.format = placeholder;
  }

  const min = element.getAttribute('min');
  if (min) constraints.min = isNaN(Number(min)) ? min : Number(min);
  const max = element.getAttribute('max');
  if (max) constraints.max = isNaN(Number(max)) ? max : Number(max);
  const pattern = element.getAttribute('pattern');
  if (pattern) constraints.pattern = pattern;

  return Object.keys(constraints).length > 0 ? constraints : undefined;
}

function elementMatchesDisplayNone(element: Element): boolean {
  const styleAttr = (element as HTMLElement).getAttribute('style');
  if (styleAttr && /display\s*:\s*none/i.test(styleAttr)) {
    return true;
  }
  return false;
}

function hasHiddenAncestor(element: Element): boolean {
  let current = element.parentElement;
  while (current) {
    if (elementMatchesDisplayNone(current)) return true;
    if (current.hasAttribute('hidden')) return true;
    current = current.parentElement;
  }
  return false;
}

function selectPrimaryForm(document: Document): HTMLFormElement | null {
  const forms = Array.from(document.querySelectorAll('form')) as HTMLFormElement[];
  if (forms.length === 0) {
    return null;
  }

  const scored = forms.map((form) => {
    const score = form.querySelectorAll('input, textarea, select').length;
    const weight = form.getAttribute('data-drupal-selector')?.includes('webform-submission') ? 1000 : 0;
    return { form, score: score + weight };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored[0]?.form ?? null;
}

function isLikelyHoneypot(label: string | undefined, name: string): boolean {
  const text = (label || '').toLowerCase();
  if (text.includes('leave this field blank') || text.includes('honeypot')) return true;
  if (name && name.toLowerCase().includes('honeypot')) return true;
  return false;
}
