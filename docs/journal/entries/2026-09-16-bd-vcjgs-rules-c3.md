---
date: 2026-09-16
bead: polyglot-pdf-vcjgs
tags: [security, firestore, auth, sprint-23]
surfaces: [firestore.rules, backend/routes/signup_routes.py, frontend/src/contexts/AuthContext.tsx, backend/tests/unit/test_firestore_rules_text.py]
---

# C3: the staff-email allowlist is no longer publicly listable; the evidence trail has an explicit deny

Sprint 23 workstream C3 (`docs/sprint_23_security-audit_plan.md`, PF-6 P1
and the rules half of PF-8). `authorized_emails` carried `allow read: if
true` because the voice app's email signup queried it from the browser
before the account existed. A public read on a collection is a LIST: anyone
holding the public web config could enumerate every allowlisted staff
email. This change moves the check behind the backend and closes the rule.

## What changed

- **`POST /api/signup/check`** (`backend/routes/signup_routes.py`): body
  `{email}` (3..254 chars), one Admin-SDK lookup on the lower-cased address
  (`where email == ..., limit 1`), `204` on a hit and the uniform `404
  "Not found"` on everything else -- a miss, a string with no `@` (never
  looked up), a Firestore failure (fail closed). Same posture as
  `/api/links/open`: unauthenticated by design, the cause logged as a
  type/length only, the address never logged. Not rate-limited (PF-5 is
  the sprint's open decision).
- **`AuthContext.signUpWithEmail`** calls that route (JSON, lower-cased)
  and treats anything but `204` -- including a network failure -- as a
  refusal; the Firestore query and its four imports are gone. The test
  block was rewritten around a stubbed `fetch` (six cases incl. fail-closed
  and "200 is not the contract").
- **`firestore.rules`**: `authorized_emails` is `allow read, write: if
  false`; `confirmation_events` has its explicit deny block (it was safe
  only by the implicit default). Both joined `ADMIN_SDK_ONLY_COLLECTIONS`
  in the rules-text pin, which asserts the file and the list agree in both
  directions; its "NOT LISTED, deliberately" note now says why `users`
  stays out (owner-only read/write; a per-uid rule also denies listing)
  and that the allowlist moved in.
- Merging B1b (its sweep of `admin_backend/`) with this bead's `email` kwarg
  caught one admin sign-in log line carrying the address
  (`admin_backend/services/admin_auth.py`); it logs the length now.
- Docs: the allowlist section of `docs/components/auth.md` (server-side
  check, full deny, the deploy note no longer ties signup to a
  client-readable rule), the route row in `technical_guide.md`.

## Rules audit (the `firebase-security-rules-auditor` skill, run on the final file)

```json
{
  "score": 4,
  "summary": "Every collection except users/{uid} is a full client deny (Admin-SDK-only), and authorization on the backends is decided from verified token claims (firm_id, role, is_client_link), never from the self-written profile document; the one client-writable path is a user's own profile. No leak, no privilege escalation, no PII exposure remains after the authorized_emails close.",
  "findings": [
    {"check": "Storage abuse / type safety", "severity": "minor", "issue": "users/{uid} write has no field, type or size validation: a signed-in user can write arbitrary fields (incl. a decorative `role`) or a large document to their OWN profile. Nothing server-side reads that document for authorization, so this is self-data corruption / resource use only.", "recommendation": "Add hasOnly([uid,email,displayName,photoURL,createdAt,lastLogin,role]) with type checks and a size bound on the string fields; keep role out of the writable set once the profile's role is retired."},
    {"check": "Update bypass", "severity": "minor", "issue": "create and update share one owner-only rule for users/{uid}; with no shape validation there is nothing to bypass, but also nothing pinned.", "recommendation": "Same as above."},
    {"check": "Business logic", "severity": "n/a", "issue": "Email signup no longer needs a client-readable rule (server-side check); Google sign-in and the profile sync keep working under owner-only users access.", "recommendation": "None."}
  ]
}
```

The `users/{uid}` shape validation is filed as a follow-up
(`polyglot-pdf-wnkky`), not folded in: it changes a rule the profile
sync writes through and deserves its own emulator-backed proof.

## Not done here, and why

- **Emulator-backed rules tests** (criterion 1's "emulator rules test"):
  the Firestore emulator needs a Java runtime; the maintainer's machine
  has none and CI has no Java/emulator step. A test nobody has run is
  worse than no test (scar #9), so it is `polyglot-pdf-34y4y` (a
  `rules-tests/` package plus a CI job with Java). The rules-TEXT pin
  covers the two blocks mechanically in both directions today.

## Verification

- Scar #9, one interpreter each, all RED: `email=body.email` added to the
  refusal log (the widened guard); `strip()` dropped on the server (the
  whitespace test); the trim dropped on the client (vitest); the backend's fail-closed branch
  flipped to fail-open (the 404-on-failure test); `allow read: if true`
  restored on `authorized_emails` (the rules pin, both directions); the
  `confirmation_events` block removed (the rules pin); the browser treating
  `404` as allowed (two vitest cases red).
- Backend: the new route module (7 tests), the rules pin, the route-auth
  pin, the PII guard and the health tests green; frontend
  `AuthContext.test.tsx` 15 green; `tsc --noEmit` clean. Full suite (both services + repo-level) on the final commit: 6520 passed, 287 skipped, 4 deselected, 92 warnings
  (an earlier run's one failure was the C1 access matrix demanding a
  classification for the new route -- added to its deliberately-ungated
  list with the reason).

Fresh-eyes (Sonnet, read-only): one round, all three criteria PASS (the
emulator-test deviation judged met in substance given the tracked bead and
the rules-text pin); one doc gap -- `config-deployment.md`'s rules deploy
note still tied email signup to a client-readable rule -- fixed. Opus
cross-surface: round 1 traced the route into CORS (same-origin via the
`/api/**` Hosting rewrite in production, so no preflight), the E2 CSP, the
IAM envelope, the 422 handler, the access matrix and the deploy scripts,
and found the rest of the restatement set (scar #8): README and the demo
deploy script's comment still said the allowlist is publicly readable --
fixed, five sites; the log guard had no `email` kwarg, so the route's own
"never logs the address" promise had no repo-wide pin -- `email` joins the
sensitive set with a meta-test and a mutation; the server trimmed the
address while the browser did not -- one normalisation now (trim, then
lower-case for the check; the trimmed address creates the account),
pinned on both sides; two comment nits. Round 2 closed all but the tail of
one README sentence (different wording from the enumeration grep -- the
scar #8 remainder shape; fixed) and found the route using the positional
`.where()` every other query site avoids with a documented
`FieldFilter` + `ImportError` fallback -- adopted, and the fake now
records the FieldFilter's fields so the test pins that shape; it also
noted PF-5's rate-limit scope did not list the new door (the plan's row
and C4's surfaces now do). Round 3: NO-GAPS on the substance; one comment in the schema
editor's auth module (a contrast clause saying the voice app reads the
collection from the browser -- a third enumeration axis) fixed, plus a
redundant README clause.

## Lessons

- **"Read: if true" on a lookup table is a list, not a lookup.** The rule
  was written for one `where` query; Firestore rules cannot express "this
  query only", so the honest shapes are a server-side check or a full deny.

## Files

`firestore.rules`, `backend/routes/signup_routes.py`, `backend/main.py`,
`backend/tests/unit/test_signup_check_route.py`,
`backend/tests/unit/test_firestore_rules_text.py`,
`frontend/src/contexts/AuthContext.tsx`, `frontend/src/contexts/AuthContext.test.tsx`,
`docs/components/auth.md`, `docs/technical_guide.md`, `docs/freshness/*.ack`.
