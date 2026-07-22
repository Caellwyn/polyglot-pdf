# Multilingual voice UX assessment -- es / zh / fr / hi / ru (bd polyglot-pdf-6mzi)

**Date:** 2026-07-22. **SDK:** google-genai 2.8.0 (post-cutover). **Backend:**
Vertex (ADC, demo project), model `gemini-live-2.5-flash-native-audio`
(production default tier), production DTI arm (`--arm dti --continuous`,
text-AI sidecar wired). **Driver:** `measure_form_session_costs.py` extended
with `--spoken-language` (session spoken language seeded pre-connect exactly as
the production handshake does: ASR bias bd y25o + option-label translation bd
ow1e both follow from it) and per-language persona phrasing in
`fixtures/multilang_phrases.json` (bd 6mzi; native-script text lives in the
JSON fixture, never in .py source). Output transcripts captured via `--debug`
(per-question `model_said` / `model_heard` + the new `greeting_model_said`).

**Question:** what register does the assistant use per language; does it slip
into other languages, produce nonsense/bad/inappropriate translations, or
otherwise degrade UX for low-literacy, low-English-proficiency native speakers?

## Method

One 14-question I-90 slice per language (A-number, USCIS account, 3 name
fields, name-change checkbox, full mailing-address block), happy path, user
answers gTTS-synthesized IN the target language (native script for zh/hi/ru),
personal names spelled letter-by-letter per the 5roy convention. One run per
language -- single-run observations are flaky-class evidence, not rates.

| run (data/costs_i90-full_2.5_dti_cont_happy_*) | lang | spoken_language | all-in USD | fill acc | failure modes |
|---|---|---|---|---|---|
| 20260722T173837Z | es | Spanish | $0.727 | 13/14 | transcription: apt "12" -> "2" |
| 20260722T174131Z | zh | Chinese | $0.656 | **9/14** | wrong-field x2 (name-block shift), mismatch (middlename "N/A"), transcription ("Westhamer"), spurious ("N/A" into in-care-of) |
| 20260722T174410Z | fr | French | $0.726 | 14/14 | none |
| 20260722T174640Z | hi | Hindi | $0.572 | 13/14 | apt filled "10" (model-invented) vs spoken "12" |
| 20260722T174916Z | ru | Russian (UNSUPPORTED in app) | $0.518 | 13/14 | givenname "LIN" vs "LINH" |

Total live spend: ~$3.20 (Gate-2 estimate was $1.5-2.5; per-run cost of the
DTI 14q slice is ~2.5x the old E6 10q pilot arm -- the estimate was anchored on
the wrong arm, noted for next time).

## Per-language register verdicts

