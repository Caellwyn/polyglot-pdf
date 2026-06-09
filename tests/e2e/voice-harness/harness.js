/*
 * Voice form-fill E2E test harness (bd polyglot-pdf-g8w).
 *
 * Runs IN THE BROWSER. The agent injects this file's source via preview_eval so
 * that window.__VFF_HARNESS exists, then drives the cycle turn by turn (see
 * RUNBOOK.md). It loads committed 16 kHz mono PCM16 WAV fixtures, streams them
 * into the live WebSocket through window.__VFF_TEST_INJECT (the dev-gated hook in
 * connection.ts), waits for Gemini to finish each spoken turn, and reads back the
 * field state for assertions.
 *
 * Depends on the app hook window.__VFF_TEST_INJECT being installed -- that needs
 * window.__VFF_LOCAL_DEV === true AND window.__VFF_TEST_HARNESS === true set
 * BEFORE the connection manager is created (set them, then reload).
 *
 * ASCII-only (repo rule). No build step; plain browser JS.
 */
(function () {
  'use strict';

  // Wire format the backend forwards to Gemini: PCM16 LE, 16 kHz, mono.
  var SAMPLE_RATE = 16000;
  var BYTES_PER_SAMPLE = 2;
  var CHUNK_MS = 20; // 20 ms => 320 samples => 640 bytes per chunk.

  function inject() {
    var h = window.__VFF_TEST_INJECT;
    if (!h) {
      throw new Error(
        'window.__VFF_TEST_INJECT is missing. Set window.__VFF_LOCAL_DEV=true and ' +
        'window.__VFF_TEST_HARNESS=true, then reload so the hook installs.'
      );
    }
    return h;
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  /*
   * Fetch a WAV fixture and return its raw PCM16 data as an ArrayBuffer.
   * Parses the RIFF/WAVE header (does NOT assume a fixed 44-byte offset -- it
   * walks chunks to find 'fmt ' and 'data'), and HARD-FAILS on a format mismatch
   * so a wrong-rate fixture can never silently feed Gemini garbage.
   */
  async function loadFixture(url) {
    var resp = await fetch(url);
    if (!resp.ok) {
      throw new Error('loadFixture: fetch failed ' + resp.status + ' for ' + url);
    }
    var buf = await resp.arrayBuffer();
    var dv = new DataView(buf);

    function tag(off) {
      return String.fromCharCode(dv.getUint8(off), dv.getUint8(off + 1),
        dv.getUint8(off + 2), dv.getUint8(off + 3));
    }
    if (tag(0) !== 'RIFF' || tag(8) !== 'WAVE') {
      throw new Error('loadFixture: not a RIFF/WAVE file: ' + url);
    }

    var fmt = null;
    var dataOff = -1;
    var dataLen = 0;
    var off = 12; // first chunk after 'RIFF'<size>'WAVE'
    while (off + 8 <= buf.byteLength) {
      var id = tag(off);
      var size = dv.getUint32(off + 4, true);
      var body = off + 8;
      if (id === 'fmt ') {
        // A PCM (WAVEFORMATEX) fmt chunk is >= 16 bytes; bitsPerSample lives at
        // byte 14. Guard the size so a malformed/short fmt chunk can't read a
        // garbage bitsPerSample out of the following chunk's bytes (fresh-eyes,
        // PR #123).
        if (size < 16) {
          throw new Error('loadFixture: fmt chunk too short (' + size + ' bytes) in ' + url);
        }
        fmt = {
          audioFormat: dv.getUint16(body, true),
          channels: dv.getUint16(body + 2, true),
          sampleRate: dv.getUint32(body + 4, true),
          bitsPerSample: dv.getUint16(body + 14, true)
        };
      } else if (id === 'data') {
        dataOff = body;
        dataLen = size;
      }
      off = body + size + (size % 2); // chunks are word-aligned
    }

    if (!fmt) throw new Error('loadFixture: no fmt chunk in ' + url);
    if (dataOff < 0) throw new Error('loadFixture: no data chunk in ' + url);
    if (fmt.audioFormat !== 1) throw new Error('loadFixture: not PCM (fmt ' + fmt.audioFormat + ')');
    if (fmt.sampleRate !== SAMPLE_RATE) {
      throw new Error('loadFixture: sample rate ' + fmt.sampleRate + ' != ' + SAMPLE_RATE);
    }
    if (fmt.channels !== 1) throw new Error('loadFixture: channels ' + fmt.channels + ' != 1');
    if (fmt.bitsPerSample !== 16) throw new Error('loadFixture: bits ' + fmt.bitsPerSample + ' != 16');

    return buf.slice(dataOff, dataOff + dataLen);
  }

  /*
   * Stream a PCM16 ArrayBuffer into the WS as ~20 ms chunks, pacing in real time
   * so Gemini's VAD/turn logic behaves like a live mic. VAD-mode aware, mirroring
   * the real client: manual VAD brackets the burst with activity_start/end;
   * native VAD streams continuously and appends a short trailing silence to let
   * Gemini's own VAD detect end-of-speech.
   */
  async function injectUtterance(pcmBuffer, opts) {
    opts = opts || {};
    var chunkMs = opts.chunkMs || CHUNK_MS;
    var h = inject();
    var native = h.isNativeVad();

    var bytesPerChunk = Math.round((SAMPLE_RATE * BYTES_PER_SAMPLE * chunkMs) / 1000);

    if (!native) {
      h.sendActivityStart();
    }

    for (var pos = 0; pos < pcmBuffer.byteLength; pos += bytesPerChunk) {
      var end = Math.min(pos + bytesPerChunk, pcmBuffer.byteLength);
      h.sendAudio(pcmBuffer.slice(pos, end));
      await sleep(chunkMs); // pace at ~real time
    }

    if (native) {
      // ~500 ms of trailing silence so Gemini's VAD closes the turn.
      var silence = new ArrayBuffer(bytesPerChunk);
      var silenceMs = 500;
      var frames = Math.ceil(silenceMs / chunkMs);
      for (var i = 0; i < frames; i++) {
        h.sendAudio(silence.slice(0));
        await sleep(chunkMs);
      }
    } else {
      await h.sendActivityEnd();
    }
  }

  /*
   * Generic poller: resolve as soon as fn() returns truthy, else time out.
   * Returns { met, value, timedOut, elapsedMs }. This is the load-bearing wait
   * primitive -- the harness gates on CONCRETE OUTCOMES (a field got a value, a
   * field got confirmed, Gemini advanced) rather than on audio playback, because
   * audio-end is an unreliable turn signal: Gemini streams many tiny chunks, and
   * in an automated/headless tab playback may not fire onended at all. (The first
   * live run, bd polyglot-pdf-g8w, timed out on vffOnAudioPlaybackEnd every turn
   * even though the fill SUCCEEDED -- the outcome was the only trustworthy signal.)
   */
  function waitForCondition(fn, opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs || 30000;
    var pollMs = opts.pollMs || 200;
    var startedAt = Date.now();
    return new Promise(function (resolve) {
      function tick() {
        var value;
        try { value = fn(); } catch (e) { value = false; }
        if (value) {
          resolve({ met: true, value: value, timedOut: false, elapsedMs: Date.now() - startedAt });
          return;
        }
        if (Date.now() - startedAt >= timeoutMs) {
          resolve({ met: false, value: value, timedOut: true, elapsedMs: Date.now() - startedAt });
          return;
        }
        setTimeout(tick, pollMs);
      }
      tick();
    });
  }

  /*
   * Wait until `fieldId` holds a non-empty value (i.e. Gemini's update_form_fields
   * landed). This is the reliable "the field got filled" gate for the answer step.
   */
  function waitForFieldValue(fieldId, opts) {
    return waitForCondition(function () {
      var f = readField(fieldId);
      var v = f.domValue != null ? f.domValue : f.ssValue;
      return (v != null && String(v).length > 0) ? f : false;
    }, opts);
  }

  /*
   * Wait until `fieldId` is genuinely CONFIRMED. The authoritative signal is the
   * sessionStorage `confirmed` flag (`ssConfirmed`): `update_form_fields` fills the
   * field as UNCONFIRMED, and only the `confirm_field` round-trip
   * (WebFormConnection.handleConfirmFieldRequest) flips sessionStorage to confirmed.
   * We deliberately do NOT accept `domConfirmed` -- `fieldManager.applyUpdates` sets
   * `data-vff-confirmed="true"` at FILL time (a decoration), so it is true before
   * any "yes" is processed and would false-pass (Codex review, PR #123). Advance is
   * recorded for corroboration only. Returns the snapshot (+ `_advanced`) when met.
   */
  function waitForConfirmed(fieldId, opts) {
    return waitForCondition(function () {
      var f = readField(fieldId);
      if (f.ssConfirmed === true) {
        var nf = null;
        try { nf = lastNextField(); } catch (e) {}
        f._lastNextField = nf;
        f._advanced = nf != null && nf !== fieldId;
        return f;
      }
      return false;
    }, opts);
  }

  /*
   * Clear the target field's state (DOM value + the sessionStorage entry) so a
   * RERUN cannot read a STALE filled/confirmed value from a previous attempt and
   * false-pass before any new audio is processed -- sessionStorage survives the
   * reload the RUNBOOK's retry does (Codex review, PR #123). Call before a cycle.
   */
  function clearFieldState(fieldId) {
    try {
      var el = document.getElementById(fieldId);
      if (el && 'value' in el) {
        el.value = '';
        el.removeAttribute('data-vff-confirmed');
      }
    } catch (e) { /* ignore */ }
    try {
      var raw = sessionStorage.getItem('schema_form_state');
      if (raw) {
        var st = JSON.parse(raw);
        if (st && st.fieldValues && st.fieldValues[fieldId]) {
          delete st.fieldValues[fieldId];
          sessionStorage.setItem('schema_form_state', JSON.stringify(st));
        }
      }
    } catch (e) { /* ignore */ }
  }

  /*
   * Best-effort "Gemini finished speaking" wait, kept for PACING only (never for
   * correctness -- use the outcome waiters above for that). Resolves on a quiet
   * window after vffOnAudioPlaybackEnd, OR after timeoutMs. settleMs is generous
   * because Gemini streams chunky audio. Always resolves (timedOut flag tells you
   * which path); callers should treat a timeout as "proceed anyway", not failure.
   */
  function waitForGeminiQuestion(opts) {
    opts = opts || {};
    var settleMs = opts.settleMs || 1200;
    var timeoutMs = opts.timeoutMs || 20000;

    return new Promise(function (resolve) {
      var prev = window.vffOnAudioPlaybackEnd;
      var settleTimer = null;
      var hardTimer = null;
      var done = false;
      var sawAudio = false;

      function finish(timedOut) {
        if (done) return;
        done = true;
        if (settleTimer) clearTimeout(settleTimer);
        if (hardTimer) clearTimeout(hardTimer);
        window.vffOnAudioPlaybackEnd = prev; // restore
        resolve({ timedOut: !!timedOut, sawAudio: sawAudio });
      }

      window.vffOnAudioPlaybackEnd = function () {
        if (typeof prev === 'function') {
          try { prev(); } catch (e) { /* ignore app handler error */ }
        }
        sawAudio = true;
        if (settleTimer) clearTimeout(settleTimer);
        settleTimer = setTimeout(function () { finish(false); }, settleMs);
      };

      hardTimer = setTimeout(function () { finish(true); }, timeoutMs);
    });
  }

  /*
   * Read a field's current value + confirmed state from BOTH the DOM (the
   * load-bearing surface: fieldManager writes here) and sessionStorage (the app's
   * mirror). Returns raw + digit-normalized value so the caller can compare
   * robustly against an LLM-produced value (strips spaces, commas, punctuation).
   */
  function readField(fieldId) {
    var el = document.getElementById(fieldId);
    var domValue = el ? (el.value !== undefined ? el.value : null) : null;
    var domConfirmed = el ? el.getAttribute('data-vff-confirmed') === 'true' : false;

    var ssValue = null;
    var ssConfirmed = null;
    try {
      var raw = sessionStorage.getItem('schema_form_state');
      if (raw) {
        var st = JSON.parse(raw);
        var fv = st && st.fieldValues && st.fieldValues[fieldId];
        if (fv) {
          ssValue = fv.value !== undefined ? fv.value : null;
          ssConfirmed = !!fv.confirmed;
        }
      }
    } catch (e) { /* ignore parse error */ }

    var src = domValue != null ? domValue : (ssValue != null ? ssValue : '');
    var digits = String(src).replace(/[^0-9]/g, '');

    return {
      fieldId: fieldId,
      domValue: domValue,
      domConfirmed: domConfirmed,
      ssValue: ssValue,
      ssConfirmed: ssConfirmed,
      digits: digits
    };
  }

  function lastNextField() {
    return inject().getLastNextField();
  }

  /*
   * Run the full answer -> fill -> confirm -> advance cycle for one numeric field,
   * gating on concrete OUTCOMES (not audio). Returns a PASS/FAIL/FLAKY report the
   * agent reads back. Non-deterministic-LLM tolerant: normalizes digits, and
   * classifies a stuck/timeout as FLAKY (not FAIL). Pre-load the two fixtures and
   * pass them in (digitsBuf, yesBuf) so this function never awaits the network.
   */
  async function runCycle(opts) {
    opts = opts || {};
    var fieldId = opts.fieldId;
    var expectDigits = opts.expectDigits || '1234567';
    var digitsBuf = opts.digitsBuf;
    var yesBuf = opts.yesBuf;
    var turnTimeoutMs = opts.turnTimeoutMs || 35000;
    var report = { fieldId: fieldId, steps: [], verdict: 'FLAKY' };

    // Clear any stale value/confirm from a previous attempt FIRST -- sessionStorage
    // survives the reload a retry does, so without this a rerun could read the old
    // filled+confirmed value and false-pass before any new audio (Codex, PR #123).
    clearFieldState(fieldId);
    report.steps.push({ step: 'clear-state', cleared: readField(fieldId).digits === '' });

    // Let Gemini ask the first question (pacing only; do not gate correctness).
    var q1 = await waitForGeminiQuestion({ timeoutMs: 18000 });
    report.steps.push({ step: 'wait-first-question', sawAudio: q1.sawAudio, timedOut: q1.timedOut });

    // Answer: inject the digits, then wait for the field to actually fill.
    await injectUtterance(digitsBuf);
    var filled = await waitForFieldValue(fieldId, { timeoutMs: turnTimeoutMs });
    var fillSnap = readField(fieldId);
    report.steps.push({ step: 'fill', met: filled.met, elapsedMs: filled.elapsedMs, raw: fillSnap.domValue, digits: fillSnap.digits });

    if (!filled.met) { report.verdict = 'FLAKY'; report.reason = 'field never filled'; return report; }
    if (fillSnap.digits !== expectDigits) { report.verdict = 'FAIL'; report.reason = 'wrong value: got ' + JSON.stringify(fillSnap.domValue); return report; }

    // Snapshot the next-field BASELINE before injecting "yes". The advance check
    // below requires lastNextField to CHANGE from this baseline, not merely to
    // differ from `fieldId` -- otherwise a stale next-field value left by an earlier
    // transition in the same page would make the advance wait resolve instantly,
    // false-passing the exact confirm-without-navigation failure we mean to catch
    // (Codex, PR #123).
    var baselineNext = (function(){ try { return lastNextField(); } catch (e) { return null; } })();

    // Let Gemini ask the verify question (pacing), then confirm.
    var q2 = await waitForGeminiQuestion({ timeoutMs: 18000 });
    report.steps.push({ step: 'wait-verify-question', sawAudio: q2.sawAudio, timedOut: q2.timedOut, baselineNext: baselineNext });

    await injectUtterance(yesBuf);
    // PASS REQUIRES a real confirmation: the authoritative sessionStorage `confirmed`
    // flag, which only the confirm_field round-trip sets. We do NOT accept the
    // fill-time DOM decoration (`domConfirmed`), which would false-pass (Codex, PR #123).
    var confirmW = await waitForConfirmed(fieldId, { timeoutMs: turnTimeoutMs });
    var confSnap = readField(fieldId);
    report.steps.push({ step: 'confirm', met: confirmW.met, elapsedMs: confirmW.elapsedMs, ssConfirmed: confSnap.ssConfirmed, domConfirmed: confSnap.domConfirmed });
    if (!confirmW.met) { report.verdict = 'FLAKY'; report.reason = 'field never confirmed (sessionStorage confirmed flag never set within timeout)'; return report; }

    // PASS also REQUIRES the ADVANCE: the RUNBOOK proves fill -> confirm -> ADVANCE,
    // so confirmation alone is not enough. A bug where confirm succeeds but
    // navigation never happens (e.g. the 0ux receive-loop crash after the first
    // fill) must NOT report a successful cycle (Codex, PR #123). Require
    // lastNextField to CHANGE from the pre-"yes" baseline AND land on a field other
    // than the one just confirmed.
    var advanceW = await waitForCondition(function () {
      var nf = null; try { nf = lastNextField(); } catch (e) {}
      return (nf != null && nf !== fieldId && nf !== baselineNext) ? nf : false;
    }, { timeoutMs: turnTimeoutMs });
    report.steps.push({ step: 'advance', met: advanceW.met, elapsedMs: advanceW.elapsedMs, baselineNext: baselineNext, lastNextField: advanceW.value || (function(){try{return lastNextField();}catch(e){return null;}})() });
    if (!advanceW.met) { report.verdict = 'FLAKY'; report.reason = 'confirmed but never advanced to a NEW next field (navigation/onNextField never fired)'; return report; }

    report.verdict = 'PASS';
    return report;
  }

  window.__VFF_HARNESS = {
    SAMPLE_RATE: SAMPLE_RATE,
    loadFixture: loadFixture,
    injectUtterance: injectUtterance,
    waitForGeminiQuestion: waitForGeminiQuestion,
    waitForCondition: waitForCondition,
    waitForFieldValue: waitForFieldValue,
    waitForConfirmed: waitForConfirmed,
    clearFieldState: clearFieldState,
    readField: readField,
    lastNextField: lastNextField,
    runCycle: runCycle,
    isNativeVad: function () { return inject().isNativeVad(); }
  };

  console.log('[VFF Harness] installed window.__VFF_HARNESS');
  return window.__VFF_HARNESS;
})();
