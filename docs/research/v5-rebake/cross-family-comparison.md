# Cross-family judge comparison + cost actuals (bd polyglot-pdf-hif1)

*Committed evidence for the findings doc's cross-family and spend claims
(docs/research/2026-07-25-v5-rebake-findings.md).*

Methodology: 17 Claude (Sonnet) subagents -- one per language, run in the
agent harness with zero new API keys -- each re-judged that language's FULL
final baked set for both kits ({source, translation, where} pairs extracted
from the committed kit schemas, glossary register/DNT/digits/script rules in
hand), flagging only genuine drift/DNT/digit/script/register problems.

Counting rule: the comparison keys on DISTINCT (language, kit,
source-string) triples. The committed flag artifacts' 87-entry worklist
(73 unresolved + 14 ambiguous) collapses to 81 distinct triples, because
fan-out records the same source string at several kit paths (e.g. a source
that is both a field's spoken name and an option label, or repeated
unit-type fields). That is the "81" the agreement numbers below use.

Cost derivation: token sums below are summed from the re-bake run's own
per-call `text_ai_usage` log lines (prompt_tokens / output_tokens per
call), priced at the published Vertex list rates (gemini-2.5-pro
$1.25/M in, $10/M out; gemini-2.5-flash-lite $0.10/M in, $0.40/M out).

---

## Cross-family agreement (Claude Sonnet judge vs Gemini pipeline final verdict)

- Gemini worklist (unresolved + ambiguous): 81 distinct strings
- Claude flags on the FINAL baked set: 7 distinct strings
- Flagged by BOTH: 1
- Claude-only (Gemini's final pass cleared them): 6
- Gemini-only (Claude found the kept string acceptable): 80

### Claude-only flags (full detail)

- [CLAUDE-ONLY] afrikaans `w7` source="Middle name"
  translation="Tweede naam"
  reason: Meaning drift: 'Tweede naam' literally means 'second name', which reads as a second given name rather than a middle name. The standard, unambiguous Afrikaans term for 'middle name' is 'middelnaam' -- used correctly elsewhere in this same form set (e.g. the I-90 kit's 'current middle name' -> 'huidige middelnaam'). Ambiguous next to 'First name'/'Last name' fields.
- [CLAUDE-ONLY] afrikaans `w7` source="Name at birth middle name"
  translation="Naam by geboorte tweede naam"
  reason: Same drift as 'Middle name': 'tweede naam' (second name) is ambiguous/incorrect for 'middle name'; should be 'middelnaam' as used consistently elsewhere in the form set.
- [CLAUDE-ONLY] afrikaans `w7` source="Prior name middle name"
  translation="Vorige naam tweede naam"
  reason: Same drift as 'Middle name': 'tweede naam' (second name) is ambiguous/incorrect for 'middle name'; should be 'middelnaam' as used consistently elsewhere in the form set.
- [ALSO-GEMINI] french `i-90` source="My existing card has incorrect data because of Department of Homeland Security"
  translation="Ma carte existante contient des donn\u00e9es incorrectes en raison d'une erreur du Department of Homeland Security"
  reason: Meaning drift: the translation inserts "une erreur du" (an error by), a concept absent from this source string. The source sentence as given ends at "...because of Department of Homeland Security" with no mention of "error" -- the translator appears to have imported wording from the near-duplicate option elsewhere in the same form ("My existing card has incorrect data because of DHS error"), but judged against its own source text this instance adds content not present in the English.
- [CLAUDE-ONLY] portuguese `i-90` source="Sandy"
  translation="Loiro-escuro"
  reason: This is a fixed-vocabulary hair-color option (Bald, Blond, Red, Sandy, ...). 'Sandy' hair is a light tan/light-brown shade distinct from blond; 'Loiro-escuro' means 'dark blond', which shifts it into the blond category rather than rendering the sandy/tan-brown shade -- a meaning drift for this specific option label, not just an idiomatic rewording.
- [CLAUDE-ONLY] swedish `i-90` source="Hispanic or Latino"
  translation="Spansktalande eller latino"
  reason: Meaning drift: 'Hispanic' is an ethnicity/origin category (Latin American or Spanish-cultural descent), not a language-ability category. 'Spansktalande' means 'Spanish-speaking', which mismaps the term -- someone can be Hispanic without speaking Spanish, or Spanish-speaking without being Hispanic. On a US demographic-classification form field this changes what the voice model understands the option to mean.
- [CLAUDE-ONLY] swedish `i-90` source="Not Hispanic or Latino"
  translation="Inte spansktalande eller latino"
  reason: Same drift as 'Hispanic or Latino' above, repeated here: 'Hispanic' (ethnicity/origin) is rendered as 'spansktalande' (Spanish-speaking, a language-ability term), which is a different category.

## Cost actuals (from the re-bake call log)

- gemini-2.5-flash-lite: 92 calls, 120,197 in / 112,362 out tokens -> $0.06
- gemini-2.5-pro: 287 calls, 620,833 in / 341,909 out tokens -> $4.20
- TOTAL: $4.25
