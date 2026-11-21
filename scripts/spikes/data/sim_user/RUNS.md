# Simulated-user W-7 runs (bd polyglot-pdf-tmu0f)

Every run below is synthetic: the user side is the Haiku 5.5 actor playing the
`w7_ana_nospell_v1` persona, and its words come from the fact sheet via gTTS.
These are the E.3 bring-up runs, made while the harness was being built. The
measurement runs belong to bd `polyglot-pdf-15j9v` (E.4).

All runs: `gemini-3.8-live` on Vertex, `--arm dti --continuous --compression
--derive-compression --text-ai --pro-pass --user sim --actor haiku --tts gtts
--ears transcript`, `LIVE_TEMPERATURE=0.4`, `SPELLBACK_TOOL_ENABLED=true`.

| Run (UTC stamp) | Harness commit | Result | Why it is here |
|---|---|---|---|
| 20261119T234140Z | 4456f1329 | stopped after 3 turns, 1/22 confirmed | Exposed three harness bugs: the gate timeout was shorter than an 88 s option recital, a withheld turn_complete was not handled, and the stall streak did not reset. |
| 20261120T000312Z | b922224fa | aborted (exit 3) at turn 11, 4/22 confirmed | Exposed a Claude API 400 on empty history content, and the sim user not hearing the name_spellback clip. The fallback fail-fast worked as designed. |
| 20261120T001346Z | 4102abb47 | complete, 22/22 confirmed, 22/22 correct | First complete run. Cloud STT had no quota project, so divergence is empty; Haiku rejected a correct spoken-digit ZIP read-back four times. |
| 20261120T003632Z | afa7fe9fe | complete, 22/22 confirmed, 21/22 correct | Divergence valid (41 of 42 scored generations aligned). First name ended as "Anna": gTTS says Ana like Anna and the correction did not spell, so the loop ran 109 turns. |
| 20261120T010304Z | 7d0f25acc | complete, 22/22 confirmed, 22/22 correct | Clean: 47 turns, no rejections, 0 STT errors, 44 of 45 scored generations aligned, $1.48 all-in. |

Later harness commits (077e22ca9, da367dc39) changed how `gate_violations`
is measured and how the loop waits for a reply. They were reviewed offline and
not re-run live here.

# 3.8 benchmark re-run with the sim user (bd polyglot-pdf-15j9v)

Files: `bench/`. Findings: `scripts/spikes/sim_user_findings.md`. Same
config as above, plus `--persona` for the self-correcting group. Harness
commits are from PR #938 (`fix/sim-referee`) and PR #936.

| Run (UTC stamp) | Group | Harness commit | Result | Status |
|---|---|---|---|---|
| 20261120T180145Z | W-7 happy | d03e11a08 (pre-referee) | complete, 22/22 correct, $1.03 live | benchmark |
| 20261120T181950Z | W-7 happy | d03e11a08 (pre-referee) | complete, 22/22 correct, $1.10 live | benchmark |
| 20261120T183218Z | W-7 happy | d03e11a08 (pre-referee) | complete, 22/22 correct, $1.04 live | benchmark |
| 20261120T193947Z | W-7 self-correcting pilot | 468101acf (pre-referee) | complete, 21/22: the actor confirmed the slip "Lucy" | discarded |
| 20261120T200124Z | I-90 v2 pilot | 468101acf (pre-referee) | turn cap at 54/57 confirmed (51/57 correct): the actor rejected a correct CORAZON 20 times | discarded |
| 20261120T210813Z | W-7 self-correcting | 5eb79f3ef (referee) | complete, 22/22, 22 slips corrected, $1.58 live | benchmark |
| 20261120T225207Z | W-7 self-correcting | 07a2cb8d8 (+ gTTS retry) | complete, 22/22, 22 slips corrected, $1.72 live | benchmark |
| 20261120T231321Z | W-7 self-correcting | 07a2cb8d8 (+ gTTS retry) | complete, 22/22, 20 slips spoken and corrected, $1.39 live | benchmark |
| 20261120T213916Z | I-90 v2 | 5eb79f3ef (referee) | complete, 55/57 correct, $3.51 | benchmark |
| 20261120T221527Z | I-90 v2 | 5eb79f3ef (referee) | complete, 57/57 correct, $3.28 | benchmark |
| 20261120T232745Z | I-90 v2 | 07a2cb8d8 (+ gTTS retry) | complete, 54/57 correct, $3.87; turn 46 holds the one wrong referee override (fixed in 588645521) | benchmark, flagged |

Two more self-correcting W-7 runs (21:23Z, 21:28Z) crashed on a transient
gTTS refusal before writing any file; the retry in 07a2cb8d8 fixed that.
