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

## Lessons

- A function with zero callers is not "wired" -- and a doc calling it
  "defined but not yet wired" is the honest state until something calls it.
  Both session functions had shipped, been bug-fixed (a latent TypeError),
  and been documented for two beads before this one gave them a caller.
- Session-end telemetry belongs in the `finally`, not the happy path: the
  interesting sessions are the ones that die badly, and those are exactly
  the ones a happy-path call would miss.
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
- backend/tests/integration/test_websocket_ephemeral.py
- docs/standards/confirmation-and-audit.md, docs/components/auth.md,
  docs/technical_guide.md
- docs/journal/entries/2026-08-20-bd-xwlt-firm-telemetry.md (this entry)
