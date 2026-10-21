"""The text + TTS pricing tables are complete and sourced (bd polyglot-pdf-wio6m).

WHY THIS FILE EXISTS. A cost dashboard built on a guessed rate is worse than one
with a visible hole: the hole prompts someone to fill it, the guess is believed.
So the rule for these tables is that a number is either VERIFIED against the
live pricing page (and dated in a comment beside it) or explicitly None -- and a
None fails a test until an operator reads the page and fills it in.

TEXT_GENERATION_PRICING was verified against ai.google.dev/gemini-api/docs/pricing
on 2026-10-21 and is complete.

TTS_PRICING_USD_PER_CHAR is complete too: the Chirp 3 HD rate was read from
cloud.google.com/text-to-speech/pricing by the maintainer on 2026-09-14 (the
page would not load for an automated fetch on 2026-09-09) and is dated beside
the row. test_tts_pricing_is_filled_in below is the gate that keeps every tier
verified: a new tier added as None fails it until its rate is sourced.

The Live table (GEMINI_PRICING_BY_FAMILY) is a separate product and is NOT
covered here -- it prices the native-audio Live endpoint, not generate_content.
"""

import pytest

from backend.config import (
    TEXT_GENERATION_PRICING,
    TTS_PRICING_USD_PER_CHAR,
    get_text_generation_pricing,
    tts_voice_tier,
)

# Every text model must price all three columns: an input rate without a cached
# rate silently bills cache hits at full price.
REQUIRED_TEXT_COLUMNS = {"text_input", "cached_input", "text_output"}

# Per-1M list prices as read from the page on 2026-10-21 (Standard paid tier).
# Held here as the HUMAN-READABLE source figures so a drifted table fails
# against the number someone actually verified, not against itself.
EXPECTED_PER_1M = {
    # The lite default (MODEL_LABELING / TRANSLATION_VERIFY_BT_MODEL).
    "gemini-3.1-flash-lite": {"text_input": 0.25, "cached_input": 0.025, "text_output": 1.50},
    # The lite-tier outage fallback (TextAIGemini.DEFAULT_FALLBACK_MODELS).
    "gemini-3.5-flash-lite": {"text_input": 0.30, "cached_input": 0.03, "text_output": 2.50},
    "gemini-2.5-flash": {"text_input": 0.30, "cached_input": 0.03, "text_output": 2.50},
    "gemini-2.5-flash-lite": {"text_input": 0.10, "cached_input": 0.01, "text_output": 0.40},
    # <=200k-token prompt tier (this app's validator/translation prompts never
    # approach 200k); the page's >200k tier is not carried here.
    "gemini-2.5-pro": {"text_input": 1.25, "cached_input": 0.125, "text_output": 10.00},
}

_PER_1M = 1_000_000

# The verified per-1M figures expressed as per-token rates -- the shape the
# lookup returns. Derived from EXPECTED_PER_1M so there is still exactly ONE
# place a verified number is written down.
EXPECTED_PER_1M_AS_RATES = {
    model: {column: figure / _PER_1M for column, figure in columns.items()}
    for model, columns in EXPECTED_PER_1M.items()
}


def test_text_pricing_covers_the_models_the_chain_uses():
    """The verified table is exactly the verified model set."""
    assert set(TEXT_GENERATION_PRICING) == set(EXPECTED_PER_1M), (
        "TEXT_GENERATION_PRICING drifted from the verified model set; "
        "re-verify against the pricing page and update EXPECTED_PER_1M too."
    )


