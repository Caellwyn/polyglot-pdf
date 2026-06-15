# Gemini 2.5 native-audio Live: the early-turn `1011 Internal error` is caused by an *incomplete* tool declaration under tool-soliciting prompts -- not by transient server errors, and not by the absence of tools

*A reproducible, wire-verified diagnosis. Tested 2026-06-15 against the Gemini
Live API via the `google-genai` Python SDK 2.8.0, default `api_version`
(`v1beta`), on `gemini-2.5-flash-native-audio-preview-12-2025`.*

## TL;DR

On `gemini-2.5-flash-native-audio-preview-12-2025`, a Live session reliably
closes with a WebSocket `1011 Internal error` **at an early turn boundary**
(in our data, after the 1st or 2nd clean turn -- surviving turn 1 does NOT mean
you are safe) **when BOTH of these hold**:

1. the `tools` you send contain a **structurally incomplete `function_declaration`**
   -- e.g. a declaration that has a `name` but **no `parameters` schema**; and
2. the session is **soliciting tool use** -- a system instruction + prompts that
   put the model in a position to call a tool.

Remove **either** condition and the crash goes away:

- Omitting `tools` entirely, sending `tools: []`, sending
  `tools: [{functionDeclarations: []}]`, or sending **fully-formed** declarations
  (name + typed `parameters`) all **survive** -- even under tool-soliciting
  prompts.
