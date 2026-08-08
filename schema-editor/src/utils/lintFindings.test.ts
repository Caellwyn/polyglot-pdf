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
  RULE_REMEDIES,
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

  it('strips the identity token so a content edit does not move it', () => {
    expect(stripIdentitySuffix('fields (id=x).help[identity:abc123]'))
      .toBe('fields (id=x).help');
    // NOT end-anchored (Opus outer review, pass 8): a backend change that
    // appends a segment after the token must not silently resume churning
    // every guidance fingerprint on each edit.
    expect(stripIdentitySuffix('fields (id=x).help[identity:abc123].extra'))
      .toBe('fields (id=x).help.extra');
  });

  it('is STABLE when an earlier field is removed (positional index stripped)', () => {
    // The `(id=X)` token is the identity; `fields[i]` is not. One Ignore
    // click shifts every later index, and a fingerprint carrying it falsely
    // demoted every later signed-off field -- the mass re-review wave the
    // message exclusion exists to prevent, re-entering through the path
    // (Opus outer review, pass 8).
    const before = f({
      rule: 'help-details-oversize', field_id: 'target',
      path: 'fields[1] (id=target).help.details',
    });
    const after = f({
      rule: 'help-details-oversize', field_id: 'target',
      path: 'fields[0] (id=target).help.details',   // an earlier field went away
    });
    expect(findingFingerprint(after)).toBe(findingFingerprint(before));
    // Section-anchored findings get the same treatment...
    expect(findingFingerprint(f({ path: 'sections[3] (id=sec_a)', field_id: 'sec_a' })))
      .toBe(findingFingerprint(f({ path: 'sections[0] (id=sec_a)', field_id: 'sec_a' })));
    // ...but an OPTION index is real identity (no id token beside it), so it
    // must still distinguish one answer choice from another.
    expect(findingFingerprint(f({ path: 'fields[0] (id=x).options[1]', field_id: 'x' })))
      .not.toBe(findingFingerprint(f({ path: 'fields[0] (id=x).options[2]', field_id: 'x' })));
  });

  it('still distinguishes two DIFFERENT fields (the id token survives)', () => {
    expect(findingFingerprint(f({ path: 'fields[0] (id=a)', field_id: 'a' })))
      .not.toBe(findingFingerprint(f({ path: 'fields[0] (id=b)', field_id: 'b' })));
  });

  it('distinguishes two different duplicate-value defects on one field (Opus outer r9)', () => {
    // option-value-duplicate is emitted at the BARE field path with the
    // offending value only in the message, so without a content
    // discriminator, fixing duplicate "a" and introducing duplicate "b"
    // inherited the old sign-off and never demoted.
    const dupA = f({
      rule: 'option-value-duplicate', field_id: 'x',
      path: 'fields[0] (id=x)', message: '2 answer choices share the value "a"',
    });
    const dupB = f({
      rule: 'option-value-duplicate', field_id: 'x',
      path: 'fields[0] (id=x)', message: '2 answer choices share the value "b"',
    });
    expect(findingFingerprint(dupA)).not.toBe(findingFingerprint(dupB));
    // The SAME defect reworded still matches -- only the listed rules take
    // the content discriminator, and the index strip still applies.
    expect(findingFingerprint(f({ ...dupA, path: 'fields[7] (id=x)' })))
      .toBe(findingFingerprint(dupA));
    // Other rules keep the message-independent fingerprint C12 depends on.
    const other = f({ rule: 'help-details-oversize', field_id: 'x',
                      path: 'fields[0] (id=x).help.details' });
    expect(findingFingerprint({ ...other, message: 'reworded entirely' }))
      .toBe(findingFingerprint(other));
  });

  it('never rewrites indices inside a PDF widget NAME (Opus outer r9)', () => {
    // `widget '<name>'` paths carry raw AcroForm names, which legitimately
    // contain fields[0]-shaped segments; collapsing them would let one
    // dismissal hide a different widget's finding.
    const w0 = f({ rule: 'dump-widget-unclaimed', field_id: null,
                   path: "widget 'form1[0].fields[0].x[0]'" });
    const w1 = f({ rule: 'dump-widget-unclaimed', field_id: null,
                   path: "widget 'form1[0].fields[1].x[0]'" });
    expect(findingFingerprint(w0)).not.toBe(findingFingerprint(w1));
  });
});

