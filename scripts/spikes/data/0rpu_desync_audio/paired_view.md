# Paired view -- live-model text track vs Cloud STT of the audio

247 generations across 9 runs.

- **14 HARD MISMATCHES** -- both tracks spelled, and they
  differ. These are the defect.
- 31 rows where only the TEXT track spelled (the model
  asked but the audio for that generation carried no spelling) --
  normal, since the spelling lands on the neighbouring generation.

Full table: `paired_view.csv`. Rebuild: `python build_paired_view.py`.

## HARD MISMATCHES -- audio spelled something the text did not

| run | gen | field | AUDIO spelled | text nearby | conf | wav |
|---|---|---|---|---|---|---|
| night_runRUDE | 8 | name_1a_middle | **JOHN** | JOHNSON JOSHUA | 0.649 | `fss_msgevm9j_usut9zmd_a1_g8_s547.wav` |
| night_runRUDE | 10 | name_1a_last | **JOHN** | JOHNSON | 0.768 | `fss_msgevm9j_usut9zmd_a1_g10_s644.wav` |
| reanchor_control | 9 | name_1a_middle | **JOHN** | JOHNSON JOSHUA | 0.874 | `fss_msgy59zk_m7hpmarr_a1_g9_s601.wav` |
| reanchor_control | 11 | name_1a_last | **JOHN** | JOHNSON MARIA | 0.86 | `fss_msgy59zk_m7hpmarr_a1_g11_s706.wav` |
| reanchor_control | 15 | name_1b_middle | **JOHN** | JOSE SMITH | 0.867 | `fss_msgy59zk_m7hpmarr_a1_g15_s1011.wav` |
| spellback_comma | 7 | name_1a_first | **JOHN** | - | 0.55 | `fss_msh3pk9m_eilsn0ti_a1_g7_s465.wav` |
| spellback_comma | 11 | name_1a_last | **JOHN** | - | 0.498 | `fss_msh3pk9m_eilsn0ti_a1_g11_s684.wav` |
| spellback_comma | 13 | name_1b_first | **MARIA** | RIA | 0.887 | `fss_msh3pk9m_eilsn0ti_a1_g13_s814.wav` |
| spellback_comma | 15 | name_1b_middle | **JOH** | - | 0.478 | `fss_msh3pk9m_eilsn0ti_a1_g15_s951.wav` |
| spellback_comma | 17 | name_1b_last | **SMITH** | ITH | 0.898 | `fss_msh3pk9m_eilsn0ti_a1_g17_s1082.wav` |
| spellback_echo_once | 5 | us_person_name_ssn_itin | **LORETAJ** | JOHN LORETTAJOHNSON | 0.505 | `fss_mshzqmr2_hb2djp2d_a1_g5_s418.wav` |
| spellback_echo_once | 9 | name_1a_middle | **JOHN** | JOHNSON JOSHUA | 0.864 | `fss_mshzqmr2_hb2djp2d_a1_g9_s628.wav` |
| spellback_echo_once | 11 | name_1a_last | **JOHN** | JOHNSON MARIA | 0.834 | `fss_mshzqmr2_hb2djp2d_a1_g11_s729.wav` |
| spellback_echo_once | 15 | name_1b_middle | **JOHN** | JOSE SMITH | 0.776 | `fss_mshzqmr2_hb2djp2d_a1_g15_s998.wav` |

## How to use this for the spell-back tool

Re-run an arm with the tool enabled, rebuild this view, and compare
`audio_spelled` against `text_spelled` per row. The tool works when
every scoreable spelled row reads `spelling_matches = yes`.

Watch the confidence column: healthy generations score 0.93-0.99 and
corrupted spelled read-backs score 0.34-0.65, so a row that becomes
UNSCOREABLE is not a pass -- it is a row that must be hand-checked.
