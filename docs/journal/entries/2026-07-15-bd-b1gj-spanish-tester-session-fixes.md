---
date: 2026-07-15
bead: polyglot-pdf-b1gj
title: "Spanish tester session fixes: unknown-field loop-breaker, language lock, epistemic + speech SI, disclaimer label, overlay i18n (6 beads)"
tags: [postmortem, hotfix, testing]
---

## Trigger

A hired tester ran the app in Spanish on 2026-07-15 (12:49-14:15 ET) and filed
19 bug reports (CSV with console logs). Cloud Run logs for the window were
pulled and correlated per bug. Headline finding: one session
(web_HztoUP05yUQ, 17:40-17:48Z) burned 483 tool calls in 8 minutes -- 340
update_form_fields of which 338 were rejected as unknown-field, plus 140
ask_secretary calls -- while the user heard "I can't record that number" and
then an English "One moment" on repeat until the idle-timeout disconnect.
Root cause chain (verified in code): the DTI validation pool holds only the
current field; a real-but-inactive field id passes _is_known_field_id (so the
h1bn coercion correctly leaves it), then validation rejects it with a bare
"<id>: unknown field" -- no recovery path, so the model retries forever.
Also observed: English leaking into a Spanish session (the get_form_status
tool description's quoted example utterance, verbatim-English recovery
prompts, the hardcoded 'I Agree' in the disclaimer prompt), the model claiming
no fields were filled without checking, too-fast speech, the regional
"nombre de pila", and an all-English overlay panel.

This PR bundles the six fix beads: polyglot-pdf-b1gj (unknown-field
dead-end), ghv4 (language lock), poc3 (epistemic SI block), t1aj (speech
style), s863 (disclaimer agree-button label), ibxz (overlay i18n).

## What shipped

- **b1gj -- unknown-field recovery + loop-breaker** (callback_handler.py):
  unknown ids are split via the already-injected _is_known_field resolver --
  manifest/merge-known ids get "this field exists but is NOT the active field
  ... call switch_to_field first"; unresolvable ids get "never invent or
  guess field ids". A per-session counter of consecutive wholly-unknown
  rejections escalates the 3rd+ response to a leading STOP RETRYING
  instruction and logs unknown_field_loop_breaker_fired (cost-telemetry
  visibility for runaway loops). Counter resets on any applied field or plain
  validation error.
- **ghv4 -- language lock**: the DTI SI LANGUAGE block is now
  CHOICE-authoritative, not detection-first (maintainer directive at closeout:
  pin to the language dynamically chosen at the app-start modal -- 18
  languages today, growing toward 90; utterance detection is only the
  fallback when no session language was announced). English system text (tool
  responses, errors, injected instructions) never changes the spoken
  language; every injected guidance block re-anchors the chosen language via
  a new "Speak <lang> aloud" segment in render_field_guidance (same pattern
  as the uogm fill-language segment; a get_spoken_language getter is injected
  into CallbackHandler and tracks the client-sent choice live). Quoted
  English utterances were purged from the get_form_status tool description,
  the secretary pending/fallback instructions, and RECOVERY_PROMPT_LEVEL_1-3
  (now instructions, not verbatim scripts). Nothing anywhere keys on Spanish
  specifically -- Spanish appears only in translation tables and test
  fixtures.
- **poc3 -- epistemic block**: new "WHAT YOU CANNOT SEE" SI block -- the model
  never knows fill/confirm state without checking get_form_status /
  ask_secretary, and must not assert form state unchecked.
- **t1aj -- speech style**: new "SPEECH STYLE" SI block -- measured pace
  (slower for numbers/spellings/read-backs), plain widely-understood
  vocabulary, no regional idioms or ultra-formal forms.
- **s863 -- disclaimer button label**: read_disclaimer now carries
  agree_button_label (resolved inside connection.ts readDisclaimer from the
  DisclaimerModal's own BUTTON_TRANSLATIONS, so all four callers get it with
  no signature change); DISCLAIMER_INITIATING_MESSAGE names that label with an
  'I Agree' fallback for old clients.
- **ibxz -- overlay i18n**: new frontend/src/demo/overlayTranslations.ts (18
  languages, house pattern per DisclaimerModal/connectionTimeoutTranslations)
  wired into both VoiceOverlay and VoiceOverlayMobile: Hold-to-Talk /
  Recording, Pause/Resume/Reconnect, Clear Form + its confirm dialog (now
  unified across desktop/mobile), Input Mode row, field counters, mic-error
  label. Non-English strings are a machine draft pending native review (same
  caveat as jf6w.1).

