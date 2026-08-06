/**
 * The CLIENT half of the shared count-predicate parity fixture (sprint-18 C4,
 * bd polyglot-pdf-g687).
 *
 * backend/tests/unit/test_publish_readiness.py runs the SAME cases through the
 * Python is_counted_reviewed. Both must agree on every case, because the
 * catalogue renders the backend's stamped number while the open editor renders
 * this predicate's -- if they disagree, one saved kit shows two percentages,
 * which is the bug this bead exists to end.
 *
 * This file exists because prose could not hold the mirror together: the Python
 * side had omitted the guidance-staleness exclusion from the timeliness rule,
 * so the ordinary sign-off -> drift -> ack flow counted reviewed here and NOT
 * reviewed in the stamp. Per-side unit tests both passed; only a shared
 * expectation catches that class of drift (Opus fresh-eyes round 2).
 */
import { describe, it, expect } from 'vitest';
import { isCountedReviewed } from './reviewStatus';
import { currentIdentity } from './guidanceStaleness';
import type { FormField } from '../types/schema';
import type { LintFinding } from './remoteKitStore';
import fixture from './__fixtures__/reviewPredicateParity.json';

interface ParityCase {
  name: string;
  field: Record<string, unknown>;
  findings: LintFinding[];
  expected: boolean;
}

// The fixture writes `@identity` where a case needs the field's OWN identity
// hash -- the two languages compute that hash independently but must agree on
// its value, so neither side can hardcode it. On this side the hash is only
// ever compared against what the finding path carries, so resolving the
// placeholder consistently within a case is what the test needs.
const IDENTITY = 'deadbeefcafe0123456789abcdef012345678901';

function resolve<T>(value: T): T {
  return JSON.parse(
    JSON.stringify(value).replace(/@identity/g, IDENTITY),
  ) as T;
}

describe('count predicate parity with backend publish_readiness', () => {
  const cases = (fixture as { cases: ParityCase[] }).cases;

  it('the fixture is non-trivial (guards against an emptied file)', () => {
    expect(cases.length).toBeGreaterThanOrEqual(15);
    // Both outcomes must be represented, or a broken predicate that always
    // returns one value would pass every case.
    expect(cases.some(c => c.expected)).toBe(true);
    expect(cases.some(c => !c.expected)).toBe(true);
  });

  it.each(cases.map(c => [c.name, c] as const))('%s', (_name, c) => {
    const raw = resolve(c.field) as Record<string, unknown>;
    // `ackSha1: "@identity"` is the fixture's way of saying "an ack matching
    // this field's CURRENT identity" -- on this side the ack is compared
    // against the identity the FINDING PATH carries, so the resolved constant
    // is the right value to store.
    const review = raw._review as Record<string, unknown> | undefined;
    if (review && 'ackSha1' in review) {
      review.guidance_ack_sha1 = review.ackSha1;
      delete review.ackSha1;
    }
    const field = raw as unknown as FormField;
    const findings = resolve(c.findings);
    // Sanity: a case using @identity must actually parse as an identity, or it
    // would silently exercise the fail-open branch instead of the comparison.
    for (const f of findings) {
      if (f.rule === 'guidance-identity-stale') {
        expect(currentIdentity(findings, field.id)).toBe(IDENTITY);
      }
    }
    expect(isCountedReviewed(field, findings)).toBe(c.expected);
  });
});
