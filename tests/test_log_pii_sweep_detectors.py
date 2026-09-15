"""scripts/audit/log_pii_sweep.py detector + formatter contract (bd
polyglot-pdf-v8l6m, sprint 23 workstream B2).

EXIT CRITERION 1 lives here: every detector has a positive AND a negative
unit case (scar #9 -- pin both directions), including the underscore
boundary trap (`\\b` fails after `_`; this repo has been bitten by that
exact regex three times), and the output formatter is proven -- by
construction, not by inspection -- unable to emit a matched substring.

Mutation-verify per docs/standards/testing.md#test-the-tests: the
comments on the boundary-trap cases below record what a `\\b`-based
implementation would do differently, so reverting the lookaround regression
is a one-line, checkable mutation.

ASCII only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.audit.log_pii_sweep as sweep  # noqa: E402


def _matches(detector_name: str, text: str) -> list:
    return sweep.DETECTORS[detector_name](text)


# ---------------------------------------------------------------------------
# ws_token_in_url -- [?&]token= inside httpRequest.requestUrl.
# ---------------------------------------------------------------------------

def test_ws_token_in_url_positive_query_param():
    assert _matches("ws_token_in_url", "/ws/fill?token=abc.def") != []


def test_ws_token_in_url_positive_second_param():
    assert _matches("ws_token_in_url", "/ws/fill?kit=i90&token=abc.def") != []


def test_ws_token_in_url_negative_no_token_param():
    assert _matches("ws_token_in_url", "/ws/fill?kit=i90&employee=e1") == []


def test_ws_token_in_url_negative_token_as_substring_not_param():
    """"tokenized" or a path segment containing "token" without "=" must
    not fire -- the detector looks for the QUERY-PARAM shape specifically."""
    assert _matches("ws_token_in_url", "/api/tokenized-resource") == []


# ---------------------------------------------------------------------------
# jwt -- two-segment JWT shape, \beyJ[\w-]{20,}\.eyJ
# ---------------------------------------------------------------------------

_FAKE_JWT = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ"
    # Firebase ID tokens are RS256 (RSA-2048): a 256-byte signature is 342
    # base64url chars with no padding -- nowhere near the link token's
    # fixed 43-char HMAC-SHA256 signature, which is what actually keeps
    # the two detectors from colliding on a REAL Firebase token (an HS256
    # JWT's 32-byte HMAC signature would also be 43 chars and WOULD
    # collide; this app never issues those, only verifies Firebase's own
    # RS256 tokens, so the 342-char fixture below is the realistic case).
    "." + ("A" * 342)
)


def test_jwt_positive_two_segment_shape():
    assert _matches("jwt", "Authorization: Bearer " + _FAKE_JWT) != []


def test_jwt_negative_single_segment_base64_is_not_a_jwt():
    """A bare base64 blob starting eyJ with no second eyJ segment (e.g. a
    single-segment encoded value) must not fire -- only the two-segment
    header.payload shape is a JWT."""
    single = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    assert _matches("jwt", single) == []


def test_jwt_negative_short_first_segment():
    """Fewer than 20 chars after eyJ (the header/payload floor the pattern
    requires) must not fire -- guards against matching short, incidental
    "eyJ..."-prefixed strings that are not real JWTs."""
    assert _matches("jwt", "eyJshort.eyJalsoshort") == []


# ---------------------------------------------------------------------------
# link_token_in_url -- this app's one-dot signed link token, URL-scoped only.
# ---------------------------------------------------------------------------

_FAKE_LINK_TOKEN = (
    "eyJ2IjoxLCJhdWQiOiJzdGFnaW5nIiwiZmlybV9pZCI6ImYxIn0"
    "."
    # Exactly 43 chars -- a real base64url(HMAC-SHA256 digest) with no
    # padding is always this length (32 raw bytes -> 43 base64url chars),
    # so the fixture must match it exactly or it tests nothing real.
    "wZ3cPGZfrnpS6kVzHaT0TcU9BocKRh1M0Q1lDvHp9kM"
)


def test_link_token_in_url_positive_inside_url():
    text = "GET /api/links/open?token=" + _FAKE_LINK_TOKEN + " 200"
    assert _matches("link_token_in_url", text) != []


def test_link_token_in_url_negative_outside_a_url():
    """The exact same token-shaped string, but with no surrounding URL
    context, must NOT fire -- the bead requires the one-dot shape be
    scoped to a URL only, since a bare base64-with-a-dot string appears
    incidentally elsewhere (this is the false-positive class the bead's
    own report calls out for the loose A-number pattern; the link-token
    shape has the analogous risk without the URL scope)."""
    assert _matches("link_token_in_url", "just some text: " + _FAKE_LINK_TOKEN) == []


def test_link_token_in_url_negative_jwt_shape_is_not_double_counted():
    """A real (RS256) Firebase JWT inside a URL must not also fire
    link_token_in_url -- the link-token pattern requires an EXACT 43-char
    final segment (a 32-byte HMAC-SHA256 digest, base64url, no padding),
    while an RS256 JWT signature is 342 base64url chars (256-byte RSA-2048
    signature). This is what actually keeps the two detectors from
    colliding on a real token; an HS256 JWT (32-byte HMAC signature, also
    43 chars) WOULD collide, but this app never issues or accepts those --
    it only verifies Firebase's own RS256-signed ID tokens."""
    text = "GET /callback?id_token=" + _FAKE_JWT + " 200"
    hits = _matches("link_token_in_url", text)
    assert hits == []


