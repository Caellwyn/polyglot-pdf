/**
 * Lint-finding identity + display helpers (sprint-18 C1, bd polyglot-pdf-o7y9):
 * fingerprints (rule + field + path-sans-identity, message EXCLUDED), the
 * property-anchor parse the FieldEditor renders findings by, and the Form
 * row's standalone-dismiss bookkeeping on schema._form_review.
 */
import { describe, it, expect } from 'vitest';
import type { FormSchema } from '../types/schema';
import type { LintFinding } from './remoteKitStore';
import {
  findingFingerprint,
  formLevelFindings,
  isFindingDismissable,
  isFindingDismissed,
  propertyAnchor,
  ruleLabel,
  stripIdentitySuffix,
  visibleFormFindings,
  withFormFindingDismissed,
} from './lintFindings';

function f(extra: Partial<LintFinding>): LintFinding {
  return {
    severity: 'WARNING', rule: 'translation-coverage',
    path: '$', message: 'gap', field_id: null,
    ...extra,
  };
}

const SCHEMA = {
  source: 'pdf', form_metadata: { title: 'T', version: '1' },
  parts: [], sections: [], fields: [],
} as unknown as FormSchema;

describe('findingFingerprint', () => {
  it('keys on rule + field + path, and EXCLUDES the message', () => {
    const a = f({ message: 'old wording' });
    const b = f({ message: 'rewritten by the copy pass' });
    expect(findingFingerprint(a)).toBe(findingFingerprint(b));
    expect(findingFingerprint(f({ rule: 'translation-mechanical' })))
      .not.toBe(findingFingerprint(a));
    expect(findingFingerprint(f({ path: '$.other' })))
      .not.toBe(findingFingerprint(a));
    expect(findingFingerprint(f({ field_id: 'x' })))
      .not.toBe(findingFingerprint(a));
  });

  it('strips the trailing identity token so a content edit does not move it', () => {
    expect(stripIdentitySuffix('fields (id=x).help[identity:abc123]'))
      .toBe('fields (id=x).help');
    // Only a TRAILING identity token strips -- an embedded look-alike stays.
    expect(stripIdentitySuffix('fields (id=x[identity:aa]).help'))
      .toBe('fields (id=x[identity:aa]).help');
  });
});

describe('propertyAnchor', () => {
  const anchor = (path: string) =>
    propertyAnchor(f({ path, field_id: 'x' }));

  it('maps help paths to instructions/details', () => {
    expect(anchor('fields[0] (id=x).help.instructions').kind).toBe('instructions');
    expect(anchor('fields (id=x).help[identity:abc]').kind).toBe('instructions');
    expect(anchor('fields[0] (id=x).help.details').kind).toBe('details');
  });

  it('maps option paths with their index', () => {
    expect(anchor('fields[0] (id=x).options[2]'))
      .toEqual({ kind: 'options', optionIndex: 2 });
    expect(anchor('fields[0] (id=x).options[0].label_translations.spanish'))
      .toEqual({ kind: 'options', optionIndex: 0 });
  });

  it('maps condition paths and defaults the rest to the field', () => {
    expect(anchor('fields[3] (id=x).show_if').kind).toBe('conditions');
    expect(anchor('fields[3] (id=x).require_if.all_of[0]').kind).toBe('conditions');
    expect(anchor('fields[3] (id=x)').kind).toBe('field');
  });
});

describe('ruleLabel', () => {
  it('labels known rules, falls back to the raw id, and stays silent for the local fallback', () => {
    expect(ruleLabel('unknown-operator')).toBe('Unrecognized comparison');
    expect(ruleLabel('some-brand-new-rule')).toBe('some-brand-new-rule');
    expect(ruleLabel('')).toBe('');
  });
});

describe('the Form row standalone dismiss (s18 C1, decision 1)', () => {
  const coverage = f({ path: '$.fields', message: 'guidance coverage gap' });
  const unclaimed = f({
    severity: 'WARNING', rule: 'dump-widget-unclaimed',
    path: "widget 'form1[0].x[0]'",
  });
  const multiclaim = f({
    severity: 'ERROR', rule: 'dump-widget-multiclaim',
    path: "widget 'form1[0].y[0]'",
  });

  it('formLevelFindings keeps only the field-less findings', () => {
    const anchored = f({ field_id: 'a', path: 'fields[0] (id=a)' });
    expect(formLevelFindings([coverage, anchored])).toEqual([coverage]);
  });

  it('a WARNING dismisses and stays dismissed under a reworded message', () => {
    const next = withFormFindingDismissed(SCHEMA, coverage);
    expect(next).not.toBe(SCHEMA);
    expect(isFindingDismissed(next, coverage)).toBe(true);
    const reworded = { ...coverage, message: 'totally new copy' };
    expect(isFindingDismissed(next, reworded)).toBe(true);
    // ...but a different rule/path re-raises.
    expect(isFindingDismissed(next, unclaimed)).toBe(false);
  });

  it('an ERROR is not dismissable -- it blocks the gate regardless', () => {
    expect(isFindingDismissable(multiclaim)).toBe(false);
    expect(withFormFindingDismissed(SCHEMA, multiclaim)).toBe(SCHEMA);
  });

  it('visibleFormFindings hides dismissed WARNINGs and always shows ERRORs', () => {
    let schema = withFormFindingDismissed(SCHEMA, coverage);
    expect(visibleFormFindings(schema, [coverage, unclaimed, multiclaim]))
      .toEqual([unclaimed, multiclaim]);
    schema = withFormFindingDismissed(schema, unclaimed);
    expect(visibleFormFindings(schema, [coverage, unclaimed, multiclaim]))
      .toEqual([multiclaim]);
  });

  it('dismissing is idempotent and never grows the stored list', () => {
    const once = withFormFindingDismissed(SCHEMA, coverage);
    const twice = withFormFindingDismissed(once, coverage);
    expect(twice).toBe(once);
    expect(once._form_review?.dismissed_fingerprints).toHaveLength(1);
  });
});
