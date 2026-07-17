/**
 * Load-time legacy-shape migration (bd polyglot-pdf-0x10.4).
 *
 * A kit saved by the pre-8n2s editor carries a top-level field `required`
 * key that NO consumer reads (the canonical home is validation.required, bd
 * a1ql). The editor's FormField type no longer declares the key, but a raw
 * JSON load keeps it on the object and JSON.stringify re-saves it -- so a
 * stale kit trips the backend's required-top-level lint ERROR forever, with
 * no UI control that could clear it. Migrating on load makes every load
 * path self-healing: a truthy legacy value moves into validation.required
 * (never clobbering an explicit canonical value), and the legacy key is
 * dropped either way. Mirrors backend schema_repair's
 * migrate-top-level-required action.
 */
import type { FormSchema } from '../types/schema';

export function migrateLegacyRequired(schema: FormSchema): FormSchema {
  const fields = schema.fields;
  if (!Array.isArray(fields)) return schema;
  let changed = false;
  const migrated = fields.map((f) => {
    if (!f || typeof f !== 'object' || !('required' in f)) return f;
    changed = true;
    const { required: legacy, ...rest } = f as typeof f & { required?: unknown };
    if (legacy && rest.validation?.required === undefined) {
      return { ...rest, validation: { ...rest.validation, required: true } };
    }
    return rest;
  });
  return changed ? { ...schema, fields: migrated } : schema;
}
