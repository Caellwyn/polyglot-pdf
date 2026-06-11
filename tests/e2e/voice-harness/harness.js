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
   * Continuous silence streamer (bd polyglot-pdf-95uy). Gemini's NATIVE VAD
   * needs an UNBROKEN audio stream to detect end-of-utterance: a fixed 500 ms
   * tail followed by dead air leaves the turn open forever (the model waits
   * for more audio; 3/3 stalls in the 95uy repro). The real client streams the
   * mic continuously in native mode, so the harness must too: after each
   * utterance, stream zero-filled frames at real-time pace until the next
   * utterance (or an explicit stopSilenceStream()).
   */
  var _silenceStream = null;

  function startSilenceStream(chunkMs) {
    stopSilenceStream();
    chunkMs = chunkMs || CHUNK_MS;
    var h = inject();
    var bytesPerChunk = Math.round((SAMPLE_RATE * BYTES_PER_SAMPLE * chunkMs) / 1000);
    var silence = new ArrayBuffer(bytesPerChunk);
    var stream = { alive: true, stop: function () { stream.alive = false; if (_silenceStream === stream) _silenceStream = null; } };
    (async function pump() {
      while (stream.alive) {
        try { h.sendAudio(silence.slice(0)); } catch (e) { stream.stop(); return; }
        await sleep(chunkMs);
      }
    })().catch(function (e) {
      stream.stop();
      try { console.error('[VFF Harness] silence pump unexpected error', e); } catch (_) {}
    });
    _silenceStream = stream;
    return stream;
  }

  function stopSilenceStream() {
    if (_silenceStream) _silenceStream.stop();
  }

  /*
   * Stream a PCM16 ArrayBuffer into the WS as ~20 ms chunks, pacing in real time
   * so Gemini's VAD/turn logic behaves like a live mic. VAD-mode aware, mirroring
   * the real client: manual VAD brackets the burst with activity_start/end;
   * native VAD streams continuously -- the utterance, then unbroken real-time
   * silence (see startSilenceStream above) so Gemini's own VAD can close the turn.
   */
  async function injectUtterance(pcmBuffer, opts) {
    opts = opts || {};
    var chunkMs = opts.chunkMs || CHUNK_MS;
    var h = inject();
    var native = h.isNativeVad();

    var bytesPerChunk = Math.round((SAMPLE_RATE * BYTES_PER_SAMPLE * chunkMs) / 1000);

    // Pause the inter-turn silence stream while the utterance frames go out
    // (two writers would double-pace the stream).
    stopSilenceStream();

    if (!native) {
      h.sendActivityStart();
    }

    for (var pos = 0; pos < pcmBuffer.byteLength; pos += bytesPerChunk) {
      var end = Math.min(pos + bytesPerChunk, pcmBuffer.byteLength);
      h.sendAudio(pcmBuffer.slice(pos, end));
      await sleep(chunkMs); // pace at ~real time
    }

    if (native) {
      startSilenceStream(chunkMs);
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
   *
   * SAME-PAGE rerun (no reload): the app exposes resetFieldState on the inject
   * hook (bd polyglot-pdf-o1c), which routes the clear through SchemaFormStateManager
   * (save + schemaFormStateChange dispatch) AND refreshes the live
   * WebFormConnection.state -- so SchemaForm's React state and the connection's
   * in-memory copy are also reset, not just sessionStorage. Prefer it when present;
   * fall back to the direct DOM + storage clear (still correct for the documented
   * reload-between-attempts path, and for an app build predating the hook).
   */
  function clearFieldState(fieldId) {
    try {
      var el = document.getElementById(fieldId);
      if (el && 'value' in el) {
        el.value = '';
        el.removeAttribute('data-vff-confirmed');
      }
    } catch (e) { /* ignore */ }
    var h = window.__VFF_TEST_INJECT;
    if (h && typeof h.resetFieldState === 'function') {
      try {
        h.resetFieldState(fieldId);
        return;
      } catch (e) { /* fall through to the direct clear below */ }
    }
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
    // requireAdvance: PASS also requires Gemini to move to a NEW next field after
    // confirm (the default -- proves fill -> confirm -> ADVANCE). Set false only
    // for a field where the advance is not expected (e.g. the last field before
    // a section boundary is handled by the multi-section scenario's own
    // section-cross assertion instead). bd polyglot-pdf-8k8.
    var requireAdvance = opts.requireAdvance !== false;
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

    // ORDER-TOLERANT CONFIRM (bd polyglot-pdf-par / tfz): 2.5 native-audio calls
    // confirm_field RELIABLY but often PROACTIVELY -- right after speaking the
    // verify question, BEFORE we inject "yes". A confirm that already landed must
    // count as success, not a FLAKY "never confirmed". So check the authoritative
    // sessionStorage `confirmed` flag BEFORE injecting "yes": if it is already
    // true, the field is confirmed (record it, still inject "yes" because a real
    // user answers, then proceed). Otherwise inject "yes" and wait for it. We do
    // NOT accept the fill-time DOM decoration (`domConfirmed`), which would
    // false-pass (Codex, PR #123).
    var preYes = readField(fieldId);
    var confirmedEarly = preYes.ssConfirmed === true;
    var confirmW;
    if (confirmedEarly) {
      // Confirm already landed on the verify turn. Still inject "yes" (the real
      // demo flow speaks it), but do not gate on a post-yes flip -- the field is
      // already confirmed, and re-confirming an already-confirmed field is a no-op.
      await injectUtterance(yesBuf);
      confirmW = { met: true, elapsedMs: 0 };
    } else {
      await injectUtterance(yesBuf);
      confirmW = await waitForConfirmed(fieldId, { timeoutMs: turnTimeoutMs });
      if (!confirmW.met) {
        // bd polyglot-pdf-95uy secondary quirk: ~50% of native-VAD runs emit a
        // ctrl46 control token + a second turn_complete and then stall even with
        // silence streaming. A single re-inject of the "yes" recovers the turn;
        // retry once before declaring FLAKY.
        await injectUtterance(yesBuf);
        confirmW = await waitForConfirmed(fieldId, { timeoutMs: turnTimeoutMs });
        confirmW.retried = true;
      }
    }
    var confSnap = readField(fieldId);
    report.steps.push({ step: 'confirm', met: confirmW.met, when: confirmedEarly ? 'early' : 'post-yes', elapsedMs: confirmW.elapsedMs, ssConfirmed: confSnap.ssConfirmed, domConfirmed: confSnap.domConfirmed });
    if (!confirmW.met) { report.verdict = 'FLAKY'; report.reason = 'field never confirmed (sessionStorage confirmed flag never set within timeout)'; return report; }

    // PASS also REQUIRES the ADVANCE: the RUNBOOK proves fill -> confirm -> ADVANCE,
    // so confirmation alone is not enough. A bug where confirm succeeds but
    // navigation never happens (e.g. the 0ux receive-loop crash after the first
    // fill) must NOT report a successful cycle (Codex, PR #123). Require
    // lastNextField to CHANGE from the pre-"yes" baseline AND land on a field other
    // than the one just confirmed. Skipped when requireAdvance is false (the
    // multi-section scenario asserts the section CROSS itself for the last field
    // in a section -- bd polyglot-pdf-8k8).
    if (requireAdvance) {
      var advanceW = await waitForCondition(function () {
        var nf = null; try { nf = lastNextField(); } catch (e) {}
        return (nf != null && nf !== fieldId && nf !== baselineNext) ? nf : false;
      }, { timeoutMs: turnTimeoutMs });
      report.steps.push({ step: 'advance', met: advanceW.met, elapsedMs: advanceW.elapsedMs, baselineNext: baselineNext, lastNextField: advanceW.value || (function(){try{return lastNextField();}catch(e){return null;}})() });
      if (!advanceW.met) { report.verdict = 'FLAKY'; report.reason = 'confirmed but never advanced to a NEW next field (navigation/onNextField never fired)'; return report; }
    } else {
      report.steps.push({ step: 'advance', skipped: true, reason: 'requireAdvance=false (section-cross asserted by scenario)' });
    }

    report.verdict = 'PASS';
    return report;
  }

  /*
   * Seed one or more fields as filled-AND-confirmed via the dev hook
   * (__VFF_TEST_INJECT.seedFieldConfirmed), which routes through the SAME
   * SchemaFormStateManager write path a genuine confirm uses. This lets the
   * multi-section scenario drive ONE numeric field by voice and have the REAL
   * section auto-advance fire when that last unconfirmed VISIBLE field in the
   * section is confirmed. seedMap is { fieldId: value }. Returns
   * { seeded: [...], failed: [...] } -- "failed" entries did not read back as
   * confirmed (a setup failure, not a signal about the code under test).
   */
  function seedFields(seedMap) {
    var h = inject();
    if (typeof h.seedFieldConfirmed !== 'function') {
      throw new Error('seedFields: __VFF_TEST_INJECT.seedFieldConfirmed is missing (app build predates bd polyglot-pdf-8k8).');
    }
    var seeded = [];
    var failed = [];
    Object.keys(seedMap).forEach(function (fieldId) {
      var ok = false;
      try { ok = h.seedFieldConfirmed(fieldId, seedMap[fieldId]); } catch (e) { ok = false; }
      // Verify the seed actually took: the confirmed flag must read back true via
      // the SAME authoritative path the assertions use (sessionStorage ssConfirmed).
      var f = readField(fieldId);
      if (ok && f.ssConfirmed === true) {
        seeded.push(fieldId);
      } else {
        failed.push(fieldId);
      }
    });
    return { seeded: seeded, failed: failed };
  }

  /*
   * Read the CURRENT section from sessionStorage: { id, order }. order is the
   * 1-based section number (schema.sections[*].order). Returns { id:null,
   * order:null } when unreadable. This is the authoritative "which section are we
   * in" signal -- SchemaFormStateManager.switchToSection writes currentSectionId
   * and moves the old id into completedSections.
   */
  function getCurrentSection() {
    try {
      var raw = sessionStorage.getItem('schema_form_state');
      if (!raw) return { id: null, order: null };
      var st = JSON.parse(raw);
      var id = st && st.currentSectionId != null ? st.currentSectionId : null;
      var order = null;
      if (id != null && st.schema && Array.isArray(st.schema.sections)) {
        var sec = st.schema.sections.filter(function (s) { return s.id === id; })[0];
        if (sec && sec.order != null) order = sec.order;
      }
      return { id: id, order: order };
    } catch (e) {
      return { id: null, order: null };
    }
  }

  /*
   * Read the completed-section ids from sessionStorage (serialized as an array on
   * save). Used to corroborate that the OLD section was finalized, not just that a
   * new one was entered.
   */
  function getCompletedSections() {
    try {
      var raw = sessionStorage.getItem('schema_form_state');
      if (!raw) return [];
      var st = JSON.parse(raw);
      return Array.isArray(st && st.completedSections) ? st.completedSections : [];
    } catch (e) {
      return [];
    }
  }

  /*
   * Wait until the current section's order reaches targetOrder. A section switch
   * tears down + restarts the Gemini session, so the default timeout is generous.
   * Returns the waitForCondition result ({ met, value:{id,order}, ... }).
   */
  function waitForSection(targetOrder, opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs || 40000;
    return waitForCondition(function () {
      var s = getCurrentSection();
      return s.order === targetOrder ? s : false;
    }, { timeoutMs: timeoutMs });
  }

  /*
   * Best-effort "Gemini greeted the new section" wait. Hooks window.vffOnSectionChanged
   * (fired on the backend section_switched message) the same overridable way
   * waitForGeminiQuestion hooks vffOnAudioPlaybackEnd. PACING-style: always resolves
   * (timedOut flag tells you which path), so a timeout means "proceed", not failure --
   * the authoritative section-cross proof is waitForSection + lastNextField, not this.
   */
  function waitForSectionGreeting(opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs || 20000;
    return new Promise(function (resolve) {
      var prev = window.vffOnSectionChanged;
      var hardTimer = null;
      var done = false;
      function finish(timedOut, sawSwitch) {
        if (done) return;
        done = true;
        if (hardTimer) clearTimeout(hardTimer);
        window.vffOnSectionChanged = prev; // restore
        resolve({ timedOut: !!timedOut, sawSectionChanged: !!sawSwitch });
      }
      window.vffOnSectionChanged = function () {
        if (typeof prev === 'function') {
          try { prev(); } catch (e) { /* ignore app handler error */ }
        }
        finish(false, true);
      };
      hardTimer = setTimeout(function () { finish(true, false); }, timeoutMs);
    });
  }

  /*
   * The DEMO REHEARSAL: drive a multi-field, multi-section voice session and gate
   * on fill -> confirm -> advance ... -> SECTION CROSS -> continue. This is the
   * scenario bd polyglot-pdf-wpw is judged by.
   *
   * Strategy (bd polyglot-pdf-8k8): seed the non-target section-1 fields confirmed
   * so the ONLY field Gemini fills+confirms by voice in section 1 is the numeric
   * target; confirming it is the last unconfirmed VISIBLE field, so the REAL FE
   * auto-advance (handleConfirmFieldRequest -> computeNextField null ->
   * switchToSection) fires. Then a SECOND voice field is filled in section 2 to
   * prove multi-field-across-the-boundary.
   *
   * opts: {
   *   digitsBuf, yesBuf,                  // section-1 fixtures (reused from runCycle)
   *   s1FieldId, s1ExpectDigits,          // default p1_line1_aliennumber / '1234567'
   *   s1Seed,                             // { fieldId: value } confirmed before leg 1
   *   s2FieldId, s2ExpectDigits, s2DigitsBuf, // section-2 voice field + its fixture
   *   s2Seed,                             // { fieldId: value } confirmed before leg 2
   *                                       //   (the section-2 fields BEFORE the voice
   *                                       //   target, so the target is the next field)
   *   targetSectionOrder                  // default 2
   * }
   * s2DigitsBuf is REQUIRED -- the scenario's whole point is the second voice fill
   * across the boundary; omitting it is a setup error, not an optional skip.
   * Returns { verdict, crossedToSection: bool, legs: [...] }.
   */
  async function runMultiSectionScenario(opts) {
    opts = opts || {};
    var digitsBuf = opts.digitsBuf;
    var yesBuf = opts.yesBuf;
    var s1FieldId = opts.s1FieldId || 'p1_line1_aliennumber';
    var s1ExpectDigits = opts.s1ExpectDigits || '1234567';
    // Seed the non-target section-1 fields confirmed. checkbox4 is set to a
    // NON-"[0]" option so the show_if-gated p1_line5a/b/c name fields stay hidden
    // (shouldShowField equals-check) and do not block the section-complete ->
    // switch transition -- verified against form-kits/i-90/schema.json.
    var s1Seed = opts.s1Seed || {
      p1_checkbox4: 'P1_checkbox4[1]',
      p1_line2_acctidentifier: '123456789012',
      p1_line3a_familyname: 'Smith',
      p1_line3b_givenname: 'Jane',
      p1_line3c_middlename: 'A'
    };
    var s2FieldId = opts.s2FieldId || 'p1_line6f_zipcode';
    var s2ExpectDigits = opts.s2ExpectDigits || '12345';
    var s2DigitsBuf = opts.s2DigitsBuf;
    // Seed the section-2 fields that come BEFORE the voice target so the target
    // is the NEXT field computeNextField returns -- otherwise Gemini is asked for
    // the first mailing-address field (p1_line6a_incareofname), not the ZIP, and
    // leg 2 times out on the wrong field (Codex/fresh-eyes PR #133). The unit
    // radio (p1_unit_type6c_unit) is seeded non-empty, which SHOWS the apt field
    // (show_if is_not_empty), so the apt field is seeded too -- verified against
    // form-kits/i-90/schema.json. Only fields strictly before p1_line6f_zipcode.
    var s2Seed = opts.s2Seed || {
      p1_line6a_incareofname: 'Acme Corp',
      p1_line6b_streetnumbername: '100 Main St',
      p1_unit_type6c_unit: 'P1_checkbox6c_Unit[1]',
      p1_line6c_aptsteflrnumber: '4B',
      p1_line6d_cityortown: 'Springfield',
      p1_line6e_state: 'IL'
    };
    var targetSectionOrder = opts.targetSectionOrder || 2;

    var result = { verdict: 'FLAKY', crossedToSection: false, legs: [] };

    // s2DigitsBuf is mandatory: leg 2 (the second voice fill across the boundary)
    // is the scenario's reason to exist. A missing fixture is a SETUP error -- it
    // must NOT silently downgrade to a section-cross-only PASS (Codex/fresh-eyes
    // PR #133: a demo rehearsal that "passes" without proving the second fill is a
    // false green).
    if (!s2DigitsBuf) {
      result.verdict = 'FLAKY';
      result.reason = 'setup-error: s2DigitsBuf (the section-2 voice fixture) is required; leg 2 is not optional';
      return result;
    }

    // --- Setup: seed the non-target fields confirmed UP FRONT -- BOTH the
    // section-1 fields AND the section-2 prefix fields (those before the leg-2
    // voice target). The section-2 prefix MUST be seeded BEFORE leg 1 triggers the
    // switch: switchToSection builds the new section's handshake (current_values +
    // initial_field_hint) from sessionStorage AT SWITCH TIME, so a section-2 field
    // seeded AFTER the switch is too late -- Gemini was already prompted for the
    // first address field, and seedFieldConfirmed only updates browser state, it
    // does not re-handshake the live Gemini session (Codex PR #133 round 2).
    // Seeding the prefix now means the switch's initial_field_hint resolves to the
    // ZIP target. The fields are in two different sections, but sessionStorage
    // fieldValues is flat (keyed by field id), so a single seed pass sets them all.
    var seedAll = {};
    Object.keys(s1Seed).forEach(function (k) { seedAll[k] = s1Seed[k]; });
    Object.keys(s2Seed).forEach(function (k) { seedAll[k] = s2Seed[k]; });
    var seed = seedFields(seedAll);
    result.legs.push({ leg: 'seed', seeded: seed.seeded, failed: seed.failed });
    if (seed.failed.length > 0) {
      result.verdict = 'FLAKY';
      result.reason = 'seed-setup-failed: ' + seed.failed.join(',') + ' did not read back confirmed';
      return result;
    }

    // --- Leg 1: voice-fill + confirm the last unconfirmed section-1 field, then
    // assert the REAL section auto-advance crosses into the target section. The
    // cycle's own advance check is skipped (requireAdvance:false) because we assert
    // the SECTION CROSS here, not an in-section advance. ---
    var leg1 = await runCycle({
      fieldId: s1FieldId, expectDigits: s1ExpectDigits,
      digitsBuf: digitsBuf, yesBuf: yesBuf, requireAdvance: false
    });
    leg1.leg = 'section1-fill';
    result.legs.push(leg1);
    if (leg1.verdict !== 'PASS') {
      result.verdict = leg1.verdict; // FAIL (wrong value) or FLAKY (never filled/confirmed)
      result.reason = 'leg1 ' + leg1.verdict + ': ' + (leg1.reason || 'see steps');
      return result;
    }

    // The crossing. Gate on the REAL switch signals, not just currentSectionId:
    // the frontend writes currentSectionId BEFORE the backend acknowledges the
    // switch, so waitForSection alone could pass on a backend switch that never
    // completed (Codex PR #133 round 2). A genuine cross requires ALL of:
    //   (a) currentSectionId order reached the target (waitForSection),
    //   (b) the OLD section moved into completedSections (FE finalized it),
    //   (c) vffOnSectionChanged fired (the backend sent section_switched),
    //   (d) lastNextField points at the expected NEXT field in the new section
    //       -- the leg-2 target, since its section-2 prefix is seeded confirmed.
    // Install the section-changed watcher BEFORE awaiting the section state so a
    // fast switch (vffOnSectionChanged firing during waitForSection) is still
    // captured -- otherwise the hook installs after the event and reports a
    // spurious sawSectionChanged:false.
    var s1SectionId = getCurrentSection().id; // the section we are leaving
    var greetP = waitForSectionGreeting();
    var sectionW = await waitForSection(targetSectionOrder);
    var greet = await greetP;
    // Give lastNextField a moment to settle to the new section's hint, then read.
    var nextHintW = await waitForCondition(function () {
      var nf = null; try { nf = lastNextField(); } catch (e) {}
      return nf === s2FieldId ? nf : false;
    }, { timeoutMs: 10000 });
    var completed = getCompletedSections();
    var oldSectionFinalized = completed.indexOf(s1SectionId) !== -1;
    var nextAfterCross = (function () { try { return lastNextField(); } catch (e) { return null; } })();
    result.legs.push({
      leg: 'section-cross',
      orderReached: sectionW.met,
      currentSection: getCurrentSection(),
      oldSectionFinalized: oldSectionFinalized,
      sawSectionChanged: greet.sawSectionChanged,
      nextField: nextAfterCross,
      nextIsTarget: nextHintW.met
    });
    if (!sectionW.met) {
      result.verdict = 'FLAKY';
      result.reason = 'confirmed section-1 field but currentSectionId never reached section ' + targetSectionOrder;
      return result;
    }
    if (!greet.sawSectionChanged) {
      result.verdict = 'FLAKY';
      result.reason = 'currentSectionId advanced but the backend section_switched (vffOnSectionChanged) never fired -- switch not acknowledged';
      return result;
    }
    if (!oldSectionFinalized) {
      result.verdict = 'FLAKY';
      result.reason = 'crossed sections but the old section (' + s1SectionId + ') was never moved into completedSections';
      return result;
    }
    if (!nextHintW.met) {
      result.verdict = 'FLAKY';
      result.reason = 'crossed into section ' + targetSectionOrder + ' but Gemini was pointed at ' + nextAfterCross + ', not the seeded leg-2 target ' + s2FieldId;
      return result;
    }
    result.crossedToSection = true;

    // --- Leg 2: voice-fill the section-2 target -- proves multi-field across the
    // boundary. Its section-2 prefix was seeded confirmed UP FRONT (above), so the
    // switch handshake already pointed Gemini at this field. The target is not last
    // in its section, so the cycle's normal advance check applies. ---
    clearFieldState(s2FieldId);
    var leg2 = await runCycle({
      fieldId: s2FieldId, expectDigits: s2ExpectDigits,
      digitsBuf: s2DigitsBuf, yesBuf: yesBuf
    });
    leg2.leg = 'section2-fill';
    result.legs.push(leg2);
    if (leg2.verdict !== 'PASS') {
      result.verdict = leg2.verdict;
      result.reason = 'leg2 ' + leg2.verdict + ': ' + (leg2.reason || 'see steps');
      return result;
    }

    result.verdict = 'PASS';
    return result;
  }

  window.__VFF_HARNESS = {
    SAMPLE_RATE: SAMPLE_RATE,
    loadFixture: loadFixture,
    injectUtterance: injectUtterance,
    startSilenceStream: startSilenceStream,
    stopSilenceStream: stopSilenceStream,
    waitForGeminiQuestion: waitForGeminiQuestion,
    waitForCondition: waitForCondition,
    waitForFieldValue: waitForFieldValue,
    waitForConfirmed: waitForConfirmed,
    clearFieldState: clearFieldState,
    readField: readField,
    lastNextField: lastNextField,
    runCycle: runCycle,
    seedFields: seedFields,
    getCurrentSection: getCurrentSection,
    getCompletedSections: getCompletedSections,
    waitForSection: waitForSection,
    waitForSectionGreeting: waitForSectionGreeting,
    runMultiSectionScenario: runMultiSectionScenario,
    isNativeVad: function () { return inject().isNativeVad(); }
  };

  console.log('[VFF Harness] installed window.__VFF_HARNESS');
  return window.__VFF_HARNESS;
})();
