"""Tests for scripts/authoring/translate_option_labels.py (bd polyglot-pdf-2h9j).

Pins the CLI contract around the shared bake (unit-tested in
backend/tests/unit/test_option_translation_bake.py):
  - --check reports without writing or calling any model, exit 1 when a write
    run would change the file, exit 0 when fully covered;
  - a write run bakes lowercase-name keys, writes indent=2 ensure_ascii JSON
    (the committed-kit convention), and a second run is a byte-identical no-op
    with ZERO model calls (idempotency);
  - a failed language exits 2 but still writes the partial result;
  - an unknown --languages name is rejected up front.

Imports the CLI by file path (repo precedent: test_extract_form_backfill.py).
The fake adapter is injected by monkeypatching _build_text_ai -- no Gemini,
no network.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
_SCRIPT = _REPO / "scripts" / "authoring" / "translate_option_labels.py"
spec = importlib.util.spec_from_file_location("translate_option_labels", _SCRIPT)
tol = importlib.util.module_from_spec(spec)
sys.modules["translate_option_labels"] = tol
spec.loader.exec_module(tol)


ESPANOL = {"Yes": "S\u00ed", "No": "No", "Male": "Masculino"}
FRANCAIS = {"Yes": "Oui", "No": "Non", "Male": "Homme"}


class FakeTextAI:
    """Answers the bake's context-carrying translate_items call (bd alry)."""

    def __init__(self, fail_languages=()):
        self.fail_languages = {f.lower() for f in fail_languages}
        self.calls = []

    async def translate_items(self, items, language_name, language_code, *,
                              form_name=None, glossary_context=None):
        sent = []
        for item in items:
            sent.extend(item["options"] if item["kind"] == "option-set"
                        else [item["text"]])
        self.calls.append((tuple(sent), language_name))
        if language_name.lower() in self.fail_languages:
            return None
        table = {"spanish": ESPANOL, "french": FRANCAIS}[language_name.lower()]
        result = {}
        for item in items:
            if item["kind"] == "option-set":
                options = {s: table[s] for s in item["options"] if s in table}
                if options:
                    result[item["id"]] = {"options": options}
            elif item.get("text") in table:
                result[item["id"]] = {"translation": table[item["text"]]}
        return {"items": result, "ambiguous": []}


class OfflineLiteAI:
    """Keeps the default-ON verify gate (bd 9ikj) hermetic: back_translate
    fails open, so no test here can construct a REAL lite adapter and hit a
    live endpoint on a credentialed machine (the hazard bd alry closed in
    the editor-route tests -- same fix, this suite)."""

    async def back_translate(self, items, language_name, language_code):
        return None


@pytest.fixture()
def kit(tmp_path):
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    schema = {"fields": [
        {"id": "sex", "type": "radio", "options": [
            {"value": "M", "label": "Male"},
        ]},
        {"id": "confirm", "type": "radio", "options": [
            {"value": "y", "label": "Yes"},
            {"value": "n", "label": "No"},
        ]},
    ]}
    (kit_dir / "schema.json").write_text(
        json.dumps(schema, indent=2), encoding="utf-8")
    return kit_dir


def _inject(monkeypatch, fake):
    monkeypatch.setattr(tol, "_build_text_ai", lambda *a, **k: fake)
    import backend.services.option_translation as _ot
    monkeypatch.setattr(
        _ot, "_build_verify_lite_ai", lambda: OfflineLiteAI())
    return fake


def test_check_reports_missing_without_writing_or_calling(kit, monkeypatch):
    fake = _inject(monkeypatch, FakeTextAI())
    before = (kit / "schema.json").read_bytes()

    rc = tol.main(["--kit", str(kit), "--check", "--languages", "spanish,french"])

    assert rc == 1
    assert (kit / "schema.json").read_bytes() == before
    assert fake.calls == []  # --check never builds/uses an adapter


def test_write_bakes_ascii_json_and_second_run_is_noop(kit, monkeypatch):
    fake = _inject(monkeypatch, FakeTextAI())
    rc = tol.main(["--kit", str(kit), "--languages", "spanish,french"])
    assert rc == 0
    assert len(fake.calls) == 2  # one batched call per language

    raw = (kit / "schema.json").read_bytes()
    assert all(b < 128 for b in raw)  # ensure_ascii convention
    schema = json.loads(raw)
    male = schema["fields"][0]["options"][0]
    assert male["label_translations"] == {
        "spanish": "Masculino", "french": "Homme"}
    assert (male["value"], male["label"]) == ("M", "Male")

    # Idempotency: second run -- zero calls, byte-identical file, exit 0.
    fake2 = _inject(monkeypatch, FakeTextAI())
    rc2 = tol.main(["--kit", str(kit), "--languages", "spanish,french"])
    assert rc2 == 0
    assert fake2.calls == []
    assert (kit / "schema.json").read_bytes() == raw

    # And --check now agrees: fully covered.
    assert tol.main(["--kit", str(kit), "--check",
                     "--languages", "spanish,french"]) == 0


def test_failed_language_exits_2_but_writes_partial(kit, monkeypatch):
    _inject(monkeypatch, FakeTextAI(fail_languages=["french"]))
    rc = tol.main(["--kit", str(kit), "--languages", "spanish,french"])
    assert rc == 2

    schema = json.loads((kit / "schema.json").read_text(encoding="utf-8"))
    male = schema["fields"][0]["options"][0]
    assert male["label_translations"] == {"spanish": "Masculino"}

    # Healthy re-run fills exactly the gap.
    fake = _inject(monkeypatch, FakeTextAI())
    assert tol.main(["--kit", str(kit), "--languages", "spanish,french"]) == 0
    assert [c[1] for c in fake.calls] == ["French"]


