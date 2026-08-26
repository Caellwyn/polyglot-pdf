"""POST /api/tts/intro -- the scripted intro clip route (bd polyglot-pdf-s1iex.3).

Pins the bead's exit criteria: audio/mpeg for EVERY supported language when
the flag is on (language set DERIVED from SPOKEN_LANGUAGE_BCP47, never a
hand-list), 503 when off, and a repeat request served from the in-process
cache with NO second synthesis RPC. Plus the keyed-route contract (unknown
form -> 400 with synthesis never invoked), the 0 dB gain decision, the
ETag/304 revalidation path, and the static frontend mirror pin for the
agree-label table (the same mirror idiom as
test_spellback_tool.test_char_cap_matches_frontend_mirror).

All synthesis is faked at the intro_tts module boundary -- no test touches
the network. Fresh Settings() per test (get_settings is lru_cached -- the
test-ordering trap); expected non-ASCII strings are always READ from the
data files, never re-typed (bd uov.6 lesson). ASCII only in this file
(scar #6).
"""
import json
import re
from pathlib import Path

import pytest

from backend.config import Settings
from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47
import backend.services.intro_tts as intro_tts

_REPO = Path(__file__).resolve().parents[3]
_MODAL_TSX = (_REPO / "frontend" / "src" / "schema-forms" / "components"
              / "DisclaimerModal.tsx")
_LABELS = json.loads(
    (Path(intro_tts.__file__).parent / "intro_agree_labels.json")
    .read_text(encoding="utf-8"))
_LABELS.pop("_comment", None)


class TestIntroRoute:
    def _client(self, monkeypatch, enabled: bool):
        from fastapi.testclient import TestClient
        from backend.main import app
        # The TTS routes moved to the STRICTER dependency (bd
        # polyglot-pdf-ugm6): they spend money, so a completed client link
        # must buy no more synthesis. Override THAT, or every request here
        # 401s on a real token check.
        from backend.services.auth import require_paid_client_work as require_auth
        import backend.routes.tts_routes as tts_routes

        settings = Settings()
        settings.INTRO_TTS_ENABLED = enabled
        monkeypatch.setattr(tts_routes, "get_settings", lambda: settings)
        app.dependency_overrides[require_auth] = lambda: {"uid": "test"}
        client = TestClient(app)
        return client, app, require_auth

    def _fake_synth(self, monkeypatch, calls: list):
        """Fake the ONE outbound RPC (_synthesize_sync as imported by
        intro_tts) and reset the module cache so tests are independent."""
        def fake(text, voice_name, locale, gain_db=None):
            calls.append({
                "text": text, "voice": voice_name,
                "locale": locale, "gain_db": gain_db,
            })
            return b"MP3BYTES-" + str(len(calls)).encode()

        monkeypatch.setattr(intro_tts, "_synthesize_sync", fake)
        monkeypatch.setattr(intro_tts, "_cache", {})

    def test_flag_off_is_503(self, monkeypatch):
        client, app, require_auth = self._client(monkeypatch, enabled=False)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            resp = client.post(
                "/api/tts/intro",
                json={"form_number": "I-90", "language": "English"})
            assert resp.status_code == 503
            assert calls == []
        finally:
            app.dependency_overrides.pop(require_auth, None)

    @pytest.mark.parametrize("language", sorted(SPOKEN_LANGUAGE_BCP47))
    def test_every_supported_language_returns_audio(self, monkeypatch,
                                                    language):
        """Exit criterion 1, DERIVED from the app's language map. The wire
        name is the map's lowercase key -- the route must resolve it
        case-insensitively to the store's display-cased entry."""
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            resp = client.post(
                "/api/tts/intro",
                json={"form_number": "I-90", "language": language})
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("audio/mpeg")
            assert resp.headers["cache-control"] == "private, max-age=3600"
            assert resp.headers.get("etag", "").startswith('"intro-')
            [call] = calls
            # The synthesized text is fully interpolated table content:
            # the form name, the language's own agree label (read from the
            # data file, never re-typed), and no leftover placeholders.
            resolved = intro_tts.resolve_intro_language(language)
            assert "Form I-90" in call["text"]
            assert _LABELS[resolved] in call["text"]
            assert "[FORM NUMBER]" not in call["text"]
            assert "[AGREE LABEL]" not in call["text"]
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_unknown_form_is_400_and_never_synthesizes(self, monkeypatch):
        """The keyed-route contract: caller text never enters synthesis."""
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            for bad in ("I-485", "drop table", "", "  "):
                resp = client.post(
                    "/api/tts/intro",
                    json={"form_number": bad, "language": "English"})
                assert resp.status_code == 400, bad
            assert calls == []
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_unknown_language_falls_back_to_english(self, monkeypatch):
        """An older/odd client gets a working English clip, never an error
        -- the same fallback the shipped modal applies."""
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            for weird in (None, "Klingon", ""):
                resp = client.post(
                    "/api/tts/intro",
                    json={"form_number": "W-7", "language": weird})
                assert resp.status_code == 200, weird
            english = " ".join(
                intro_tts._LANGUAGES["English"]["paragraphs"])[:40]
            for call in calls:
                assert call["text"].startswith(english[:20])
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_repeat_request_serves_from_cache_single_rpc(self, monkeypatch):
        """Exit criterion 2: ONE synthesis RPC per (language, form) for the
        process lifetime; the repeat is byte-identical with the same ETag."""
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            body = {"form_number": "I-90", "language": "Spanish"}
            first = client.post("/api/tts/intro", json=body)
            second = client.post("/api/tts/intro", json=body)
            assert first.status_code == second.status_code == 200
            assert len(calls) == 1
            assert first.content == second.content
            assert first.headers["etag"] == second.headers["etag"]
            # A DIFFERENT key is a genuine new synthesis, not a cache hit.
            client.post("/api/tts/intro",
                        json={"form_number": "W-7", "language": "Spanish"})
            assert len(calls) == 2
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_if_none_match_revalidates_304_without_body(self, monkeypatch):
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            body = {"form_number": "I-90", "language": "Hindi"}
            first = client.post("/api/tts/intro", json=body)
            etag = first.headers["etag"]
            resp = client.post("/api/tts/intro", json=body,
                               headers={"If-None-Match": etag})
            assert resp.status_code == 304
            assert resp.content == b""
            assert resp.headers["etag"] == etag
            assert len(calls) == 1  # the 304 path is cache-only too
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_intro_gain_is_zero_never_the_spellback_gain(self, monkeypatch):
        """The 0 dB decision: the +4 dB spell-back gain, measured on ~4s
        clips, CLIPS ~90s content (raw peak 1.000, findings doc 2026-08-13).
        Passing None here would silently re-apply it."""
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            client.post("/api/tts/intro",
                        json={"form_number": "I-90", "language": "English"})
            [call] = calls
            assert call["gain_db"] == 0.0
            assert call["gain_db"] is not None
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_etag_is_cors_exposed_for_the_cross_origin_dev_client(
            self, monkeypatch):
        """ETag is not CORS-safelisted: without expose_headers the bead-.5
        client reads null on the cross-origin local dev stack (SPA :5173 ->
        uvicorn :8000) and can never send If-None-Match -- while same-origin
        production hides the gap (s1iex.3 cross-surface review). Pin the
        BEHAVIOR at the gate: a CORS response must expose the header."""
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            resp = client.post(
                "/api/tts/intro",
                json={"form_number": "I-90", "language": "English"},
                headers={"Origin": "http://localhost:5173"})
            assert resp.status_code == 200
            exposed = resp.headers.get("access-control-expose-headers", "")
            assert "etag" in exposed.lower()
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_synthesis_failure_is_502_error_type_only(self, monkeypatch):
        client, app, require_auth = self._client(monkeypatch, enabled=True)

        def boom(text, voice_name, locale, gain_db=None):
            raise RuntimeError("chirp exploded")

        monkeypatch.setattr(intro_tts, "_synthesize_sync", boom)
        monkeypatch.setattr(intro_tts, "_cache", {})
        try:
            resp = client.post(
                "/api/tts/intro",
                json={"form_number": "I-90", "language": "English"})
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.pop(require_auth, None)