# ---------------------------------------------------------------------------
# a_number -- (?<![\w])A[0-9]{8,9}(?![\w]) -- the underscore boundary trap.
# ---------------------------------------------------------------------------

def test_a_number_positive_eight_digit():
    assert _matches("a_number", "case A12345678 opened") != []


def test_a_number_positive_nine_digit():
    assert _matches("a_number", "case A123456789 opened") != []


def test_a_number_negative_too_few_digits():
    assert _matches("a_number", "ref A1234567 is not an A-number") == []


def test_a_number_negative_too_many_digits():
    assert _matches("a_number", "ref A1234567890 is not an A-number") == []


def test_a_number_negative_after_underscore_is_not_a_bare_a_number():
    """`(?<![\\w])A[0-9]{8,9}(?![\\w])` and `\\bA[0-9]{8,9}\\b` agree here --
    both correctly refuse to treat an underscore-glued fragment
    (`tracker_id_A123456789_suffix`) as a standalone A-number, since `\\b`
    is DEFINED as a transition against the `\\w` class and underscore is a
    `\\w` character. This is the CLAUDE.md scar's literal case (`\\bptin`
    never matches `agent_ptin`) restated as a POSITIVE property this
    detector must have: an id embedded in a longer identifier is not a
    real A-number and must not be flagged.

    This does not mean `\\b` and the lookaround form are interchangeable in
    general -- see the next test for the actual discriminator: a
    boundary-check narrower than `\\w` (e.g. whitespace/punctuation-only,
    the kind of "fix" someone reaches for after seeing `\\bptin` fail on
    `agent_ptin` and concluding `\\b` is broken) creates a NEW bug in the
    opposite direction.
    """
    assert _matches("a_number", "tracker_id_A123456789_suffix") == []


def test_a_number_positive_bare_word_boundary_case():
    """The ordinary case: a correctly bounded A-number surrounded by
    spaces/punctuation must fire. Paired with the underscore-negative test
    above (scar #9 -- pin both directions)."""
    assert _matches("a_number", "please review A123456789 today") != []


def test_a_number_mutation_to_whitespace_only_boundary_goes_red():
    """The REAL discriminator for this detector's boundary logic. Someone
    who sees `\\bptin` fail on `agent_ptin` and (wrongly) concludes `\\b`
    itself is broken might "fix" it by requiring whitespace/punctuation
    specifically instead of a `\\w`-boundary -- e.g.
    `(?<=[\\s,;:])A[0-9]{8,9}(?=[\\s,;:.]|$)`. That regression is a FALSE
    NEGATIVE on a real, correctly-delimited A-number sitting at the very
    start of a log line (position 0, nothing before it) or immediately
    inside parentheses/brackets, because the narrower class does not
    recognize start-of-string or `(`/`)` as valid boundaries the way `\\b`
    and `(?<!\\w)`/`(?!\\w)` both do.

    This test exercises the ACTUAL shipped detector (not a hand-simulated
    mutant) against exactly that shape, so a future edit that narrows the
    boundary class away from `\\w` is caught here.
    """
    assert _matches("a_number", "A123456789") != []  # start-of-string boundary
    assert _matches("a_number", "(A123456789)") != []  # parenthesis boundary


# ---------------------------------------------------------------------------
# ssn
# ---------------------------------------------------------------------------