def test_unknown_language_is_rejected(kit, monkeypatch):
    _inject(monkeypatch, FakeTextAI())
    with pytest.raises(SystemExit):
        tol.main(["--kit", str(kit), "--languages", "klingon"])


def test_missing_schema_path_exits_2(tmp_path, monkeypatch, capsys):
    _inject(monkeypatch, FakeTextAI())
    rc = tol.main(["--kit", str(tmp_path / "nope")])
    assert rc == 2
    assert "not found" in capsys.readouterr().out


# --- Flag surfacing (bd polyglot-pdf-9djc) ---------------------------------


class AmbiguousTextAI(FakeTextAI):
    """FakeTextAI that also self-flags every option-set item as ambiguous --
    a real report-channel flag that flows with zero judge/back-translate
    stubbing (the planted-flag path for the CLI surface)."""

    async def translate_items(self, items, language_name, language_code, *,
                              form_name=None, glossary_context=None):
        raw = await super().translate_items(
            items, language_name, language_code,
            form_name=form_name, glossary_context=glossary_context)
        if raw is not None:
            raw["ambiguous"] = [
                i["id"] for i in items if i["kind"] == "option-set"]
        return raw


def _boobytrap_lite(monkeypatch):
    """Fail the test if anything tries to build the verify lite adapter --
    the skipped-gate pins below prove the loop truly does not run."""
    import backend.services.option_translation as _ot

    def _boom():
        raise AssertionError("verify lite adapter built despite the opt-out")
    monkeypatch.setattr(_ot, "_build_verify_lite_ai", _boom)


def test_flags_block_and_artifact(kit, monkeypatch, capsys, tmp_path):
    """A bake with planted flags prints the FLAGS summary block (rule + path
    only -- messages can carry foreign script, cp1252 hazard) and writes the
    full findings to the --flags-out JSON artifact (exit criterion 1, CLI
    surface)."""
    _inject(monkeypatch, AmbiguousTextAI())
    flags_path = tmp_path / "flags.json"

    rc = tol.main(["--kit", str(kit), "--languages", "spanish,french",
                   "--flags-out", str(flags_path)])
    assert rc == 0
    out = capsys.readouterr().out
    # Verify gate is ON by default and says so on this surface.
    assert "verify: ON" in out
    assert "FLAGS:" in out
    assert "translation-ambiguous-source" in out
    # Paths (rule + kit location) print; messages do not (cp1252 rule).
    assert "label_translations.spanish" in out
    assert "under-determined" not in out
    assert f"wrote flags artifact {flags_path}" in out

    raw = flags_path.read_bytes()
    assert all(b < 128 for b in raw)  # ensure_ascii artifact
    artifact = json.loads(raw)
    assert artifact["schema"] == str(kit / "schema.json")
    assert artifact["verify_enabled"] is True
    flags = artifact["flags"]
    assert flags and all(f["severity"] == "WARNING" for f in flags)
    assert {f["rule"] for f in flags} == {"translation-ambiguous-source"}
    # The artifact carries what the console withheld: the full messages.
    assert all("under-determined" in f["message"] for f in flags)


def test_flags_out_written_even_when_flag_free(kit, monkeypatch, tmp_path):
    _inject(monkeypatch, FakeTextAI())
    flags_path = tmp_path / "flags.json"
    rc = tol.main(["--kit", str(kit), "--languages", "spanish",
                   "--flags-out", str(flags_path)])
    assert rc == 0
    artifact = json.loads(flags_path.read_text(encoding="utf-8"))
    assert artifact["flags"] == []


def test_no_verify_skips_the_loop_and_says_so(kit, monkeypatch, capsys):
    """Exit criterion 2 (flag path): --no-verify never touches the verify
    machinery and the skip is visible on the CLI surface."""
    fake = AmbiguousTextAI()
    monkeypatch.setattr(tol, "_build_text_ai", lambda *a, **k: fake)
    _boobytrap_lite(monkeypatch)

    rc = tol.main(["--kit", str(kit), "--no-verify",
                   "--languages", "spanish,french"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verify: skipped (--no-verify)" in out
    assert "UNVERIFIED" in out
    # Ambiguity self-flags come from the FORWARD call, so the FLAGS block
    # still surfaces them even with the verify loop off.
    assert "FLAGS:" in out


def test_env_disabled_verify_skips_and_says_so(kit, monkeypatch, capsys):
    """Exit criterion 2 (env path): TRANSLATION_VERIFY_ENABLED=false skips
    the loop with the reason named on the CLI surface."""
    from types import SimpleNamespace

    from backend import config
    monkeypatch.setattr(
        config, "get_settings",
        lambda: SimpleNamespace(TRANSLATION_VERIFY_ENABLED=False))
    fake = FakeTextAI()
    monkeypatch.setattr(tol, "_build_text_ai", lambda *a, **k: fake)
    _boobytrap_lite(monkeypatch)

    rc = tol.main(["--kit", str(kit), "--languages", "spanish,french"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verify: skipped (TRANSLATION_VERIFY_ENABLED=false)" in out
    assert "UNVERIFIED" in out
