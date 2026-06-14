# d24n root cause + fix verification (bd polyglot-pdf-jnjj.1 / d24n)

The silent `tool_callback_error` / `error_type=TypeError` that fired ~2-3x per
20-question gemini-2.5 run on `update_form_fields` (captured in the wyhh cost
matrix `costs_2.5_*.meta.json` `errors` arrays), root-caused and fixed.

## Smoking gun (captured live, DEV_LOGGING on)

Captured by running the cost instrument on the model that exhibits it, with the
`backend/.env.DEV` marker present so the adapter prints the full traceback
(production redacts the message to the exception type for PII safety):

```
backend/.venv/Scripts/python.exe scripts/spikes/measure_form_session_costs.py \
    --model 2.5 --arm section-reset --path happy
```

Traceback (PII-free frames):

```
File ".../backend/services/callback_handler.py", line 713, in _build_update_fields_response
    opts_sample = ", ".join(valid_options[:3])
TypeError: sequence item 0: expected str instance, dict found
TOOL CALLBACK ERROR (PATH 2): update_form_fields
[error] tool_callback_error  tool=update_form_fields  (caught + swallowed by the
                             event.tool_call path in live_ai_gemini.py)
```

## Root cause

`backend/utils/field_validator.py::_validate_checkbox` built its `ValidationError`
with the field's RAW `options` list as `valid_options`. The generated form-kits
store options as `{value, label}` DICTS, so dicts reached
`", ".join(valid_options[:3])` in `_build_update_fields_response`. (Its membership
check `v not in options` was also comparing selected strings against dict options,
so dict-option checkbox validation never matched -- a second latent bug.)
`_validate_select` already extracted bare string values; `_validate_checkbox` did
not, and a stale formatter comment ("valid_options is now a list of strings")
masked the gap. It is intermittent because it only triggers when a dict-option
checkbox/select field receives an INVALID value (~2-3 such fields per 20q run),
which is why a static read of the success path never surfaced it.

## Fix

- `_option_values()` helper extracts bare strings from `{value,label}` dicts;
  `_validate_checkbox` uses it for BOTH the membership check and `valid_options`;
  `_validate_select` refactored onto it.
- Defensive `str()` coercion at `_build_update_fields_response` so a stray non-str
  option can never crash the formatter again.

## Verification (post-fix, same cell)

Re-running the exact cell that captured the TypeError, after the fix:

| Metric                                   | Before fix      | After fix (this run) |
|------------------------------------------|-----------------|----------------------|
| `tool_callback_error` TypeError events   | 2-3 / run       | **0**                |
| meta `errors` array                      | non-empty       | **`[]`** (empty)     |
| confirmed fields (client_confirmed)      | 13-15 / 20      | **18 / 20**          |

Run summary line: `run total: 193621 tokens, $0.1525; evictions detected: 3;
confirmed fields: 18/20`. Both d24n / jnjj.1 exit criteria met (C1: zero TypeError
events + `errors: []`; C2: confirmed rate >= 18/20). The raw `costs_*.meta.json`
sidecar is reproducible from the command above and is intentionally not committed
(the `data/` dir holds many such run artifacts); this table is the durable record.
```
