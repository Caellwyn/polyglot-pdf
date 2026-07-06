# Authoring few-shot exemplars

New-vocabulary few-shot exemplars for the PDF -> FormSchema extraction prompt
(bd polyglot-pdf-h76m.4, P1.2). Each file here is a small, hand-authored **v2**
FormSchema shown to the model so it imitates the new (schema-v2) conventions --
NOT the target form's content.

## `v2_new_vocabulary_exemplar.json`

A minimal but complete v2 schema teaching the four load-bearing conventions the
old (v1) contract got wrong:

- **`checkbox_group`** for a multi-select question (`reasons`): one logical field,
  per-box identity on `options[].pdf_field_name`, no field-level `pdf_field_name`.
- **Semantic slug option values** (`employment`, `family`, `other`, `single`,
  `married`) minted from the label -- never a widget-leaf identifier or a raw
  on-state.
- **`radio` with shared field name** (`marital_status`): one field-level
  `pdf_field_name`, each option distinguished by `pdf_on_value`.
- **Membership / equality operators** on option slugs: `spouse_name` uses
  `show_if equals married` (radio trigger); `other_reason_text` uses
  `require_if includes other` (checkbox_group trigger -- the v2 replacement for
  the retired equals-means-membership hack).

**Invariant:** every exemplar in this directory MUST pass
`FormSchema.model_validate` under the strict v2 rules AND lint clean
(`backend/services/schema_lint.lint_schema` -> 0 errors). The exemplar is a
convention teacher; a broken one would teach the model to emit broken schemas.
`tests/test_schema_contract_sync.py` pins the canonical contract example; this
exemplar is checked the same way by `tests/test_fewshot_exemplars.py`.