SI cost note (logging-and-cost invariant): the static DTI SI grew ~1.6k chars
(language-lock expansion + two new blocks), re-billed per turn on 2.5. Judged
worth it against the tester-blocking failures; flagged for the jnjj SI-diet
epic to reclaim if measurement disagrees.

Deferred / filed this sprint: polyglot-pdf-nm7z (audio output dies after
pause/unpause -- needs live repro), polyglot-pdf-ynbz (post-deploy retest of
bugs 5/6/11/12 + live verification of all six fixes -- the code beads close on
code-level criteria; live spot-checks are delegated to ynbz), polyglot-pdf-tjs1
(repair the rotten test_read_disclaimer_route_logic harness).

Also fixed in passing: the three test_disclaimer_flow.py tests were async
without asyncio markers, so pytest collected but silently SKIPPED them (they
only ran via __main__). Now marked; the un-runnable route-loop test is
explicitly @pytest.mark.skip'd with context (repair = tjs1).

Fresh-eyes assess (Step 5.5): round 1 Sonnet NO-GAPS; round 2 (final Opus)
GAPS-FOUND(1) + 2 minor observations. Adopted all three: (1) the SI's
pre-existing quoted English example utterances ('Is that correct?', the
address-conflict sample, the spelling read-back) violated the ghv4 criterion
-- fixed with an explicit illustration rider in the LANGUAGE block (quoted
phrases are English illustrations of intent, always expressed in the session
language) rather than deleting the load-bearing examples; (2) the
validator-exception path (result=None) returned a bare message-less response
and bypassed the loop-breaker -- now routed through the same formatter with
the counter advanced (+ unit test); (3) the untranslated connection-error
toasts (pre-existing, outside ibxz scope) deferred onto the ryu6
consolidation bead. Rejected: none.

## Lessons

- **A tool-rejection message with no exit ramp is a loop generator.** The
  model treated "unknown field" as retryable and burned 338 calls. Any in-band
  error a model can hit repeatedly must name the recovery action (here:
  switch_to_field) and escalate to an explicit STOP after N repeats -- the
  same shape as the 0y7 confirm loop-breaker.
- **Quoted example utterances in prompts/tool descriptions get spoken
  verbatim, in their own language.** The English "One moment while I check
  the form" example was read aloud in English mid-Spanish. Instructions about
  what to say must be phrased as instructions ("acknowledge briefly in the
  user's language"), never as quotable English strings. Same for "scripts"
  like the recovery prompts.
- **pytest can silently skip async tests that lack markers** -- they show as
  warnings, not failures, and rot invisibly (the disclaimer route test had
  been dead for months while "passing"). Watch skipped counts, not just
  pass/fail.

## Doc freshness

- docs/standards/ws-protocol.md -- UPDATED: `read_disclaimer` row documents the
  new optional `agree_button_label` rider (s863); stamp bumped 2026-07-15.
- docs/components/voice-ai.md -- UPDATED: actionable unknown-field rejections +
  STOP-RETRYING loop-breaker (b1gj); per-injection spoken-language re-anchor +
  no-quoted-English rule (ghv4); stamp bumped 2026-07-15.
- docs/standards/voice-and-vad.md, docs/technical_guide.md -- flagged stale by
  the checker (they track config.py / websocket_routes.py, which this branch
  touched), REVIEWED AND LEFT: this branch changed no VAD behavior and no HTTP
  API; their staleness predates this branch (tracked files last changed by
  earlier commits).

## Files touched

- backend/services/callback_handler.py -- unknown-field split + loop-breaker; spoken-language getter; secretary pending/fallback text
- backend/services/validation_handler.py -- (read only; unchanged)
- backend/services/form_filling_service.py -- get_spoken_language injection; send_disclaimer_message agree_button_label
- backend/services/ai_context.py -- render_field_guidance spoken_language segment
- backend/config.py -- SI language-lock/epistemic/speech blocks; get_form_status description; recovery prompts; disclaimer template
- backend/routes/websocket_routes.py -- read_disclaimer agree_button_label pass-through
- backend/tests/unit/test_field_validation_responses.py -- 5 new recovery/loop-breaker tests
- backend/tests/unit/test_dti.py -- spoken-language segment test
- backend/tests/unit/test_disclaimer_flow.py -- asyncio markers; s863 template test; explicit skip of the rotten route test
- frontend/src/demo/overlayTranslations.ts (new) + overlayTranslations.test.tsx (new)
- frontend/src/demo/VoiceOverlay.tsx / VoiceOverlayMobile.tsx -- panel strings from the map
- frontend/src/schema-forms/components/DisclaimerModal.tsx -- export BUTTON_TRANSLATIONS
- frontend/src/shared/connection.ts -- readDisclaimer sends agree_button_label