- The *same* incomplete declaration under a **non-soliciting** persona ("you're a
  pirate, just chat") **survives**.

So the popular guess "you must always pass a tools array (even an empty one)" is
**half right for the wrong reason**: an empty array is safe, but so is omitting
tools -- because the trigger is not absence, it is a *malformed declaration the
model is then asked to use*. The crash is **probabilistic** (~80% for a single
name-only declaration), not 100%, which is exactly why it reads as "flaky 2.5."
The sibling model `gemini-3.1-flash-live-preview` does not exhibit it.

**Practical rule:** if you declare tools, declare them *completely* (every
`function_declaration` gets a real `parameters` schema). A half-populated
declaration is worse than no declaration at all.

## Why this was hard to see

Two confounds buried it for weeks:

1. **The popular SDK collapses `tools=[]` to no-tools before the wire.** In
   `google-genai` the Python `connect()` path does (roughly)
   `model_copy(update={'tools': None})` then `if config.tools:` -- an empty list
   is falsy, so a typed `LiveConnectConfig(tools=[])` reaches the server with **no
   `tools` key at all**. You cannot test "empty tools array" through the typed
   config object; it is silently identical to omitting it. A `config.model_dump()`
   will show `tools: []` while the wire carries nothing -- misleading.
2. **Wrappers/adapters often inject a fallback stub.** Our own adapter, when given
   no tools, injected a *name-only* stub (`[{function_declarations:[{name:...}]}]`).
   That stub is exactly the malformed shape that triggers the crash -- so "we sent
   no tools" actually meant "we sent an incomplete declaration," and the bug got
   mis-attributed to tool *absence*.

To get past both, the experiment **wrapped the SDK websocket `send`** to (a)
capture the exact `setup` packet that reached the server and (b) inject wire
shapes the typed config cannot express. Every cell below is reported against the
`tools` value **actually on the wire**, not the config object.

## Problem

A voice app streams mic audio to a Gemini Live native-audio model and lets the
model drive via tool calls. Production was stable, but every stripped-down probe
died with `1011` within the first turn or two on 2.5, while the same probe ran
fine on 3.1. For weeks this was written off as "2.5 is unstable / transient
Google-side errors," which blocked all measurement because no probe survived.

## Observations

1. The crash is **probabilistic, not deterministic** -- a single name-only
   declaration under soliciting prompts crashed ~80% of sessions (24/30), not
   100%. (An earlier 10/10 run was a temporal cluster; widening N revealed the
   true rate. This non-determinism is the source of the "flaky" reputation.)
2. It is **model-specific** to 2.5 native-audio; 3.1 flash-live never crashed in
   any cell.
3. It is **independent of context-window / compression config** -- present with
   compression off, inert, and actively firing, identically.
4. It needs an **incomplete declaration on the wire** -- complete declarations,
   empty arrays, and omission are all safe.
5. It needs **tool solicitation** -- the same incomplete declaration is safe when
   the prompts/system-instruction do not invite tool use.

The crash lands at an **early turn boundary**: the first turn (and sometimes a
second) is processed and the model responds, then the socket closes with `1011`
as that turn completes. In our data (the name-only crash cell, 24 crashes) the
close happened after the 1st clean turn in 67% of crashes and after the 2nd in
33% -- so a single-turn probe that survives is NOT proof of safety.

## Evidence

Wire-verified cell matrix on `gemini-2.5-flash-native-audio-preview-12-2025`,
`google-genai` 2.8.0, `v1beta`, single endpoint, 2026-06-15. Real synthesized
audio, explicit activity signals, 3 turns/session. "wire `tools`" is the exact
`setup.tools` captured leaving the SDK. "form" persona = a form-filling system
instruction + answer prompts (solicits tool use); "pirate" = "just chat, don't
use tools."

| wire `tools` shape | persona | N | crash rate | close |
|---|---|---:|---:|---|
| omitted (no key) | form | 10 | **0%** | -- |
| `[]` (true empty list) | form | 5 | **0%** | -- |
| `[{functionDeclarations: []}]` | form | 5 | **0%** | -- |
| 1 fully-typed declaration | form | 10 | **0%** | -- |
| full production tool set (5, typed) | form | 10 | **0%** | -- |
| **1 name-only declaration** (no params) | **form** | **30** | **80%** | `1011` |
| **2 name-only declarations** (no params) | **form** | **24** | **33%** | `1011`/`1008` |
| 1 name-only declaration (no params) | **pirate** | 5 | **0%** | -- |
| 1 fully-typed declaration | pirate | 5 | **0%** | -- |
| 3.1 flash-live, any shape | form | -- | **0%** | -- |

(The 2-name-only row is N=24, not 25: one session was excluded because it failed
with a *local* `ConnectionResetError` before reaching the server -- not a Gemini
`1011`/`1008`. Counting only sessions that actually reached the wire, the rate is
8/24 = 33%.)

Reading the matrix:

- **Completeness, not presence, is the lever.** Omit / `[]` / empty-decls /
  typed-1 / full all survive; only the *name-only* (incomplete) shapes crash.
  "Always pass `[]`" works -- but only because `[]` is not a malformed
  declaration, not because presence matters.
- **Solicitation is the second, necessary factor.** The identical name-only
  declaration crashes 80% under form prompts and **0%** under "just chat" prompts.
  Broken tools are only dangerous when the model is actually steered to use them.
  (Caveat: the "chat" cell changed BOTH the system instruction *and* the prompts,
  and that instruction explicitly said "do not use tools" -- so this isolates
  "tool use is solicited" vs "tool use is suppressed" as a bundle, not the system
  instruction and the prompt wording separately. The direction is clear; the
  precise sub-cause within "solicitation" is not separated. N=5 here is
  directional, not a rate.)
- **It is a rate, not a certainty.** 80% (name-only) and 33% (two name-only) --
  both well short of 100%, consistent with a server-side path that *sometimes*
  faults on the incomplete declaration during end-of-turn handling.
- **Compression, `api_version` (`v1alpha`), and model aliases were all ruled out**
  in earlier runs; none change the outcome. 3.1 is unaffected throughout.
- *(The 2-name-only cell crashing LESS than the 1-name-only cell is unexplained
  and noted honestly; both are "incomplete," both crash at a substantial rate,
  and the count effect was not the focus.)*

## Hypothesis

During end-of-turn state reconciliation, the 2.5 native-audio backend appears to
attempt to bind/validate the declared functions against the tool-use it is being
steered toward. A declaration that is **present but missing its `parameters`
schema** sometimes faults this path, and the server aborts with a generic `1011`
at the turn boundary. The fault requires the model to be *engaging* the tool
machinery (solicitation), which is why a "just chat" persona with the same broken
declaration is safe, and why omission / empty arrays (nothing to validate) and
complete declarations (valid to bind) are both safe. This is black-box inference
-- we have no server stack traces -- but the two controlling inputs (declaration
completeness x solicitation) are unambiguous and wire-verified.

## Solution / recommendation

**If you send tool declarations to 2.5 native-audio, send COMPLETE ones** -- every
`function_declaration` gets a real `parameters` schema (and type every required
parameter; see the adjacent caveat). Concretely:

- **Declaring tools? Make them complete.** A `name`-only declaration is the
  hazard. This is the common real-world trigger: a fallback/placeholder tool, a
  hand-written minimal repro, or a wrapper that injects a stub.
- **Not using tools? Omit `tools` entirely, or send `tools: []`** -- both are
  safe. There is no need to invent a tool. ("Always pass an empty list" is safe
  but not necessary; "never send a half-formed declaration" is the real rule.)
- **Probes/repros must mirror the deployed config**, including complete tool
  declarations -- a stripped-down probe is a *different system* whose failures do
  not transfer (and may, via a stub, manufacture this very crash).

Conceptual setup (Python, `google-genai` 2.8.x) -- a COMPLETE declaration:

```python
from google import genai
from google.genai import types

client = genai.Client()  # default api_version (v1beta)

config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    # Safe: a COMPLETE declaration (name + typed parameters). A name-only
    # declaration here is what triggers the 1011 under tool-soliciting prompts.
    # (Sending no tools at all, or tools=[], is equally safe if you don't need them.)
    tools=[types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="update_form_field",
            description="Record a value for a field.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "field_id": types.Schema(type="STRING"),
                    "value": types.Schema(type="STRING"),
                },
                required=["field_id", "value"],
            ),
        ),
    ])],
)

async with client.aio.live.connect(
    model="gemini-2.5-flash-native-audio-preview-12-2025",
    config=config,
) as session:
    ...
```

### Adjacent caveat (different model, different bug) -- type every required param

While isolating the above we found a **separate** issue in the same `tools` block:
under `google-genai` 2.8.0, **`gemini-3.1-flash-live` rejects a tool call when a
*required* parameter is declared with no type**, verbalizing "I had an issue
processing that value" instead of emitting the function call. Typing the parameter
(e.g. `STRING`) restored reliable tool-calling. `gemini-2.5` tolerated the untyped
param. Net rule across both models: **declare tools completely, and give every
required parameter an explicit type.**

### What this does NOT explain

`gemini-2.5` native-audio also has a **separate, lower-rate intermittent** failure
mode -- an occasional no-audio turn or mid-session close unrelated to tool shape
(we saw a stray `1008` even in a with-tools run). The completeness rule removes
the early-turn `1011` driven by malformed declarations; it does not make the audio
path perfectly reliable. Budget a reconnect/retry path for the residual.

## Reproduction notes

- SDK `google-genai` 2.8.0 (Python), default transport / `api_version` (v1beta),
  single endpoint, 2026-06-15. Model `gemini-2.5-flash-native-audio-preview-12-2025`.
- To prove the wire shape you must capture below the typed config (the SDK erases
  `tools=[]`): wrap the websocket `send` and read the first `{"setup": {...}}`
  packet. Mutating that dict before forwarding is also how you put a true `[]` or
  `[{functionDeclarations: []}]` on the wire.
- The decisive controls: (a) one **name-only** declaration vs one **fully-typed**
  declaration under the same soliciting prompts -- name-only crashes ~80%, typed
  0%; (b) the **same** name-only declaration under "just chat" prompts -- 0%.
- Crash is a **rate** -- run N>=20 to characterize it; a handful of sessions can
  show all-crash or all-survive by chance.
- **Single-endpoint / single-day caveat:** the Live API is geo-load-balanced and
  this is a preview model; behavior may differ by region/date and Google may
  change it. Re-verify against the live endpoint before relying on the exact
  strings or rates.

*Raw per-session evidence (every cell, with the captured wire `tools`):
`scripts/spikes/data/diag_1011_tools_combined.json` and the per-batch
`diag_1011_tools_batch{1,2,3}.json` / `..._rate.json`. Probe:
`scripts/spikes/diag_native_audio_1011_tools.py`.*
