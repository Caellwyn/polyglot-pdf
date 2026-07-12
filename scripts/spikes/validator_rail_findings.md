# Validator -> switch_to_field correction rail: live E2E verification

bd polyglot-pdf-oiok (sprint-11 epic fc7t, decision D2). Method + numbers so a
future session can judge staleness: google-genai 2.8.0, 2026-07-12, Vertex
(polyglot-demo-aa709), live model gemini-live-2.5-flash-native-audio (production
standard tier), validator gemini-2.5-flash-lite (production primary).

## Question

With the new steer text (the rail: "call switch_to_field with the first flagged
field's field_id... read the value back... update and confirm"), does the LIVE
production-configured model actually execute the sequence -- navigate ->
read-back -> correction -> confirm -- on a validator conflict?

## Method (backend/scripts/probe_validator_rail.py)

Deploy-faithful end to end from the seeded state onward: REAL I-90 schema; a
9-field contract-2 payload seeding the West-Virginia-state + Iowa-ZIP (50301)
contradiction; the REAL ValidatorService + TextAIGemini on Vertex produces the
verdict (not a fabricated conflict); the REAL
FormFillingService._compose_validator_steer composes the injected text; the live
session runs the REAL static DTI SI (build_form_context, 4457 chars), the REAL
continuous-mode tool declarations (switch_section dropped, 6 tools), the REAL
adapter live-config (thinking_budget 0, transcription on, derived+clamped
compression 5000/3500); tool acks mirror the production callback_handler
response shapes. Per trial: fresh session, steer injected as a user-role text
turn (the send_client_content shape), tool calls drained turn by turn.

## Result: 4/4 behavioral PASS (3+1 trials)

Every trial: validator flagged exactly [p1_line6e_state, p1_line6f_zipcode];
the model called switch_to_field on a flagged field, voiced a correct read-back
(e.g. "You previously selected West Virginia, but the ZIP code you provided
50301 belongs to Iowa. Which one is correct?"), then on the user's correction
called update_form_fields(p1_line6e_state) with the corrected value and
confirm_field on it. Run 1 trial 1 was a CHECKER false-negative only: the model
corrected the state to "IA" (the standard abbreviation) and the assertion
matched only "iowa"/"Iowa" -- the recorded trace shows the full correct
sequence; the checker now accepts the abbreviation and the clean re-run passed
4/4 assertions.

Variance observed (all acceptable): the model picks EITHER flagged field to
navigate to first (state or zipcode -- both are in the finding); correction
value arrives as "iowa"/"Iowa"/"IA"; an extra verify question sometimes
precedes confirm_field (the probe allows one "yes" turn, mirroring
probe_confirm_field's documented early-vs-post-yes variance).

## Cost

4 live trials + 4 flash-lite validator calls, ~$0.30 total (thinking disabled;
short sessions). Artifacts: scripts/spikes/data/validator_rail_20260712T202314Z.json
(3 trials incl. the checker false-negative trace) and
...20260712T202619Z.json (clean re-run).

## Verdict

The rail works live under production configuration. Scope honestly stated: this
proves the model ACTS on the steer; the steer fires at form_complete only in
continuous mode until wt6w ships page-end triggers (the epic's named
limitation), and the probe injects the steer directly rather than driving a
full client fill to the boundary (the ws unwrap between form_complete and
handle_validation_boundary is a one-line passthrough, unit-covered).
