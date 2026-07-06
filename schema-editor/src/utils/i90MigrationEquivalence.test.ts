// Evaluator-equivalence for the i-90 v1->v2 migration (bd polyglot-pdf-c5r8,
// P6.1b). Over enumerated trigger assignments, the SAME set of fields must be
// shown / required by new-evaluator(migrated) as by new-evaluator(original) --
// i.e. the migration preserved conditional BEHAVIOR, only re-expressing it in v2
// (checkbox_group, semantic slugs, includes/is_not_empty operators).
//
// "The same trigger assignment" is a real-world user choice; its LITERAL value
// differs per schema (v1 widget-leaf value vs v2 minted slug), so the harness
// maps the v1 value to the v2 slug via the migration_report slug_maps written by
// P6.1b. For each trigger field it enumerates {unset} + each of that trigger's
// option values, and compares the resulting shown/required set across ALL fields
// that carry a show_if/require_if. Single-trigger enumeration is sufficient: the
// i-90 conditions are each keyed on ONE trigger, so a per-trigger sweep exercises
// every condition's true/false transition (a full 2^13 cross-product would add
// no coverage the single-trigger sweep lacks here).

import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { isFieldRequired, shouldShowField } from './conditionalVisibility';
import type { FormField } from '../types/schema';

// Repo root by marker file (import.meta.url is not a file: URL under
// vitest+jsdom; process.cwd() is the package root -- walk up to the repo).
function repoRoot(): string {
  let dir = resolve(process.cwd());
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(dir, 'form-kits', 'i-90', 'schema.json'))) return dir;
    dir = dirname(dir);
  }
  throw new Error('repo root (form-kits/i-90) not found from ' + process.cwd());
}

const ROOT = repoRoot();
const KIT = join(ROOT, 'form-kits', 'i-90');

function readJson(p: string): any {
  return JSON.parse(readFileSync(p, 'utf-8'));
}

const migrated = readJson(join(KIT, 'schema.json'));
const original = readJson(join(KIT, 'schema_archived.json'));
const report = existsSync(join(KIT, 'migration_report.json'))
  ? readJson(join(KIT, 'migration_report.json'))
  : { slug_maps: {} };
const slugMaps: Record<string, Record<string, string>> = report.slug_maps || {};

// Every distinct trigger id named by any show_if/require_if atom.
function triggerIds(schema: any): string[] {
  const ids = new Set<string>();
  const atomsOf = (cond: any): any[] => {
    if (!cond || typeof cond !== 'object') return [];
    const buckets = ['all_of', 'any_of', 'none_of'].filter((b) => Array.isArray(cond[b]));
    if (buckets.length === 0) return [cond];
    return buckets.flatMap((b) => cond[b]);
  };
  for (const f of schema.fields) {
    for (const key of ['show_if', 'require_if']) {
      for (const atom of atomsOf(f[key])) {
        if (atom && typeof atom.field === 'string') ids.add(atom.field);
      }
    }
  }
  return [...ids];
}

// Fields that carry a condition (the surface to compare).
function conditionalFieldIds(schema: any): string[] {
  return schema.fields
    .filter((f: any) => f.show_if || f.require_if)
    .map((f: any) => f.id);
}

// The value to store for a trigger to represent "the user chose option `optValue`"
// in a given schema. A GROUP arrives as a string[] (multi-select): a v2
// checkbox_group AND a v1 checkbox-WITH-options (the pre-migration group shape --
// the evaluator's selectedSetFor treats an array uniformly, so this is the
// faithful input for both dialects). A STANDALONE checkbox (no options) is a
// boolean. radio/select is the scalar option value.
function triggerValueFor(field: any, optValue: string): unknown {
  const isGroup = field.type === 'checkbox_group'
    || (field.type === 'checkbox' && Array.isArray(field.options) && field.options.length > 0);
  if (isGroup) return [optValue];
  if (field.type === 'checkbox') return true;  // a standalone box is boolean
  return optValue;  // radio / select
}

// Enumerate a trigger's candidate option values from whichever schema declares
// them (both should agree on the option COUNT; values differ v1 vs v2).
function optionValues(field: any): string[] {
  if (!field || !Array.isArray(field.options)) return [];
  return field.options.map((o: any) => String(o.value));
}