describe('propertyAnchor', () => {
  const anchor = (path: string) =>
    propertyAnchor(f({ path, field_id: 'x' }));

  it('maps help paths to instructions/details', () => {
    expect(anchor('fields[0] (id=x).help.instructions').kind).toBe('instructions');
    expect(anchor('fields (id=x).help[identity:abc]').kind).toBe('instructions');
    expect(anchor('fields[0] (id=x).help.details').kind).toBe('details');
    // The guidance verify-loop flags write a BARE `.help` path
    // (enrich_instructions.py); their remedies point at the Instructions
    // box, so that is their anchor -- and the lookahead must not swallow
    // `.help.details` (Opus outer review, pass 4).
    expect(anchor('fields (id=x).help').kind).toBe('instructions');
  });

  it('carries the raw option token -- index OR value, never pre-parsed', () => {
    expect(anchor('fields[0] (id=x).options[2]'))
      .toEqual({ kind: 'options', optionToken: '2' });
    expect(anchor('fields[0] (id=x).options[married].label_translations.spanish'))
      .toEqual({ kind: 'options', optionToken: 'married' });
  });

  it('matches the widget-claim rule\'s " option[j]" spelling too (Opus outer r1)', () => {
    // field-claim-unresolvable emits `fields[i] (id=X) option[j]` -- space,
    // singular. The dotted-plural-only regex sent this per-option ERROR to
    // the generic banner with no hint of which option is broken.
    expect(anchor('fields[3] (id=race) option[1]'))
      .toEqual({ kind: 'options', optionToken: '1' });
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

  it('a WARNING dismisses, and a CHANGED message re-raises it', () => {
    // The dismiss path deliberately diverges from the timeliness path
    // (second confirming review). Timeliness excludes the message so a
    // copy-pass rewording cannot mass-demote reviewed fields; a DISMISSAL is
    // a permanent human "I read this and accept it", and several form-level
    // rules carry their whole content in the message -- so it must re-raise
    // when the content changes. Accepted cost: a pure rewording of a
    // form-level WARNING re-asks once, on ONE row, which is far cheaper than
    // hiding a grown problem forever.
    const next = withFormFindingDismissed(SCHEMA, coverage);
    expect(next).not.toBe(SCHEMA);
    expect(isFindingDismissed(next, coverage)).toBe(true);
    const reworded = { ...coverage, message: 'totally new copy' };
    expect(isFindingDismissed(next, reworded)).toBe(false);
    // ...and a different rule/path is likewise untouched.
    expect(isFindingDismissed(next, unclaimed)).toBe(false);
  });

  it('an ERROR is not dismissable -- it blocks the gate regardless', () => {
    expect(isFindingDismissable(multiclaim)).toBe(false);
    expect(withFormFindingDismissed(SCHEMA, multiclaim)).toBe(SCHEMA);
  });

  it('mass-drift is not dismissable despite WARNING severity -- it is the ' +
     'wave collapse\'s only surviving signal (bd cf6v)', () => {
    // The collapse suppresses the per-field stale flags AND disarms the
    // per-field ack gate; dismissing this one finding would leave a kit
    // reading fully reviewed with every guidance_ack_sha1 stale and nothing
    // on any surface saying so. It clears only via re-bake/re-verify.
    const wave = f({
      rule: 'guidance-identity-mass-drift', path: '$',
      message: 'all 51 fields with authored guidance changed identity at once',
      severity: 'WARNING',
    });
    expect(isFindingDismissable(wave)).toBe(false);
    expect(withFormFindingDismissed(SCHEMA, wave)).toBe(SCHEMA);
    expect(visibleFormFindings(SCHEMA, [wave])).toEqual([wave]);
    // ...and an ordinary WARNING remains dismissable (the exception is
    // rule-scoped, not a severity flip).
    expect(isFindingDismissable(coverage)).toBe(true);
  });

  it('visibleFormFindings hides dismissed WARNINGs and always shows ERRORs', () => {
    let schema = withFormFindingDismissed(SCHEMA, coverage);
    expect(visibleFormFindings(schema, [coverage, unclaimed, multiclaim]))
      .toEqual([unclaimed, multiclaim]);
    schema = withFormFindingDismissed(schema, unclaimed);
    expect(visibleFormFindings(schema, [coverage, unclaimed, multiclaim]))
      .toEqual([multiclaim]);
  });

  it('a dismissal covers the finding READ, not the rule forever (2nd review)', () => {
    // Several form-level rules carry their whole content in the MESSAGE at
    // one fixed path: help-instructions-missing ("12 of 40 fields..."),
    // translation-coverage, and help-details-not-contained (emitted once PER
    // PARAGRAPH, all sharing rule+path+null field_id). Keying the dismissal
    // on the message-independent fingerprint meant one click hid a GROWING
    // problem forever, and hid sibling findings the human never saw.
    const at12 = f({
      rule: 'help-instructions-missing', path: '$.fields',
      message: '12 of 40 fields have no spoken guidance yet (a, b, c)',
    });
    const at300 = f({
      rule: 'help-instructions-missing', path: '$.fields',
      message: '300 of 400 fields have no spoken guidance yet (a, b, c)',
    });
    const dismissed = withFormFindingDismissed(SCHEMA, at12);
    expect(isFindingDismissed(dismissed, at12)).toBe(true);
    expect(isFindingDismissed(dismissed, at300)).toBe(false);
    expect(visibleFormFindings(dismissed, [at300])).toEqual([at300]);

    // Sibling paragraphs of help-details-not-contained stay independent.
    const para1 = f({
      rule: 'help-details-not-contained', path: '$.form_metadata.details',
      message: 'paragraph 1 is not a verbatim quote',
    });
    const para2 = f({
      rule: 'help-details-not-contained', path: '$.form_metadata.details',
      message: 'paragraph 2 is not a verbatim quote',
    });
    const oneDismissed = withFormFindingDismissed(SCHEMA, para1);
    expect(visibleFormFindings(oneDismissed, [para1, para2])).toEqual([para2]);
  });

  it('dismissing is idempotent and never grows the stored list', () => {
    const once = withFormFindingDismissed(SCHEMA, coverage);
    const twice = withFormFindingDismissed(once, coverage);
    expect(twice).toBe(once);
    expect(once._form_review?.dismissed_fingerprints).toHaveLength(1);
  });
});

describe('audit-identity-no-edition remedy tracks the publish gate (bd polyglot-pdf-xzw5)', () => {
  const remedy = RULE_REMEDIES['audit-identity-no-edition'];

  it('does not tell the author to IGNORE a missing edition date', () => {
    // It was safe to ignore while the fingerprint fallback was automatic. It is
    // now the one case the publish gate HARD REFUSES (422
    // AUTHOR_VERSION_REQUIRED), so "ignore this" pointed the author away from
    // the only action that clears it. The backend/frontend parity test compares
    // rule IDs only, never text, so CI was silent on the drift (Opus outer
    // cross-surface review).
    expect(remedy).not.toMatch(/ignore this/i);
    expect(remedy).not.toMatch(/fall(s)? back to a content fingerprint automatically/i);
  });

  it('names both real remedies: an edition date, or a version at publish', () => {
    // Allowlist rather than blacklist -- banning one phrasing is a synonym away
    // from being defeated, so assert what the text MUST offer.
    expect(remedy).toMatch(/edition date/i);
    expect(remedy).toMatch(/version/i);
    expect(remedy).toMatch(/publish/i);
  });
});
