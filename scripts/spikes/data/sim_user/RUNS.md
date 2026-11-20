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
