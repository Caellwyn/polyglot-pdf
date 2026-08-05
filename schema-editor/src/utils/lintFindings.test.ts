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
  resolveOptionIndex,
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

  it('carries the raw option token -- index OR value, never pre-parsed', () => {
    expect(anchor('fields[0] (id=x).options[2]'))
      .toEqual({ kind: 'options', optionToken: '2' });
    expect(anchor('fields[0] (id=x).options[married].label_translations.spanish'))
      .toEqual({ kind: 'options', optionToken: 'married' });
  });

  it('maps condition paths and defaults the rest to the field', () => {
    expect(anchor('fields[3] (id=x).show_if').kind).toBe('conditions');
    expect(anchor('fields[3] (id=x).require_if.all_of[0]').kind).toBe('conditions');
    expect(anchor('fields[3] (id=x)').kind).toBe('field');
  });
});

describe('resolveOptionIndex (two producer conventions, Opus round 2)', () => {
  // i-90's real shape: numeric option VALUES that are NOT their indices.
  const values = ['2', '3', '4'];
  const lintRule = f({ rule: 'option-value-slug', field_id: 'x' });
  const translationRule = f({ rule: 'translation-drift-unresolved', field_id: 'x' });

  it('a translation flag resolves its token as an option VALUE', () => {
    // Value '2' lives at index 0 -- a digits-mean-index read anchored it at
    // index 2 (the option whose value is '4'), the wrong row.
    expect(resolveOptionIndex(values, translationRule, '2')).toBe(0);
    expect(resolveOptionIndex(values, translationRule, '4')).toBe(2);
  });

  it('a lint option rule resolves its token as an INDEX', () => {
    expect(resolveOptionIndex(values, lintRule, '2')).toBe(2);
    expect(resolveOptionIndex(values, lintRule, '0')).toBe(0);
  });

  it('an unresolvable token yields undefined (fall back, never a wrong row)', () => {
    expect(resolveOptionIndex(values, translationRule, 'ghost')).toBeUndefined();
    expect(resolveOptionIndex(values, lintRule, '9')).toBeUndefined();
    // an out-of-range index-convention token that matches a VALUE tiebreaks
    // to the value rather than rendering nowhere
    expect(resolveOptionIndex(values, lintRule, '4')).toBe(2);
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

  it('formLevelFindings keeps everything no field ROW can carry', () => {
    const anchored = f({ field_id: 'a', path: 'fields[0] (id=a)' });
    // A section-anchored finding (the publish-blocking to-review-pending
    // ERROR carries a SECTION id in its field_id) resolves to no field, so
    // it belongs to the Form row -- keying on the raw field_id string made
    // it render NOWHERE (Opus round 2).
    const sectionAnchored = f({
      severity: 'ERROR', rule: 'to-review-pending',
      path: 'sections[0] (id=sec_to_review_misc)',
      field_id: 'sec_to_review_misc',
    });
    const fields = [{ id: 'a' }];
    expect(formLevelFindings([coverage, anchored, sectionAnchored], fields))
      .toEqual([coverage, sectionAnchored]);
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