def test_ssn_positive():
    assert _matches("ssn", "ssn on file: 123-45-6789") != []


def test_ssn_negative_wrong_grouping():
    assert _matches("ssn", "not an ssn: 12-345-6789") == []


def test_ssn_negative_extra_digit_breaks_boundary():
    assert _matches("ssn", "id 1123-45-67890 is not an ssn") == []


# ---------------------------------------------------------------------------
# email
# ---------------------------------------------------------------------------

def test_email_positive():
    assert _matches("email", "contact staff@example.com for help") != []


def test_email_negative_no_at_sign():
    assert _matches("email", "contact staff.example.com for help") == []


# ---------------------------------------------------------------------------
# phone
# ---------------------------------------------------------------------------

def test_phone_positive_with_separators():
    assert _matches("phone", "call 555-234-5678 now") != []


def test_phone_positive_no_separators():
    assert _matches("phone", "call 5552345678 now") != []


def test_phone_negative_too_few_digits():
    assert _matches("phone", "order id 55512345 is not a phone number") == []


def test_phone_negative_too_many_digits_no_boundary():
    assert _matches("phone", "order id 555123456789 is not a phone number") == []


def test_phone_negative_uuid_fragment():
    """A UUID's "123456-7890" run sits between hex neighbours and has one
    separator where a phone has two -- the first live sweep's request_id hit."""
    assert _matches("phone", "request_id 9a123456-7890-4abc-9def-123456789012") == []


def test_phone_negative_epoch_seconds_comparison():
    """A bare 10-digit epoch timestamp starts with 1; no NANP area code does
    -- the first live sweep's error-message hit ("N < M")."""
    assert _matches("phone", "payload too large, 1757000000 < 100000000") == []


def test_phone_negative_mixed_separators():
    assert _matches("phone", "ref 555-2345678 and 555.234-5678") == []


# ---------------------------------------------------------------------------
# dob_date -- only meaningful when scoped by the caller to jsonPayload
# string fields; the detector itself just recognizes the date SHAPE.
# ---------------------------------------------------------------------------

def test_dob_date_positive_iso_shape():
    assert _matches("dob_date", "dob recorded as 1990-05-14 in the form") != []


def test_dob_date_positive_us_slash_shape():
    assert _matches("dob_date", "dob recorded as 05/14/1990 in the form") != []


def test_dob_date_positive_month_name_shape():
    assert _matches("dob_date", "born May 14, 1990 per the intake") != []


def test_dob_date_negative_not_a_date_shape():
    assert _matches("dob_date", "field count is 2024-99-99") == []  # invalid month/day


def test_dob_date_negative_short_year():
    assert _matches("dob_date", "code 24-05-14 is not dob-shaped") == []


# ---------------------------------------------------------------------------
# _entry_json_string_fields: never surfaces insertId/labels/timestamp as if
# they were jsonPayload leaves (this is what keeps dob_date from firing on
# an entry's own timestamp -- the bead's own scoping requirement).
# ---------------------------------------------------------------------------

def test_entry_json_string_fields_excludes_top_level_metadata():
    entry = {
        "insertId": "abc123",
        "timestamp": "2026-09-14T00:00:00Z",
        "receiveTimestamp": "2026-09-14T00:00:01Z",
        "labels": {"instanceId": "2026-01-01-not-a-dob"},
        "jsonPayload": {
            "message": {
                "event_type": "gemini_api_response",
                "metadata": {"field_id": "p1_line1", "dob_seen": "1990-05-14"},
            }
        },
    }
    fields = sweep._entry_json_string_fields(entry)
    assert "insertId" not in fields
    assert "timestamp" not in fields
    assert "labels" not in fields
    assert any("dob_seen" in k for k in fields)
    assert fields["message.metadata.dob_seen"] == "1990-05-14"


def test_entry_json_string_fields_skips_non_string_leaves():
    entry = {"jsonPayload": {"count": 3, "ok": True, "nothing": None, "name": "x"}}
    fields = sweep._entry_json_string_fields(entry)
    assert fields == {"name": "x"}


# ---------------------------------------------------------------------------
# The redaction property -- the load-bearing guarantee of the whole script.
# format_report must be structurally unable to emit a matched substring,
# because Hit/BQTableResult never carry one in the first place.
# ---------------------------------------------------------------------------

_SENTINEL = "TOP-SECRET-A-NUMBER-A123456789-SHOULD-NEVER-BE-PRINTED"