class TestIntroTables:
    def test_agree_labels_match_frontend_mirror(self):
        """intro_agree_labels.json is MIRRORED (not shared) from
        BUTTON_TRANSLATIONS in DisclaimerModal.tsx -- two hand-maintained
        18-language tables on opposite sides of the Python/TS boundary.
        This static pin is what makes drift a CI failure instead of a
        wrong-label clip in one language (the outer-review observation on
        PR #584). Both sides are PARSED -- no expected value is re-typed."""
        ts = _MODAL_TSX.read_text(encoding="utf-8")
        block = re.search(
            r"BUTTON_TRANSLATIONS[^=]*=\s*\{(.*?)\n\};", ts, re.DOTALL)
        assert block, "BUTTON_TRANSLATIONS not found in DisclaimerModal.tsx"
        pairs = re.findall(
            r"'((?:\\'|[^'])+)':\s*\{[^}]*agree:\s*'((?:\\'|[^'])*)'",
            block.group(1))
        frontend = {lang.replace("\\'", "'"): agree.replace("\\'", "'")
                    for lang, agree in pairs}
        assert frontend == _LABELS

    def test_known_forms_values_carry_the_wire_key(self):
        """Every spoken form name contains its own wire key -- the guard
        against a table row whose spoken text names a DIFFERENT form."""
        for key, spoken in intro_tts.KNOWN_FORMS.items():
            assert key in spoken, (key, spoken)
            assert spoken.startswith("Form "), (key, spoken)

    def test_script_version_tracks_the_text(self):
        """script_version() is the acceptance-record hash (bd s1iex.7):
        re-derivable from the store + label table, distinct per language."""
        v_en = intro_tts.script_version("English")
        assert v_en == intro_tts.script_version("English")
        assert v_en != intro_tts.script_version("Spanish")
        import hashlib
        joined = " ".join(intro_tts._LANGUAGES["English"]["paragraphs"])
        expected = hashlib.sha256(
            ("%s\n%s" % (joined, _LABELS["English"])).encode("utf-8")
        ).hexdigest()[:16]
        assert v_en == expected

    def test_script_version_tracks_the_agree_label_too(self, monkeypatch):
        """The label IS spoken, so a label edit must change the version --
        otherwise intro_agree_labels.json can drift under an unchanged
        acceptance-record hash (fresh-eyes round-1 finding)."""
        before = intro_tts.script_version("German")
        mutated = dict(intro_tts._AGREE_LABELS)
        mutated["German"] = "Zustimmen"
        monkeypatch.setattr(intro_tts, "_AGREE_LABELS", mutated)
        assert intro_tts.script_version("German") != before
