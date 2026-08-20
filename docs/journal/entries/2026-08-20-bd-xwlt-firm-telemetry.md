---
date: 2026-08-20
bead: polyglot-pdf-xwlt
title: "Firm telemetry: firm_id threading + wire session start/end logging"
sprint: 19
tags: [security, testing]
---

## Trigger

Last child of epic polyglot-pdf-02ye (firm tier) and the bead that makes the
maintainer's 2026-08-14 requirement real: "every session logged by the backend
should include the firm id, the form id, and the id of the originating
employee." This bead delivers the firm + form half; the employee half rides
the deferred magic-link bead (ugm6), which is where an employee id first
exists. Epic rubric #3: a per-firm usage count must be answerable by query,
with no client PII anywhere.

## What shipped

- firm_id on all three record types (confirmation, session-start,
  session-end), always present as a KEY -- None when no firm claim rode the
  session -- so a per-firm query can distinguish "no firm" from "key absent"
  and one equality query spans sessions and confirmations.
- The /ws/fill gate now KEEPS its decoded claims. It had been calling
  verify_token and throwing the result away, which is why the voice path
  could not see firm identity at all (the gap the lo88 Opus review flagged
  and recorded on this bead). firm_id is read from the TOKEN, never the
  handshake: a firm id a client can type is not an identity, and the
  spoofing case is pinned.
- log_form_session_start / log_form_session_end got their FIRST callers.
  Both shipped under bd z2is as scaffolding with zero callers. Start fires
  once per session after the Gemini session is up (a reconnect does NOT
  re-log -- form_session_id survives reconnects, so re-logging would inflate
  a per-firm session count with what is one session to the user). End fires
  in the handler's finally, so it records however the socket died, and
  reports "completed" only when the client sent form_complete -- otherwise
  the honest "abandoned".
- A confirmed-field counter on the callback handler, incremented inside the
  SAME `recorded` guard that gates confirmation logging, so the session-end
  count can never exceed the confirmation events it summarizes.
- firm_id is PRESERVED across the internal section-switch restart, exactly
  as kit_id is: that restart re-enters start_session with firm_id=None, and
  overwriting would have stripped firm identity from every record after
  section 1 -- the precise shape of the 47r3 kit_id bug.
- Tests: 4 new firm-telemetry tests (all three record types share the key;
  no-claim sessions still log with None; no client identifier rides any
  record) + 3 WS threading tests (claim is the source; a handshake-supplied
  firm_id is IGNORED; a no-claim session still runs). Every one
  mutation-verified, including the security-relevant one: pointing firm_id
  at the handshake reddens both the claim-source and the spoofing test.
- The confirmation sink's PII ALLOWLIST pin was updated deliberately (it
  asserts the exact key set; a new key is supposed to fail it) with a
  comment recording why firm_id is allowed: it names our paying customer,
  never the client.

- Review record: fresh-eyes r1 scored criterion 1 FAIL and found 5 issues
  (the reconnect end-log inversion, the section-resetting counter, an
  unguarded form_metadata access, stale doc citations, an incomplete doc
  claim); r2 returned NO-GAPS after verifying each fix. The Opus outer
  cross-surface review then found a BLOCKER nothing local could see and
  REPRODUCED it against the repo's own fake-Firestore harness: this bead
  made the kit hard-delete guard match session rows. Only the third of its
  three queries was scoped to field_confirmed; the other two were kit_id
  queries that had been safe only because session events carried no kit_id
  and had no callers -- both facts this bead reversed. One voice session
  made a kit permanently undeletable; one session with a null kit_id made
  every kit unverifiable. Fixed by scoping all queries to the event
  (server-side) with the kit test client-side over the bounded,
  short-circuiting stream -- no composite index, guard semantics unchanged
  -- and pinned by three regression tests including the exact reproduction.
  Filed as bd polyglot-pdf-68s2q.

## Lessons

- A function with zero callers is not "wired" -- and a doc calling it
  "defined but not yet wired" is the honest state until something calls it.
  Both session functions had shipped, been bug-fixed (a latent TypeError),
  and been documented for two beads before this one gave them a caller.
- Session-end telemetry belongs in the `finally`, not the happy path: the
  interesting sessions are the ones that die badly, and those are exactly
  the ones a happy-path call would miss.
- WIRING A DORMANT FUNCTION CHANGES THE MEANING OF CODE THAT READS ITS
  OUTPUT. Two guard queries were correct for years because session events
  had no kit_id and no callers; this bead falsified both premises at once,
  and the queries silently changed meaning without being touched. When a
  bead gives a dormant writer its first caller -- or adds a key to an
  existing record -- enumerate every READER of that collection before
  shipping, not just the writers. The local reviews could not see it: the
  guard lives in a file this diff never opened.
- A test that pins a MECHANISM (an operator, a query count) has to be
  re-derived when the mechanism legitimately changes, but the DANGER it
  guarded must survive the rewrite. The IS_NULL operator pin became
  meaningless when the null test moved client-side; the danger it protected
  (a filter that sweeps in every record with a kit_id) got a new pin rather
  than being dropped with it.
- A fake that records what a query FETCHED cannot see a caller that breaks
  early. Counting consumption instead of batch size is what made the
  short-circuit measurable -- and the early-return provably real.
- "Completed" must come from an explicit client signal (form_complete), not
  from the absence of an error. Inferring completion from a socket close
  would report every abandoned session as finished -- a usage statistic that
  flatters rather than informs.

## Doc freshness

- Bumped: standards/confirmation-and-audit.md (firm_id in the record shape +
  its own explanation; the session pair rewritten from "defined but not yet
  wired" to wired, with the reconnect and finally semantics; the
  delete-sweep scoping note strengthened now that session records are live
  on every kit), components/auth.md (firm_id has a second consumer; firm_role
  still future), technical_guide.md (Surface contracts entry 6: the event
  shape gains firm_id, plus the two session records).
- Reviewed and left: components/tool-call-flow.md mentions field_confirmed
  only as a flow step, not a key list.

## Files touched

- backend/utils/confirmation_logger.py
- backend/routes/websocket_routes.py
- backend/services/form_filling_service.py
- backend/services/callback_handler.py
- backend/tests/unit/test_firm_telemetry.py (new)
- backend/tests/unit/test_confirmation_firestore_sink.py (allowlist pin)
- backend/tests/unit/test_kit_guarded_delete.py (guard scoping + 3 regressions)
- backend/tests/integration/test_websocket_ephemeral.py
- docs/standards/confirmation-and-audit.md, docs/components/auth.md,
  docs/technical_guide.md
- docs/journal/entries/2026-08-20-bd-xwlt-firm-telemetry.md (this entry)