def test_every_model_a_text_client_can_select_by_default_is_priced():
    """Derived from the code, not a hand list: every default text model id
    (the settings knobs that build TextAIGemini clients, plus the adapter's own
    default and fallback chain) prices to a row. An unpriced default would ship
    cost_estimate_usd=None on every call it serves."""
    from backend.adapters.text_ai_gemini import TextAIGemini
    from backend.config import Settings
    import inspect

    s = Settings()
    selectable = {
        s.MODEL_LABELING,
        s.TRANSLATION_VERIFY_BT_MODEL,
        s.VALIDATOR_PRO_MODEL,
        s.OPTION_TRANSLATION_MODEL,
        inspect.signature(TextAIGemini.__init__).parameters["model"].default,
        *TextAIGemini.DEFAULT_FALLBACK_MODELS,
    }
    unpriced = sorted(m for m in selectable if get_text_generation_pricing(m) is None)
    assert not unpriced, f"default text model(s) with no pricing row: {unpriced}"


@pytest.mark.parametrize("model", sorted(EXPECTED_PER_1M))
def test_text_pricing_row_is_complete(model):
    """No column is missing from a text-pricing row."""
    row = TEXT_GENERATION_PRICING[model]
    missing = REQUIRED_TEXT_COLUMNS - set(row)
    assert not missing, f"{model} is missing rate column(s): {sorted(missing)}"


@pytest.mark.parametrize(
    "model,column",
    [(m, c) for m in sorted(EXPECTED_PER_1M) for c in sorted(REQUIRED_TEXT_COLUMNS)],
)
def test_text_pricing_matches_the_verified_page_figure(model, column):
    """Each per-token rate equals the verified per-1M figure over 1M.

    Parametrized per COLUMN, not per model: a single assertion over a whole row
    would go red for one wrong column and tell you nothing about the other two.
    """
    expected = EXPECTED_PER_1M[model][column] / _PER_1M
    actual = TEXT_GENERATION_PRICING[model][column]
    assert actual == pytest.approx(expected, rel=1e-9), (
        f"{model}.{column}: table has {actual}, verified page figure implies "
        f"{expected} ({EXPECTED_PER_1M[model][column]} per 1M)"
    )


@pytest.mark.parametrize("model", sorted(EXPECTED_PER_1M))
def test_text_pricing_rates_are_positive(model):
    """A zero or negative rate would silently zero out a cost total."""
    for column, rate in TEXT_GENERATION_PRICING[model].items():
        assert rate > 0, f"{model}.{column} is not a positive rate: {rate}"


@pytest.mark.parametrize(
    "model_id,expected_key",
    [
        ("gemini-3.1-flash-lite", "gemini-3.1-flash-lite"),
        ("gemini-3.1-flash-lite-preview-09-2025", "gemini-3.1-flash-lite"),
        ("gemini-3.5-flash-lite", "gemini-3.5-flash-lite"),
        ("gemini-2.5-flash", "gemini-2.5-flash"),
        ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
        # The chain ships dated preview ids; they must bill at the base rate.
        ("gemini-2.5-flash-lite-preview-09-2025", "gemini-2.5-flash-lite"),
        ("gemini-2.5-flash-preview-05-20", "gemini-2.5-flash"),
        # Case-insensitive: model ids arrive from env and config alike.
        ("GEMINI-2.5-FLASH-LITE", "gemini-2.5-flash-lite"),
    ],
)
def test_lookup_resolves_concrete_model_ids(model_id, expected_key):
    """A dated/preview id resolves to its base model's row.

    The lite id is the sharp case: it starts with "gemini-2.5-flash" too, so a
    naive prefix scan would bill lite calls at flash rates -- 3x the input rate
    and 6x the output rate. The longest-key-first ordering is what prevents it,
    and this parametrization is what pins that ordering.

    Compared BY VALUE, not by identity. An earlier version asserted `is` and
    passed alone but failed in the full suite: backend.config is reachable under
    two module identities during a whole-suite run, so the row returned by the
    lookup and the row read from the table were equal dicts from different
    module copies. Identity was never the contract -- "resolves to the right
    RATES" is -- so the assertion, not the production code, was wrong.
    """
    actual = get_text_generation_pricing(model_id)
    assert actual == EXPECTED_PER_1M_AS_RATES[expected_key], (
        f"{model_id} resolved to {actual}, expected the {expected_key} row"
    )
    # Guard the discrimination too: equality alone would pass if the row the
    # lookup could WRONGLY have picked held the same numbers. The rivals are
    # the other keys that are also a prefix of this id -- exactly the set the
    # longest-key-first scan chooses between (gemini-2.5-flash vs
    # gemini-2.5-flash-lite for a lite id). Rows outside that set may share
    # prices legitimately (gemini-3.5-flash-lite and gemini-2.5-flash list
    # identically), and are not candidates for this id anyway.
    rivals = {
        k: v for k, v in TEXT_GENERATION_PRICING.items()
        if k != expected_key and model_id.lower().startswith(k)
    }
    assert all(actual != row for row in rivals.values()), (
        f"{model_id} resolved to a row indistinguishable from a rival prefix "
        "match's; this test can no longer tell the rows apart"
    )