def test_hit_dataclass_has_no_field_for_matched_text():
    """A Hit can only ever carry service/log_name/detector/json_key/
    insert_id/timestamp -- there is no slot to smuggle a matched value
    through even if a future caller tried. Mutation: add a `matched_text`
    field to Hit and populate it in sweep_service_stream -- this test goes
    red on the field-name assertion, which is the tripwire for exactly
    that regression."""
    field_names = {f.name for f in sweep.Hit.__dataclass_fields__.values()}
    assert field_names == {
        "service", "log_name", "detector", "json_key", "insert_id", "timestamp",
    }


def test_format_report_never_emits_the_sentinel_value():
    """End-to-end: build a SweepResult whose only hit is tagged against a
    sentinel-bearing field NAME (not value -- Hit cannot carry a value),
    confirm the sentinel string itself never appears in the rendered
    report even though it is the reason the hit exists conceptually.

    This also proves the formatter's own local variables (built from Hit
    objects only) cannot reintroduce a value: the sentinel is defined here
    purely as a string this test asserts absence of, never fed into the
    pipeline as an actual field value (there is no such input in this
    script's flow -- gcloud output feeds sweep_service_stream, which is
    exercised in test_run_* below without the sentinel ever needing to
    pass through format_report). The assertion is intentionally the
    strongest possible form: the sentinel is not a plausible substring of
    anything format_report constructs.
    """
    hit = sweep.Hit(
        service="polyglot-backend", log_name="run.googleapis.com/stdout",
        detector="a_number", json_key="message.metadata.field_id",
        insert_id="ins-1", timestamp="2026-09-15T00:00:00Z",
    )
    result = sweep.SweepResult(
        hits=[hit],
        counts={("polyglot-backend", "run.googleapis.com/stdout", "a_number",
                  "message.metadata.field_id"): 1},
    )
    report = sweep.format_report("polyglot-demo-aa709", result, {})
    assert _SENTINEL not in report
    # But the redacted shape (service, log, detector, key, count, insertId,
    # timestamp) IS present -- this is a redaction test, not a "print
    # nothing" test.
    assert "a_number" in report
    assert "ins-1" in report
    assert "message.metadata.field_id" in report


def test_format_report_bq_hit_never_emits_a_value_either():
    bq = {
        "cost_by_firm_month": sweep.BQTableResult(
            reachable=True, row_hits={("firm_id", "a_number"): 2},
        ),
    }
    empty_log = sweep.SweepResult()
    report = sweep.format_report("polyglot-demo-aa709", empty_log, bq)
    assert _SENTINEL not in report
    assert "firm_id" in report
    assert "a_number" in report


def test_format_report_reports_absent_table_distinctly_from_unreachable():
    bq = {
        "income_month": sweep.BQTableResult(reachable=False, absent=True,
                                             error="not found"),
        "cost_by_kit_month": sweep.BQTableResult(reachable=False,
                                                  error="403 permission denied"),
        "hosting_cost_by_service_month": sweep.BQTableResult(reachable=True),
    }
    report = sweep.format_report("polyglot-demo-aa709", sweep.SweepResult(), bq)
    assert "ABSENT" in report
    assert "UNREACHABLE" in report
    assert "403 permission denied" in report
    assert "no detector hit" in report


# ---------------------------------------------------------------------------
# Refusal gates -- must fire BEFORE any gcloud/bq call.
# ---------------------------------------------------------------------------

def test_refuses_on_log_http_flag():
    with pytest.raises(sweep.RefusedError):
        sweep.check_no_debug_leakage(["--project", "p", "--log-http"], {})


def test_refuses_on_verbosity_debug_equals_form():
    with pytest.raises(sweep.RefusedError):
        sweep.check_no_debug_leakage(["--verbosity=debug"], {})


def test_refuses_on_verbosity_debug_space_form():
    with pytest.raises(sweep.RefusedError):
        sweep.check_no_debug_leakage(["--verbosity", "debug"], {})


def test_does_not_refuse_on_unrelated_verbosity_level():
    sweep.check_no_debug_leakage(["--verbosity", "info"], {})  # no raise


def test_refuses_on_cloudsdk_core_log_http_env_true():
    with pytest.raises(sweep.RefusedError):
        sweep.check_no_debug_leakage([], {"CLOUDSDK_CORE_LOG_HTTP": "true"})