- **Spanish -- GOOD.** Warm, natural, consistently usted-form conversational
  register ("Hola, bienvenido... ?Cual es su numero de registro de extranjero,
  su 'A-Number'?"). Plain-language questions, no academic stiffness. One
  English-jargon leak (below).
- **Chinese -- ADEQUATE register, WORST correctness.** Polite 您-form, natural
  phrasing ("您好! 我们现在开始填写 I-90 表格的第一部分"). But this run
  desynced the name block (see D2) -- 5 of 14 fields wrong.
- **French -- EXCELLENT.** Best of the five: polite vous-form, complete
  courteous sentences ("Pourriez-vous me donner votre numero d'enregistrement
  d'etranger, s'il vous plait ? C'est un numero de 7 a 9 chiffres qui commence
  par 'A'.") -- proactively explains what the field looks like. 14/14 fills.
- **Hindi -- GOOD register, one severe defect.** Natural aap-form Hindi with
  everyday English loanwords ("स्पेलिंग", "अपार्टमेंट") -- the right register
  for the target user, not shuddh-Hindi academic. But it invented a field id
  AND a value (see D3).
- **Russian -- SPEAKS IT, but the roughest UX.** Russian is NOT one of the 17
  supported spoken languages (frontend `SPOKEN_LANGUAGES`); passed anyway, the
  model does converse in fluent Russian. Register is noticeably TERSER than
  every other language ("Какой город?", "Какой штат?" -- bare two-word
  questions vs French's full courteous sentences). One mid-sentence English
  slip ("Ваше имя legally изменилось..."). The greeting reads the form title
  in raw English ("Мы заполняем раздел 'Application to Replace Permanent
  Residence Card'") where es/fr/hi translated or paraphrased it. And with no
  BCP-47 ASR bias (Russian is unmapped in `language_codes.py`), the INPUT
  transcription is language-chaos: Russian utterances came back as German
  ("Dieses Datum ist korrekt"), French ("Ma joie emaillee"), Spanish
  ("Miercoles 4200", "Ya. Voy a ver la parte 1"), and literal junk ("\\[2/3]").
  The native-audio model mostly filled correctly anyway (it hears the audio,
  not the transcription), but the one mis-fill (LIN vs LINH) was a spelled
  name -- exactly where transcription chaos bites. Empirically validates the
  ow1e "every supported language MUST be code-backed" decision for the coming
  language expansion (bd ryu6).

**No inappropriate or offensive output was observed in any language.** No
hallucinated "nonsense words" in the model's own speech; translation quality
of its questions was faithful in all five.

## Defects (beads filed)

- **D1 -- English field labels leak into non-English speech + per-field
  secretary spam** (bd polyglot-pdf-37le). The DTI turn context gives the model
  ENGLISH-only field names; in non-English sessions the model either reads
  them aloud raw (es: "El nombre para ese campo es 'uscis online account
  number'"), narrates internal state (hi: "मुझे खेद है, सिस्टम में आपका
  वर्तमान पारिवारिक नाम अभी उपलब्ध नहीं है" -- "sorry, the system doesn't
  have your family name yet"), or burns a tool call per field asking the
  secretary "what is the spoken name for p1_line2_acctidentifier" (es/zh) /
  "what is the status of <field>" (fr: 14/14 questions -- the known
  chatty-secretary mode, now with a localized trigger). Cost + latency + jargon
  aloud to exactly the user who can't parse it.
- **D2 -- zh name-block desync: answers filled one field behind** (bd
  polyglot-pdf-r5m7). The zh run assigned familyname=LINH, givenname=THI,
  middlename=N/A (expected NGUYEN/LINH/THI) -- the model lagged one field
  behind the user's answers and never recovered; 5/14 fields wrong in a single
  happy-path run. Not seen in the other four runs.
- **D3 -- hi: model INVENTED a field id and a value, then propagated the
  invented value over the user's real answer** (bd polyglot-pdf-djnk). Called
  `update_form_fields` on nonexistent `p1_line6c_unitnumber` with value "10"
  (user never said 10), spoke "अपार्टमेंट 10" aloud, then filled the REAL apt
  field with "10" and confirmed it -- while the user's actual "12" was heard
  correctly and discarded. field_id hallucination class (jnjj.46) escalated:
  value invention + propagation.
- **D4 -- Cyrillic spell-back makes name verification meaningless** (bd
  polyglot-pdf-s39z). ru run read NGUYEN back as Cyrillic letter names
  ("Н-Д-Ж-У-И-Е-Н") -- a transliteration, not the Latin spelling the form gets.
  The 5roy verify-by-spelling mitigation silently loses its power in any
  non-Latin-script session (zh happened to spell in Latin; ru did not), and the
  run's one mis-fill (LIN vs LINH) sailed through exactly this readback.
- **D5 -- short numeric answers are fragile in non-English sessions** (bd
  polyglot-pdf-ww9y). es: "apartamento numero 12" filled as "2" and read back
  "El numero es 2, ?es correcto?"; hi: apt number filled with the invented
  "10" (D3). Small numbers lack the digit-by-digit redundancy long IDs have.
- **D6 -- decline/empty convention differs by language** (bd
  polyglot-pdf-nb2c). Same "I don't have that" decline: es/fr/ru/hi filled ""
  (correct); zh wrote literal "N/A" into in-care-of-name (scored spurious) and
  middle name. What prints on the PDF should not depend on session language.
- **D7 -- register + form-title localization is uncontrolled** (bd
  polyglot-pdf-h1me). Nothing in the SI pins warmth/level: French got
  proactive courteous explanations, Russian got two-word telegraphic
  questions and an untranslated English form title in the greeting. For
  low-literacy users the SI should mandate plain, warm phrasing and
  translating form/section titles.
- **H1 -- harness gap: confirmation audio is English in every language** (bd
  polyglot-pdf-lo37). The persona's "Yes, that's correct" fixture is English
  regardless of --lang (transcribed as "यस, दैट्स करेक्ट" in hi; as German/
  Spanish garbage in ru). Realism gap AND a confound: part of the ru
  transcription chaos is English-confirm audio through an unbiased ASR.
  Localize the confirm/decline fixtures per language.

## What worked well (keep)

- **Fill-language separation holds in all five languages**: city spoken as
  休斯顿 / ह्यूस्टन / Хьюстон was written "Houston"; native option answers
  ("我选择 apartment", "Я выбираю Техас", "mai apartment chunta hoon") mapped
  to the correct English option slugs every time.
- **Option labels were spoken IN the session language** (fr: "un appartement,
  une suite ou un etage ?"; zh: "公寓"; ru model self-translated despite no
  ow1e task) -- the ow1e pipeline plus the model's own translation covers this
  surface.
- **Name spell-first (5roy) works in Latin-script sessions**: es/fr/hi/zh all
  asked for spelling and filled NGUYEN/LINH/THI exactly (zh's failure was
  field ASSIGNMENT, not spelling).
- French and Spanish sessions are demo-ready today on this evidence.

## Bundle C verification (2026-07-22, post-fix reruns)

Sprint-13 Bundle C (mccl add-Russian + nb2c decline rule + s39z Latin
spell-back + djnk discard rule + lo37 localized confirms) was verified with
one rerun each of the two most affected languages:

| run | lang | fill acc | verdict vs baseline |
|---|---|---|---|
| 20260722T215056Z | ru | 12/14 | Input transcription now predominantly RUSSIAN (de/es garble gone -- the ru-RU bias works); confirms transcribed as Russian (lo37); spell-back in LATIN letter names and all three names filled correctly incl. LINH (s39z; baseline mis-filled LIN); greeting translated the section title. Kit-baked Russian option labels covered 100% (text cost $0 -- kit precedence). Two misses: a street transcription typo ("Westhheimer") and apt "12" filled as "19" -- the ww9y short-numeric class AGAIN, second language, recorded on the bead. |
| 20260722T215331Z | zh | **14/14** | No name-block desync this run (baseline: 9/14 with 3 shifted names); declines stored EMPTY, no literal "N/A" (nb2c); Latin spell-backs; confirms transcribed as Chinese (lo37). Single run -- desync non-recurrence is NOT proven (that is A1's n>=3 job, bd 66ek.1). |

## Register-guidance A/B (bd polyglot-pdf-zmlo, 2026-07-22)

Language-agnostic REGISTER rule (+ title translation) added to both SIs and
A/B'd on ru (n=3 per arm; baseline = the m1lg flag-ON runs, identical config
except the rule) then checked on es (n=3, rule on):

| arm | fills | mean words/turn | notes |
|---|---|---|---|
| ru baseline (231520/231732/231941Z) | 38/42 | 7.7 | short-question sentences incl. bare field asks ("Номер квартиры?") |
| ru + register rule (232428/232637/232852Z) | 37/42 | 8.5 | fuller courteous asks ("Не могли бы вы назвать..."); remaining short sentences are almost all "Верно?" confirm tags (desirable brevity) |
| es + register rule (233334/233604/233836Z) | 40/42 | -- | register stays warm; NO regression |

Verdict: SHIPPED (the general rule, per maintainer preference; no
per-language register controls needed on this evidence). Honest residuals:
(a) the effect is modest and n=3; (b) title translation is IMPROVED but not
eliminated -- 1 of 3 es greetings still read the section title in English
("Application Information"); the structural fix is delivering TRANSLATED
section labels, noted on bd polyglot-pdf-tupu.2 (the spoken-name delivery
pass touches the same metadata channel).

## Caveats

- One run per language; D2/D3-class events are known to be intermittent.
  Treat single-run defects as EXISTENCE proofs, not rates.
- `model_said` strings are window-attributed transcript chunks; mid-sentence
  truncation at window edges is a capture artifact, not a speech defect.
- zh transcripts show per-character spacing ("外 国人 登记") -- an ASR
  tokenization artifact of the transcription stream, not evidence about the
  spoken audio.
- The English confirm-fixture confound (H1) inflates the ru input-transcription
  chaos; the Russian-utterance garbles (e.g. the spelled-name turn) stand on
  their own.