@pytest.mark.parametrize("model_id", [None, "", "gemini-9.9-unknown", "claude-3"])
def test_lookup_returns_none_for_unknown_models(model_id):
    """An unknown model yields None, never a fallback row.

    Deliberately unlike the Live table's DEFAULT_PRICING_FAMILY: for a cost
    dashboard, an explicit gap beats a confident wrong number.
    """
    assert get_text_generation_pricing(model_id) is None


@pytest.mark.parametrize(
    "voice_name,expected",
    [
        ("en-US-Chirp3-HD-Algieba", "Chirp3-HD"),
        ("es-ES-Chirp3-HD-Kore", "Chirp3-HD"),
        # The locale-default fallback rung leaves the voice unnamed.
        ("", None),
        (None, None),
        # A tier with no row must not be silently priced as Chirp3-HD.
        ("en-US-Neural2-A", None),
    ],
)
def test_tts_voice_tier_resolution(voice_name, expected):
    """The billed tier is derived from the RESOLVED voice name."""
    assert tts_voice_tier(voice_name) == expected


def test_tts_pricing_table_has_a_chirp3_hd_row():
    """The one tier this app synthesizes with is represented in the table."""
    assert "Chirp3-HD" in TTS_PRICING_USD_PER_CHAR, (
        "every voice this app can resolve is a Chirp3-HD voice; the table must "
        "carry that tier"
    )


def test_tts_pricing_is_filled_in():
    """Every TTS tier carries a verified, positive per-character rate.

    A tier whose rate is None is one nobody has verified against the live
    pricing page yet, and a None row makes every clip on that tier bill as
    cost_estimate_usd=None. This test refuses that state: add the rate with a
    dated, sourced comment in the shape the Gemini table uses (never a number
    from memory -- an unsourced rate quietly mis-bills every spell-back, notice
    and intro clip), and the test goes green on its own.
    """
    unverified = [tier for tier, rate in TTS_PRICING_USD_PER_CHAR.items() if rate is None]
    assert not unverified, (
        "UNVERIFIED TTS rate(s): " + ", ".join(sorted(unverified)) + ". "
        "read the live page (cloud.google.com/text-to-speech/pricing) and fill "
        "the rate in with a dated, sourced comment -- see the module docstring."
    )


@pytest.mark.parametrize("tier", sorted(TTS_PRICING_USD_PER_CHAR))
def test_tts_rate_is_positive_once_filled(tier):
    """Any FILLED TTS rate is a positive per-character number.

    Skips while the rate is the documented None, so this guard starts working
    the moment the rate lands rather than needing to be remembered then.
    """
    rate = TTS_PRICING_USD_PER_CHAR[tier]
    if rate is None:
        pytest.skip(f"{tier} rate is the documented unverified None")
    assert rate > 0, f"{tier} rate is not positive: {rate}"
    # Per CHARACTER, so a plausible rate is tiny. A number in the per-1M range
    # pasted in unconverted would be off by a factor of a million.
    assert rate < 0.01, (
        f"{tier} rate {rate} looks like a per-1M-character figure, not "
        "per-character; divide by 1_000_000"
    )
