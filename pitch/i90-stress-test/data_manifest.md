# Run-artifact manifest -- I-90 stress test

Each row = one live run. Full per-question CSVs + meta.json (prompt curves, tool
attribution, per-field fill detail) live under scripts/spikes/data/ in the repo;
these summary.json files carry the headline metrics. Total series: 25 runs, $39.29.

| file | phase | path | events | reactivity | lang | all-in $ | fill acc | Qs |
|---|---|---|---|---|---|---|---|---|
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T054615Z.summary.json | E0 pilot | happy | none | - | en | 0.189541 | 0.7 | 10 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T055241Z.summary.json | E0 pilot | happy | none | - | en | 0.250448 | 1.0 | 10 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T055600Z.summary.json | E1 happy | happy | none | - | en | 2.425401 | 0.8761 | 113 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T061257Z.summary.json | E1 happy | happy | none | - | en | 2.416718 | 0.8053 | 113 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T062904Z.summary.json | E1 happy | happy | none | - | en | 2.486589 | 0.8938 | 113 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T064929Z.summary.json | E2 realistic | happy | standard | - | en | 1.094919 | 0.6637 | 113 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T090804Z.summary.json | E2 realistic | happy | standard | - | en | 3.460401 | 0.6372 | 113 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T092808Z.summary.json | E2 realistic | happy | standard | - | en | 2.931827 | 0.8938 | 113 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T100819Z.summary.json | E2 realistic | happy | standard | - | en | 3.848147 | 0.5841 | 113 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T143305Z.summary.json | E4 reactivity | happy | none | nav-by-name | en | 0.376453 | 0.9375 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T143544Z.summary.json | E4 reactivity | happy | none | nav-change-value | en | 0.395862 | 1.0 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T143826Z.summary.json | E4 reactivity | happy | none | nav-vague-address | en | 0.382364 | 1.0 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T144107Z.summary.json | E4 reactivity | happy | none | nav-first-field | en | 0.394333 | 1.0 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T144351Z.summary.json | E4 reactivity | happy | none | recall-value | en | 0.33765 | 0.9375 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T144624Z.summary.json | E4 reactivity | happy | none | recall-empty | en | 0.352038 | 1.0 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T144901Z.summary.json | E4 reactivity | happy | none | recall-option | en | 0.352335 | 1.0 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T145139Z.summary.json | E4 reactivity | happy | none | recall-progress | en | 0.306098 | 1.0 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T145654Z.summary.json | E4 reactivity | happy | none | nav-change-value | en | 0.368446 | 0.9375 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T145942Z.summary.json | E4 reactivity | happy | none | nav-vague-address | en | 0.397026 | 0.875 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T150220Z.summary.json | E4 reactivity | happy | none | nav-first-field | en | 0.368459 | 0.9375 | 16 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T150504Z.summary.json | E6 Spanish | happy | none | - | es | 0.202587 | 1.0 | 10 |
| costs_i90-full_2.5_dti_cont_comp_happy_20260714T150650Z.summary.json | E6 Spanish | happy | none | - | es | 2.65965 | 0.885 | 113 |
| costs_i90-full_2.5_dti_cont_comp_unhappy_20260714T102843Z.summary.json | E3 unhappy | unhappy | unhappy | - | en | 2.748069 | 0.6903 | 113 |
| costs_i90-full_2.5_dti_cont_comp_unhappy_20260714T132220Z.summary.json | E3 unhappy | unhappy | unhappy | - | en | 5.3825 | 0.7522 | 113 |
| costs_i90-full_2.5_dti_cont_comp_unhappy_20260714T135542Z.summary.json | E3 unhappy | unhappy | unhappy | - | en | 5.164852 | 0.5841 | 113 |