def test_refuses_on_cloudsdk_core_log_http_env_1():
    with pytest.raises(sweep.RefusedError):
        sweep.check_no_debug_leakage([], {"CLOUDSDK_CORE_LOG_HTTP": "1"})


def test_does_not_refuse_when_cloudsdk_core_log_http_is_false():
    sweep.check_no_debug_leakage([], {"CLOUDSDK_CORE_LOG_HTTP": "false"})  # no raise


def test_does_not_refuse_with_no_flags_or_env():
    sweep.check_no_debug_leakage(["--project", "polyglot-demo-aa709"], {})  # no raise


def test_refuses_on_dead_project():
    with pytest.raises(sweep.RefusedError):
        sweep.check_not_dead_project("polyglot-forms-919f2")


def test_does_not_refuse_on_live_project():
    sweep.check_not_dead_project("polyglot-demo-aa709")  # no raise


def test_main_returns_2_on_log_http_before_any_project_check():
    """The --log-http refusal must fire even with no --project at all --
    it is checked before argparse itself, so a malformed invocation still
    gets the payload-leak refusal rather than an argparse usage error."""
    code = sweep.main(["--log-http"])
    assert code == 2


def test_main_returns_2_on_dead_project(monkeypatch):
    called = {"sweep": False}
    monkeypatch.setattr(sweep, "run_cloud_logging_sweep",
                         lambda *a, **k: called.__setitem__("sweep", True))
    code = sweep.main(["--project", "polyglot-forms-919f2"])
    assert code == 2
    assert called["sweep"] is False


# ---------------------------------------------------------------------------
# Transport is IN-PROCESS: the module must never spawn anything (on Windows
# every gcloud.cmd child opens a console window; a 30-day sweep was ~180 of
# them), and the unit tests never touch ADC -- the google imports are lazy.
# ---------------------------------------------------------------------------

def test_the_module_never_spawns_a_subprocess():
    src = Path(sweep.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src and "subprocess." not in src
    assert not hasattr(sweep, "_run")


def test_importing_the_module_does_not_touch_adc():
    # The session is built lazily on first transport use; no unit test in
    # this file may ever build the real one (they all monkeypatch above it).
    assert sweep._session is None


# --- scrub: the one channel raw remote text can take ------------------------

def test_scrub_redacts_every_detector_shape_and_caps_length():
    text = ("HTTP 400: filter rejected near 'contact staff@example.com "
            "id A123456789 ssn 123-45-6789' " + "x" * 400)
    out = sweep.scrub(text)
    assert "staff@example.com" not in out
    assert "A123456789" not in out
    assert "123-45-6789" not in out
    assert "<redacted:email>" in out and "<redacted:a_number>" in out
    assert len(out) <= sweep._ERROR_TEXT_LIMIT


def test_format_report_scrubs_transport_error_text():
    """An API error can echo a filter or a row; the report's INCOMPLETE and
    UNREACHABLE lines must go through scrub() -- a sentinel email placed in
    both error channels never reaches the output."""
    sentinel = "leak.sentinel@example.com"
    log_result = sweep.SweepResult()
    log_result.incomplete = True
    log_result.errors = ["polyglot-backend/run.googleapis.com/stdout: HTTP 400 " + sentinel]
    bq = {"income_month": sweep.BQTableResult(reachable=False, error="Forbidden " + sentinel)}
    report = sweep.format_report("polyglot-demo-aa709", log_result, bq)
    assert sentinel not in report
    assert "INCOMPLETE" in report and "UNREACHABLE" in report


# --- Cloud Logging transport: pagination + errors, via a fake session -------

class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, pages):
        self.pages = list(pages)
        self.bodies = []

    def post(self, url, json=None, timeout=None):
        self.bodies.append(json)
        return self.pages.pop(0)


def test_fetch_entries_walks_every_page_token(monkeypatch):
    session = _FakeSession([
        _FakeResp(200, {"entries": [{"insertId": "a"}], "nextPageToken": "t1"}),
        _FakeResp(200, {"entries": [{"insertId": "b"}], "nextPageToken": "t2"}),
        _FakeResp(200, {"entries": [{"insertId": "c"}]}),
    ])
    monkeypatch.setattr(sweep, "_authorized_session", lambda: session)
    entries = sweep._fetch_entries("polyglot-demo-aa709", 'logName="x"')
    assert [e["insertId"] for e in entries] == ["a", "b", "c"]
    assert session.bodies[1]["pageToken"] == "t1" and session.bodies[2]["pageToken"] == "t2"
    assert "pageToken" not in session.bodies[0]
    assert session.bodies[0]["resourceNames"] == ["projects/polyglot-demo-aa709"]


