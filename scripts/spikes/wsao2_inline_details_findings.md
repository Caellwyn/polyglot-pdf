# wsao.2 measurement gate: inline help.details vs the live voice model -- findings

*Date: 2026-07-26 (overnight run). Bead: polyglot-pdf-wsao.2 (sprint-16 plan,
staging step 2). Model: gemini-live-2.5-flash-native-audio on Vertex
(GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709), google-genai SDK 2.8.x, manual VAD
(DISABLE_GEMINI_VAD=true), SEND_TRANSCRIPT=true. Harness: tests/e2e/
voice-harness/ driving the real frontend (vite --mode demo, port 5174) +
backend (uvicorn :8001) in the Claude Browser pane. Raw run data:
scripts/spikes/data/wsao2_runs.json. Total live spend: ~8 sessions, well under
$1 (each full-section w7 baseline in the wyhh matrix was $0.19-0.33; these
were 4-turn mini-sessions).*

## Question

Sprint-16's v1 delivery policy injects a field's `help.details` (verbatim
official-booklet excerpts) INLINE into the current field's guidance block.
Does a large reference block degrade tool-call reliability / field_id
fidelity / spoken discipline -- and does an English reference block
contaminate a non-English session? (The riskiest v1 assumptions, gated BEFORE
the enrichment engine is built.)

## Method

