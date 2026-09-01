"""POST /api/tts/notice -- the free safety-notice route (bd polyglot-pdf-see5j).

Pins the bead's exit criteria: a repeat request for the same (language,
notice_key) is served from the in-process cache with NO second synthesis
RPC, and a request carrying a matching If-None-Match gets a 304 with no
body. Mirrors the sibling test_intro_route.py's fixture pattern (same
underlying cache/304 shape, lifted from intro_tts to notice_tts).

All synthesis is faked at the notice_tts module boundary -- no test touches
the network. Fresh Settings() per test (get_settings is lru_cached -- the
test-ordering trap). ASCII only in this file (scar #6).
"""
import pytest

from backend.config import Settings
import backend.services.notice_tts as notice_tts


class TestNoticeRoute:
    def _client(self, monkeypatch):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.services.auth import require_auth
        import backend.routes.tts_routes as tts_routes

        settings = Settings()
        monkeypatch.setattr(tts_routes, "get_settings", lambda: settings)
        app.dependency_overrides[require_auth] = lambda: {"uid": "test"}
        client = TestClient(app)
        return client, app, require_auth

    def _fake_synth(self, monkeypatch, calls: list):
        """Fake the ONE outbound RPC (_synthesize_sync as imported by
        notice_tts) and reset the module cache so tests are independent."""
        def fake(text, voice_name, locale, gain_db=None):
            calls.append({
                "text": text, "voice": voice_name,
                "locale": locale, "gain_db": gain_db,
            })
            return b"MP3BYTES-" + str(len(calls)).encode()

        monkeypatch.setattr(notice_tts, "_synthesize_sync", fake)
        monkeypatch.setattr(notice_tts, "_cache", {})

    def test_repeat_request_serves_from_cache_single_rpc(self, monkeypatch):
        """Exit criterion 1: ONE synthesis RPC per (language, notice_key)
        for the process lifetime; the repeat is byte-identical with the
        same ETag."""
        client, app, require_auth = self._client(monkeypatch)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            body = {"notice": "save_early", "language": "Spanish"}
            first = client.post("/api/tts/notice", json=body)
            second = client.post("/api/tts/notice", json=body)
            assert first.status_code == second.status_code == 200
            assert len(calls) == 1
            assert first.content == second.content
            assert first.headers["etag"] == second.headers["etag"]
            # A DIFFERENT key (different notice) is a genuine new synthesis.
            client.post("/api/tts/notice",
                        json={"notice": "voice_ending", "language": "Spanish"})
            assert len(calls) == 2
            # A DIFFERENT key (different language) is also a genuine new
            # synthesis -- the cache is keyed on BOTH, not just the notice.
            client.post("/api/tts/notice",
                        json={"notice": "save_early", "language": "German"})
            assert len(calls) == 3
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_a_case_mismatched_language_does_not_poison_the_cache_for_the_properly_cased_one(
            self, monkeypatch):
        """bd polyglot-pdf-see5j, Opus cross-surface finding 1: notice_text's
        lookup used to be case-SENSITIVE while the cache key was
        case-normalized (resolve_intro_language) -- so a lowercase "spanish"
        synthesized the ENGLISH fallback text but cached it under the SAME
        key a properly-cased "Spanish" request would hit, permanently
        serving English audio to Spanish requests for the rest of the
        process lifetime. Both requests must synthesize the SAME (Spanish)
        text, and the cache must correctly treat them as one cache entry
        (not two, and not one poisoned by the other's wrong text)."""
        client, app, require_auth = self._client(monkeypatch)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            lower = client.post(
                "/api/tts/notice",
                json={"notice": "save_early", "language": "spanish"})
            proper = client.post(
                "/api/tts/notice",
                json={"notice": "save_early", "language": "Spanish"})
            assert lower.status_code == proper.status_code == 200
            # ONE synthesis call total -- they resolve to the same cache key
            # AND get the correctly-resolved Spanish text, so the second
            # request is a genuine cache hit, not a second (correct) synthesis.
            assert len(calls) == 1
            assert lower.content == proper.content
            # The text actually synthesized must be SPANISH, not the English
            # fallback -- this is the regression itself: the case-mismatched
            # request must resolve to the same table entry as the properly
            # cased one, not silently fall through to English.
            spanish_text = notice_tts.NOTICE_TEXT["Spanish"]["save_early"]
            english_text = notice_tts.NOTICE_TEXT["English"]["save_early"]
            assert calls[0]["text"] == spanish_text
            assert calls[0]["text"] != english_text
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_if_none_match_revalidates_304_without_body(self, monkeypatch):
        """Exit criterion 2."""
        client, app, require_auth = self._client(monkeypatch)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            body = {"notice": "voice_ending", "language": "Hindi"}
            first = client.post("/api/tts/notice", json=body)
            etag = first.headers["etag"]
            resp = client.post("/api/tts/notice", json=body,
                               headers={"If-None-Match": etag})
            assert resp.status_code == 304
            assert resp.content == b""
            assert resp.headers["etag"] == etag
            assert len(calls) == 1  # the 304 path is cache-only too
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_unknown_notice_is_400_and_never_synthesizes(self, monkeypatch):
        """The keyed-route contract: caller text never enters synthesis."""
        client, app, require_auth = self._client(monkeypatch)
        calls: list = []
        self._fake_synth(monkeypatch, calls)
        try:
            for bad in ("drop_table", "", "  ", "save early"):
                resp = client.post(
                    "/api/tts/notice",
                    json={"notice": bad, "language": "English"})
                assert resp.status_code == 400, bad
            assert calls == []
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_synthesis_failure_is_502_error_type_only(self, monkeypatch):
        client, app, require_auth = self._client(monkeypatch)

        def boom(text, voice_name, locale, gain_db=None):
            raise RuntimeError("chirp exploded")

        monkeypatch.setattr(notice_tts, "_synthesize_sync", boom)
        monkeypatch.setattr(notice_tts, "_cache", {})
        try:
            resp = client.post(
                "/api/tts/notice",
                json={"notice": "save_early", "language": "English"})
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.pop(require_auth, None)
