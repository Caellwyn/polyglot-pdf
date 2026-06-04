# Why context-window compression is a no-op -- root cause (bd polyglot-pdf-l3a.1)

*Diagnostics run 2026-06-04 against the real Live API. Follows the 45o sweep
(`sweep_compression_window_findings.md`), which found compression did not bound
`prompt_token_count`. This bead asked WHY.*

## Conclusion -- DEAD END. Do not pursue context-window compression again.

**`contextWindowCompression` looks like an unreleased, unsupported STUB: the
google-genai SDK type exists ahead of the server implementation.** That explains every
observation -- it *serializes* (the type is real), the server *accepts* it (the field is
tolerated), and it does *nothing* (no implementation behind it on these models). It is a
**silent no-op on every native-audio Live model reachable on this key**: the prompt token
count crosses the trigger and keeps compounding exactly as with compression off. This is
**not a viable cost path for us** and should not be re-investigated unless Google
announces native-audio support.

What this means going forward:
- **Keep `CONTEXT_COMPRESSION_ENABLED=False`** (the shipped default). The config is
  plumbed and reversible, so IF Google ships native-audio eviction later, the existing
  flag enables it with no code change -- but do not assume that has happened; re-verify
  against the live endpoint first.
- **Do not re-derive this from docs.** Google's best-practices prose actively *claims*
  compression works (25k/8k example); that example is for a cascade model and is
  misleading for native-audio. The SDK type and the docs both describe the *intended*
  API, not what is *implemented* -- see the verification doctrine below.
- The cost lever the `l3a` epic was premised on (compression -> linear cost) is **not
  available** on our model family. Any future cost work must find a different lever
  (e.g. shorter sessions, a different model class if one becomes accessible).

## What each experiment ruled out

| Hypothesis | Probe | Result |
|---|---|---|
| Wrong syntax / config not built | offline SDK serialization | RULED OUT -- serializes to `triggerTokens`/`slidingWindow`/`targetTokens` |
| API rejects our trigger/window values | `diag_compression_connect_boundary.py` (trigger 200->4096) | RULED OUT -- **all ACCEPTED** at connect |
| Wrong API version (preview needs `v1alpha`) | `diag_compression_apiversion.py` | RULED OUT -- **v1alpha == v1beta**, both compound ~7x, neither evicts |
| Only the 3.1 preview is affected | 2.5-native-audio run | RULED OUT -- `gemini-2.5-flash-native-audio-preview-12-2025` also crosses the trigger with **no eviction** |
| Works on a cascade model (native-audio gap) | `diag_compression_cascade.py`, 4 model strings | UNTESTABLE here -- **no cascade Live model reachable** on this key (all `1008`); `models.list()` returns only native-audio models |

## The decisive data

`diag_compression_apiversion.py --trigger 1500 --window 800 --turns 8`, compression ON
for both, only `api_version` differs:

| turn | v1beta prompt | v1alpha prompt |
|--:|--:|--:|
| 1 | 250 | 250 |
| 5 | 1,056 | 1,013 |
| 7 | 1,516 | 1,479 |
| 8 | 1,709 | 1,751 |

Both ~6.8-7.0x growth, both cross the 1500 trigger, neither drops back toward the 800
window. Identical behavior => the API version is not the lever.

2.5-native-audio (trigger 1200): prompt `479 -> 1266` over 6 turns, crossed the trigger,
no eviction -- same shape as 3.1.

## Verification doctrine (the generalizable lesson)

**For any google-genai Live capability question -- does feature X work on model Y, what's
the min/max, is it actually live -- trust ONLY a live-endpoint probe.** Every doc source
failed differently here:

- **Google's own best-practices prose** *confidently claims* compression works, with a
  25k/8k example -- for a model class that example doesn't apply to. Worse than silent:
  confidently stale.
- **The vendored `docs/genai_docs/`** has the claim but no syntax and no
  model-applicability note.
- **Context7** was mangled (as expected) and surfaced one accidental `v1alpha` crumb that
  turned out to be a red herring.
- **The SDK types** happily construct and serialize a config the server ignores -- the
  type system describes the *intended* API, not what's *implemented* on a given model.

Gemini/genai docs and SDK types go stale silently and run ahead of the server. The only
source that did not lie was the endpoint under controlled probes. So: capability /
availability questions get an endpoint probe, not a doc read. (Stored as bd memory
`gemini-capability-questions-need-endpoint-probe`.)

## What would change the conclusion

The one untested branch is a **cascade** Live model (e.g. `gemini-live-2.5-flash-preview`,
the model the docs' compression example uses). It is **not reachable on this key** (all
`1008`), so we could not prove "works on cascade, not native-audio" directly -- we proved
"does not work on either native-audio model we can reach." This does not reopen the path:
even if compression evicts on cascade, **we run native-audio**, where it is inert. The
cascade retest is recorded only so the door isn't left ambiguous, not because it changes
our verdict.

## Harnesses (all throwaway diagnostics, no PII)

- `diag_compression_usage.py` -- drives audio off/on, dumps RAW `usage_metadata`
  (`cached_content_token_count`, `traffic_type`, ...) via the adapter's `_on_raw_usage`
  diagnostic hook. (The hook is a default-None production no-op.)
- `diag_compression_connect_boundary.py` -- accept/reject boundary across (trigger, window).
- `diag_compression_apiversion.py` -- v1beta vs v1alpha eviction comparison.
- `diag_compression_cascade.py` -- compression eviction on a cascade Live model (TEXT turns).