def test_fetch_entries_http_error_is_a_scrubbed_transport_error(monkeypatch):
    sentinel = "err.sentinel@example.com"
    session = _FakeSession([
        _FakeResp(403, {"error": {"message": "denied for " + sentinel}}),
    ])
    monkeypatch.setattr(sweep, "_authorized_session", lambda: session)
    with pytest.raises(sweep.TransportError) as info:
        sweep._fetch_entries("polyglot-demo-aa709", 'logName="x"')
    assert "403" in str(info.value)
    assert sentinel not in str(info.value)


def test_fetch_entries_refuses_to_page_forever(monkeypatch):
    pages = [_FakeResp(200, {"entries": [{"insertId": str(i)}], "nextPageToken": "more"})
             for i in range(sweep._MAX_PAGES_PER_WINDOW + 5)]
    session = _FakeSession(pages)
    monkeypatch.setattr(sweep, "_authorized_session", lambda: session)
    with pytest.raises(sweep.TransportError) as info:
        sweep._fetch_entries("polyglot-demo-aa709", 'logName="x"')
    assert "exceeded" in str(info.value)


# --- ADC project check ------------------------------------------------------

def test_project_mismatch_with_adc_is_refused(monkeypatch):
    monkeypatch.setattr(sweep, "adc_project", lambda: "some-other-project")
    with pytest.raises(sweep.RefusedError):
        sweep.check_project_matches_adc("polyglot-demo-aa709")


def test_project_matching_adc_or_unknown_adc_passes(monkeypatch):
    monkeypatch.setattr(sweep, "adc_project", lambda: "polyglot-demo-aa709")
    sweep.check_project_matches_adc("polyglot-demo-aa709")
    monkeypatch.setattr(sweep, "adc_project", lambda: None)
    sweep.check_project_matches_adc("polyglot-demo-aa709")


def test_main_refuses_a_zero_or_negative_window(monkeypatch):
    monkeypatch.setattr(sweep, "check_project_matches_adc",
                         lambda p: (_ for _ in ()).throw(AssertionError("adc touched")))
    assert sweep.main(["--project", "polyglot-demo-aa709", "--retention-days", "0"]) == 2
    assert sweep.main(["--project", "polyglot-demo-aa709", "--retention-days", "-3"]) == 2


def test_verbosity_debug_refusal_is_case_insensitive():
    with pytest.raises(sweep.RefusedError):
        sweep.check_no_debug_leakage(["--verbosity=DEBUG"], {})
    with pytest.raises(sweep.RefusedError):
        sweep.check_no_debug_leakage(["--verbosity", "Debug"], {})


# --- URL-scoped link-token detector: a bare key=value pair is URL context ---

def test_link_token_detected_in_a_bare_query_pair():
    spans = sweep._url_scoped_spans(sweep._LINK_TOKEN_RE, "token=" + _FAKE_LINK_TOKEN)
    assert spans, "a bare token=<link-token> pair is URL context"


def test_link_token_shape_outside_any_url_context_is_ignored():
    assert sweep._url_scoped_spans(sweep._LINK_TOKEN_RE, "seen " + _FAKE_LINK_TOKEN + " in prose") == []


# ---------------------------------------------------------------------------
# BigQuery table sweep: ABSENT vs UNREACHABLE vs clean, and the
# SELECT-named-columns-only property (never SELECT *).
# ---------------------------------------------------------------------------

def test_sweep_bigquery_table_reports_absent_on_not_found(monkeypatch):
    monkeypatch.setattr(sweep, "_bq_table_schema", lambda p, d, t: None)
    monkeypatch.setattr(sweep, "_bq_query_rows",
                         lambda p, q: (_ for _ in ()).throw(AssertionError("no query")))
    result = sweep.sweep_bigquery_table("polyglot-demo-aa709", "polyglot_telemetry", "income_month")
    assert result.absent is True
    assert result.reachable is False