// The set of {shown, required} facts for every conditional field, under a given
// fieldValues assignment.
function stateOf(schema: any, fieldValues: Record<string, unknown>): Record<string, string> {
  const fields = schema.fields as FormField[];
  const byId = new Map(fields.map((f) => [f.id, f]));
  const out: Record<string, string> = {};
  for (const fid of conditionalFieldIds(schema)) {
    const f = byId.get(fid)!;
    const shown = shouldShowField(f, fieldValues, fields);
    const required = isFieldRequired(f, fieldValues, fields);
    out[fid] = `${shown ? 'S' : '-'}${required ? 'R' : '-'}`;
  }
  return out;
}

// INTENTIONAL, MAINTAINER-APPROVED divergences (bd c5r8): 3 Part-4 accommodation
// checkboxes whose v1 show_if used `is_checked` on a RADIO trigger -- ALWAYS FALSE
// in both v1 evaluators (a dead condition; the fields never showed). The
// migration rewrites is_checked -> is_not_empty, so they now show once the
// Part-4 Yes/No is answered -- the AUTHOR'S CLEAR INTENT. The maintainer chose
// "fix to intent" (2026-07-06) over preserving the dead condition, so these are
// documented exceptions to strict equivalence, NOT unexplained drift. Every OTHER
// field must be behavior-identical before and after migration.
const INTENDED_DIVERGENCES = new Set<string>([
  'p4_checkbox1a', 'p4_checkbox1b', 'p4_checkbox1c',
]);

function comparableState(schema: any, fieldValues: Record<string, unknown>): Record<string, string> {
  const s = stateOf(schema, fieldValues);
  for (const id of INTENDED_DIVERGENCES) delete s[id];
  return s;
}

describe('i-90 migration: evaluator-equivalence (bd c5r8, P6.1b)', () => {
  const migById = new Map<string, any>(migrated.fields.map((f: any) => [f.id, f]));
  const origById = new Map<string, any>(original.fields.map((f: any) => [f.id, f]));
  const triggers = triggerIds(original);

  it('has the same conditional-field surface before and after migration', () => {
    expect(new Set(conditionalFieldIds(original)))
      .toEqual(new Set(conditionalFieldIds(migrated)));
  });

  it('shows/requires the same fields for the all-unset baseline', () => {
    expect(comparableState(migrated, {})).toEqual(comparableState(original, {}));
  });

  for (const trigId of triggers) {
    const origTrig = origById.get(trigId);
    const migTrig = migById.get(trigId);
    // A trigger referenced by a bracketed widget-leaf id may not resolve to a
    // field; skip enumerating its options (the baseline case still covers it).
    const opts = optionValues(origTrig);
    if (!origTrig || !migTrig || opts.length === 0) continue;

    it(`equivalent shown/required set for each value of trigger '${trigId}'`, () => {
      const map = slugMaps[trigId] || {};
      for (const origOpt of opts) {
        const migOpt = map[origOpt] ?? origOpt;  // mapped slug, else unchanged
        const origValues = { [trigId]: triggerValueFor(origTrig, origOpt) };
        const migValues = { [trigId]: triggerValueFor(migTrig, migOpt) };
        expect(comparableState(migrated, migValues), `trigger ${trigId}=${origOpt}`)
          .toEqual(comparableState(original, origValues));
      }
    });
  }

  // Pin the intended divergence POSITIVELY: the 3 accommodation checkboxes were
  // always-hidden in v1 and now show when the Part-4 radio is answered. If a
  // future change makes them behave the same as v1 again (or the migration stops
  // rewriting is_checked), this fails -- forcing a deliberate re-decision.
  it('the 3 accommodation checkboxes are the ONLY intended divergence (now shown)', () => {
    const trig = 'p4_checkbox1[1]';
    const migTrig = migById.get(trig);
    const origTrig = origById.get(trig);
    const optVal = optionValues(origTrig)[0];
    const migVal = (slugMaps[trig] || {})[optVal] ?? optVal;
    for (const id of INTENDED_DIVERGENCES) {
      const mf = migById.get(id);
      const of = origById.get(id);
      // v1: always hidden (dead is_checked). v2: shown when the radio is answered.
      expect(shouldShowField(of, { [trig]: triggerValueFor(origTrig, optVal) }, original.fields),
        `v1 ${id} should be hidden`).toBe(false);
      expect(shouldShowField(mf, { [trig]: triggerValueFor(migTrig, migVal) }, migrated.fields),
        `v2 ${id} should show`).toBe(true);
    }
  });
});