W7 reason-for-applying scenario, per run: seed `application_type` confirmed
(pre-agree, so the initiating hint targets `reason_a`) -> agree -> the model
asks reason_a -> inject a spoken deep question ("Do I need to attach a tax
return if I'm applying under a treaty exception?" -- answerable ONLY from the
booklet's reason section: Exceptions 1-2) -> capture the spoken answer
(transcript WS tap) -> inject the box-a answer -> assert `update_form_fields`
fills reason_a (sessionStorage, not DOM -- a checkbox's `domValue` is always
"on") -> confirm. Details applied to the LOCAL kit copy via
`tests/e2e/voice-harness/apply_details_w7.py` (verbatim programmatic
extraction from the booklet PDF; `--trim` for the 1,717-token variant), plus
`metadata.booklet_text` (81 KB floor) in all details arms.

> **Reproduction note (bd polyglot-pdf-r0za, 2026-07-31).** The 1,717-token
> figure below was produced by a `--trim` slicer whose "Exception 2." anchor
> matched a cross-reference inside category f's prose instead of the real body
> heading, so the artifact silently re-included box h and all of Exception 1.
> That anchoring bug is now fixed, and `--trim` today emits ~996 tokens (3,984
> chars, 42% smaller) with four non-overlapping slices. **The measurements in
> this doc are still valid as recorded** -- a 1,717-token details payload really
> did open a healthy session and answer correctly, so the ceiling bound below
> holds -- but re-running `--trim` will NOT reproduce 1,717 tokens.

## Results

| Arm | details size | runs | session | deep-question answer | fill+confirm |
|---|---|---|---|---|---|
| A baseline (no details) | 0 | 2 | healthy | "Regarding your question about attaching a tax return, that information is usually found in the form instructions. **I can't answer it based on the fields I have.**" | PASS both (tool call 500ms after utterance end, correct field+value) |
| B full section | 3,366 tok | 1 | **HARD FAIL: Vertex closes 1007 "the provided content is above the context window size 6400" at session assemble** | n/a (session never opens) | n/a |
| B trimmed | 1,717 tok | 2 | healthy | "It depends. If you're applying under **Exception 1** for passive income covered by a tax treaty, **you won't need to attach a tax return.** Are you applying under Exception 1 or a different exception?" (r2 equivalent) | PASS both |
| C Spanish + trimmed | 1,717 tok | 1 | healthy | Fully Spanish, grounded: "si solicita su ITIN bajo una excepci[o]n de beneficio de tratado fiscal, **no necesitar[a] adjuntar una declaraci[o]n de impuestos**..." | PASS |

(Answers quoted from output transcripts; accented characters bracketed here
for the repo ASCII convention -- the raw JSON has the verbatim text.)

## Verdict (the gate's exit question)

1. **Inline delivery WORKS and delivers exactly the intended value** at sizes
   that fit: grounded, concise, correct deep answers (vs. honest starvation at
   baseline), no wholesale read-aloud of the reference text, no ask-turn
   flooding, tool-call reliability and field_id fidelity intact across every
   healthy run, ~500ms answer-to-tool-call latency unchanged from baseline.
2. **BUT the binding constraint is not attention -- it is the ctu8-tuned
   context-compression window.** The live session's compression config
   derives (window, trigger) from the SI+tools floor
   (`derive_compression_window`, backend/adapters/live_ai_gemini.py); the
   effective assembled-content budget for this form is ~6,400 tokens. SI
   (12,274 chars) + tools + a 3,366-token details block in the initiating
   message breaches it -> instant 1007, session never opens. The 1,717-token
   variant fits. So the per-field inline details budget is FORM-DEPENDENT and
   mechanically computable (~ trigger - SI/tools floor - guidance overhead);
   for w7 it lies between 1,717 and 3,366 tokens.
3. **No language-lock contamination**: a Spanish session with English
   reference text answered fully in Spanish, grounded. The i18n bar holds.
4. **The delegate-fallback is words, not deeds**: at baseline the model SAID
   "I'm looking that up for you" but never called `ask_secretary` (0 calls in
   the log). The whole-booklet secretary floor is therefore unreachable in
   practice until the phase-2 hook (or stronger SI wiring) lands. Follow-up
   probe needed: does the model call ask_secretary for oversize/absent
   details when the DEEP QUESTIONS line says to? (Not measured tonight --
   inline details answered everything in the B/C arms.)
5. Compression-reclaim behavior (does the details block get evicted after
   moving on) was NOT directly observed -- sessions were 4 turns; the window
   constraint binds at session ASSEMBLE, before compression ever fires, so it
   supersedes the reclaim question for oversize blocks.

## Policy consequence (maintainer decision point, sprint-16 plan)

Inline stays the complex-field default WITH A SIZE BUDGET. For details that
exceed the budget, three options (not decided here):
  (a) bake-time size cap: lint hard-bounds `help.details` to the derived
      per-form budget; overflow content lives only in the secretary floor
      (reachable once phase-2 hooks land). Reversible, no cost change --
      RECOMMENDED default;
  (b) raise the compression window for details-bearing forms -- direct
      per-turn cost increase; re-opens the ctu8 economics;
  (c) activate phase-2 secretary-mediated delivery early for oversize fields
      -- adds the blocking ask_secretary round-trip (median ~1s, tail 8-20s)
      to deep answers.
Either way the enrichment engine (wsao.4) needs a details-size budget input,
and `derive_compression_window` / lint need to agree on the number.

## Harness fixes shipped with this bead (load-bearing for any future run)

- `injectUtterance` now paces chunks on a MessageChannel clock: background/
  hidden tabs clamp setTimeout to ~1Hz, which starved the old 20ms sleep
  pacing into a 1 chunk/sec smear (session idle-timeout); a pure microtask
  burst instead OVERFLOWS the backend audio queue (AUDIO_QUEUE_FULL frame
  drops). Channel-clocked pacing is real-time in any tab visibility state.
- Assert on sessionStorage (`ssValue`/`ssConfirmed`), never DOM: a checkbox
  input's `value` attribute is always "on" regardless of checked state --
  `waitForFieldValue`'s non-empty check false-positives on checkbox fields.
- Seed BEFORE agree: the post-agree re-handshake computes the next-field hint
  from client state at that moment; seeding after leaves the hint on the
  seeded field.
- Give the disclaimer session ~10s before clicking agree: an instant agree
  races the half-open Gemini session and can wedge the reconnect.

## Prior work consulted (Gate 1)

No prior measurement of guidance-block size vs tool-call reliability exists
(checked scripts/spikes/*_findings.md, journal, bd memories). Adjacent
priors: jnjj.46 (field_id fidelity depends on ids riding the acting channel
-- details ride the SAME channel, so no contradiction); wyhh
form_session_costs (session cost baseline used for the Gate-2 estimate);
f58l (hidden-tab clamp -- fix now landed in harness.js).