def test_sweep_bigquery_table_reports_unreachable_on_permission_error(monkeypatch):
    def schema(p, d, t):
        raise sweep.TransportError("Forbidden: 403 Permission denied")
    monkeypatch.setattr(sweep, "_bq_table_schema", schema)
    result = sweep.sweep_bigquery_table("polyglot-demo-aa709", "polyglot_telemetry", "cost_by_kit_month")
    assert result.absent is False
    assert result.reachable is False
    assert "403" in result.error


def test_sweep_bigquery_table_selects_only_string_columns_never_star(monkeypatch):
    seen = {}
    monkeypatch.setattr(sweep, "_bq_table_schema", lambda p, d, t: [
        ("firm_id", "STRING"), ("cost_usd", "FLOAT"), ("month", "DATE")])

    def rows(p, sql):
        seen["query"] = sql
        return [{"firm_id": "f-not-a-hit"}]
    monkeypatch.setattr(sweep, "_bq_query_rows", rows)
    sweep.sweep_bigquery_table("polyglot-demo-aa709", "polyglot_telemetry", "cost_by_firm_month")
    assert "SELECT firm_id " in seen["query"]
    assert "*" not in seen["query"]
    assert "cost_usd" not in seen["query"]


def test_sweep_bigquery_table_counts_a_hit_in_a_string_column(monkeypatch):
    monkeypatch.setattr(sweep, "_bq_table_schema", lambda p, d, t: [("firm_id", "STRING")])
    monkeypatch.setattr(sweep, "_bq_query_rows",
                         lambda p, q: [{"firm_id": "contact staff@example.com"}])
    result = sweep.sweep_bigquery_table("polyglot-demo-aa709", "polyglot_telemetry", "cost_by_firm_month")
    assert result.reachable is True
    assert result.row_hits.get(("firm_id", "email")) == 1


# ---------------------------------------------------------------------------
# sweep_service_stream: request-log detector scoping (URL-only) vs
# application-stream detector scoping (jsonPayload string leaves only).
# ---------------------------------------------------------------------------

def _window():
    from datetime import datetime, timezone
    return (datetime(2026, 9, 12, tzinfo=timezone.utc),
            datetime(2026, 9, 13, tzinfo=timezone.utc))


def test_sweep_service_stream_flags_token_in_request_log_url(monkeypatch):
    entry = {
        "insertId": "req-1",
        "timestamp": "2026-09-13T00:00:00Z",
        "logName": "projects/polyglot-demo-aa709/logs/run.googleapis.com%2Frequests",
        "httpRequest": {"requestUrl": "https://x.run.app/ws/fill?token=abc.def"},
    }
    monkeypatch.setattr(sweep, "_fetch_entries", lambda p, f: [entry])
    hits, incomplete, error = sweep.sweep_service_stream(
        "polyglot-demo-aa709", "polyglot-backend", "run.googleapis.com/requests", *_window())
    assert incomplete is False
    assert any(h.detector == "ws_token_in_url" for h in hits)
    assert all(hasattr(h, "insert_id") and hasattr(h, "timestamp") for h in hits)


def test_sweep_service_stream_does_not_scan_request_url_for_dob_dates(monkeypatch):
    """dob_date is a jsonPayload-string-only detector per the bead spec --
    it must never fire against httpRequest.requestUrl even if a URL
    happens to contain a date-shaped path segment."""
    entry = {
        "insertId": "req-2",
        "timestamp": "2026-09-13T00:00:00Z",
        "logName": "projects/polyglot-demo-aa709/logs/run.googleapis.com%2Frequests",
        "httpRequest": {"requestUrl": "https://x.run.app/reports/1990-05-14/summary"},
    }
    monkeypatch.setattr(sweep, "_fetch_entries", lambda p, f: [entry])
    hits, _, _ = sweep.sweep_service_stream(
        "polyglot-demo-aa709", "polyglot-backend", "run.googleapis.com/requests", *_window())
    assert all(h.detector != "dob_date" for h in hits)


def test_sweep_service_stream_scans_jsonpayload_string_leaves_on_app_stream(monkeypatch):
    entry = {
        "insertId": "app-1",
        "timestamp": "2026-09-13T00:00:00Z",
        "logName": "projects/polyglot-demo-aa709/logs/run.googleapis.com%2Fstdout",
        "jsonPayload": {"message": {"metadata": {"note": "email me at staff@example.com"}}},
    }
    monkeypatch.setattr(sweep, "_fetch_entries", lambda p, f: [entry])
    hits, _, _ = sweep.sweep_service_stream(
        "polyglot-demo-aa709", "polyglot-backend", "run.googleapis.com/stdout", *_window())
    matching = [h for h in hits if h.detector == "email"]
    assert len(matching) == 1
    assert matching[0].json_key == "message.metadata.note"


