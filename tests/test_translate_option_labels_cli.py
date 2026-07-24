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