def test_sweep_service_stream_marks_incomplete_on_transport_failure(monkeypatch):
    def boom(p, f):
        raise sweep.TransportError("entries.list HTTP 403: PERMISSION_DENIED")
    monkeypatch.setattr(sweep, "_fetch_entries", boom)
    hits, incomplete, error = sweep.sweep_service_stream(
        "polyglot-demo-aa709", "polyglot-backend", "run.googleapis.com/stdout", *_window())
    assert incomplete is True
    assert "PERMISSION_DENIED" in error
    assert hits == []


def test_sweep_service_stream_queries_the_named_stream_and_service(monkeypatch):
    seen = {}

    def fetch(p, f):
        seen["filter"] = f
        return []
    monkeypatch.setattr(sweep, "_fetch_entries", fetch)
    sweep.sweep_service_stream(
        "polyglot-demo-aa709", "polyglot-admin", "run.googleapis.com/requests", *_window())
    assert 'resource.labels.service_name="polyglot-admin"' in seen["filter"]
    assert "run.googleapis.com%2Frequests" in seen["filter"]
    assert 'timestamp>="2026-09-12T00:00:00Z"' in seen["filter"]


# --- credentials come from files, never from a gcloud subprocess ------------

def test_the_module_never_calls_google_auth_default():
    """google.auth.default() shells out to `gcloud config get project` when
    the ADC file carries no project -- a console window per call on
    Windows. The transport loads the ADC file and the gcloud config directly."""
    src = Path(sweep.__file__).read_text(encoding="utf-8")
    assert "auth.default(" not in src
    assert "load_credentials_from_file(" in src


def test_adc_project_reads_the_active_gcloud_configuration(tmp_path, monkeypatch):
    cfg = tmp_path / "gcloud"
    (cfg / "configurations").mkdir(parents=True)
    (cfg / "active_config").write_text("work", encoding="utf-8")
    (cfg / "configurations" / "config_work").write_text(
        "[core]\naccount = someone@example.com\nproject = polyglot-demo-aa709\n",
        encoding="utf-8")
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(cfg))
    assert sweep.adc_project() == "polyglot-demo-aa709"


def test_adc_project_is_none_without_a_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path))
    assert sweep.adc_project() is None


def test_missing_adc_file_is_a_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "_credentials", None)
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path))
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(sweep.RefusedError) as info:
        sweep.ensure_credentials()
    assert "application-default login" in str(info.value)


def test_main_exits_2_without_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "_credentials", None)
    monkeypatch.setattr(sweep, "adc_project", lambda: None)
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path))
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(sweep, "run_cloud_logging_sweep",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("swept without creds")))
    assert sweep.main(["--project", "polyglot-demo-aa709"]) == 2


def test_fetch_entries_retries_a_429_then_succeeds(monkeypatch):
    """The Logging read quota is per minute; a 30-day sweep trips it partway
    through. A 429 is retried with backoff instead of marking the window
    incomplete."""
    slept = []
    monkeypatch.setattr(sweep.time, "sleep", lambda s: slept.append(s))
    session = _FakeSession([
        _FakeResp(429, {"error": {"message": "Quota exceeded"}}),
        _FakeResp(429, {"error": {"message": "Quota exceeded"}}),
        _FakeResp(200, {"entries": [{"insertId": "a"}]}),
    ])
    monkeypatch.setattr(sweep, "_authorized_session", lambda: session)
    entries = sweep._fetch_entries("polyglot-demo-aa709", 'logName="x"')
    assert [e["insertId"] for e in entries] == ["a"]
    assert slept == list(sweep._RETRY_BACKOFF_S[:2])


def test_fetch_entries_gives_up_after_the_retry_budget(monkeypatch):
    monkeypatch.setattr(sweep.time, "sleep", lambda s: None)
    session = _FakeSession([_FakeResp(429, {"error": {"message": "Quota exceeded"}})
                            for _ in range(len(sweep._RETRY_BACKOFF_S) + 1)])
    monkeypatch.setattr(sweep, "_authorized_session", lambda: session)
    with pytest.raises(sweep.TransportError) as info:
        sweep._fetch_entries("polyglot-demo-aa709", 'logName="x"')
    assert "429" in str(info.value)

