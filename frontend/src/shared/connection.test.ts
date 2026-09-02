/**
 * Spec tests for the Connection Manager (connection.ts).
 *
 * These encode the DOCUMENTED behavior of createConnectionManager, not the
 * shape of the object it returns. They were re-derived when the suite was
 * un-rotted from connection.test.ts.NEEDS_SECTION_REFACTOR (bd polyglot-pdf-uov.5,
 * the T1.2 slice of the spec-driven test epic). The old suite asserted dead
 * names (currentPartId, startSection/switchSection/completeSection/
 * getCurrentSection/getCompletedSections) that the section-rename
 * (bd polyglot-pdf-gfb.4) removed; this rewrite targets the current API and the
 * behaviors the bead names: (a) the section-based state contract and (b) the
 * audio-queue barge-in flush/resume. (A third -- activity-signal suppression in
 * native-VAD mode -- went with that mode; bd polyglot-pdf-v1m8g.)
 *
 * WebFormConnection is mocked, so backend-driven handshake callbacks
 * is simulated by capturing the callbacks object the factory passes into the
 * WebFormConnection constructor and invoking it directly.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createConnectionManager } from './connection'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'

// Capture the most recent ConnectionCallbacks the factory hands to
// WebFormConnection, plus the AudioManager mock, so a test can drive the
// backend-originated callbacks and assert on the
// audio layer the factory wires up.
let capturedCallbacks: any = null
let audioManagerMock: any = null
let webFormConnectionMock: any = null

vi.mock('./fieldManager', () => ({
  createFieldManager: vi.fn(() => ({
    cleanup: vi.fn(),
    // disconnect() tears the field manager down via destroy() (the re-prompt
    // suite is the first to exercise disconnect through this mock).
    destroy: vi.fn()
  }))
}))

vi.mock('./audioManager', () => ({
  createAudioManager: vi.fn(() => {
    audioManagerMock = {
      cleanup: vi.fn(),
      // disconnect() tears the audio manager down via destroy() (first
      // exercised by the re-prompt suite's disconnect test).
      destroy: vi.fn(),
      startRecording: vi.fn(),
      stopRecording: vi.fn(),
      isRecording: vi.fn(() => false),
      // Default: Gemini IS speaking, so a barge-in flush is expected.
      isSpeaking: vi.fn(() => true),
      // Both signals (bd polyglot-pdf-uxc6s). isModelSpeaking is what the
      // FLUSH / re-prompt sites read (model PCM scheduled, clip or not);
      // isSpeaking is the clip-suppressed one the SUSPEND/RESUME pair reads.
      // Each test sets the one its site under test actually consults.
      isModelSpeaking: vi.fn(() => true),
      isAnyAudioPlaying: vi.fn(() => true),
      flushAudioQueue: vi.fn(),
      resumePlayback: vi.fn(),
      resumeAudioContext: vi.fn(),
      // Used by the shared rehydrateAudio routine (bd polyglot-pdf-z9bc) to
      // re-sync PTT/mute after arming.
      setPTTMode: vi.fn(),
      muteInput: vi.fn(),
      unmuteInput: vi.fn()
    }
    return audioManagerMock
  })
}))

vi.mock('../webFormConnection', () => ({
  WebFormConnection: vi.fn(function (this: any, _schema: any, callbacks: any) {
    // Record the callbacks the factory passes in so a test can fire the
    // backend handshake events by hand.
    capturedCallbacks = callbacks
    this.connect = vi.fn(() => Promise.resolve())
    this.disconnect = vi.fn()
    this.getStatus = vi.fn(() => 'connected')
    this.isSocketOpen = vi.fn(() => true)
    this.sendAudio = vi.fn()
    this.sendActivityStart = vi.fn()
    this.sendActivityEnd = vi.fn(() => Promise.resolve())
    this.sendPrompt = vi.fn()
    this.sendRecoveryPrompt = vi.fn()
    this.sendManualFieldUpdate = vi.fn()
    this.setGetToken = vi.fn()
    this.getState = vi.fn()
    webFormConnectionMock = this
    return this
  })
}))

describe('Connection Manager (connection.ts)', () => {
  let sessionStorageMock: { [key: string]: string }
  let testSchema: FormSchema

  beforeEach(() => {
    capturedCallbacks = null
    audioManagerMock = null
    webFormConnectionMock = null

    // sessionStorage is the single source of truth for client field state
    // (stateless-backend invariant), so the factory reads/writes it on init.
    sessionStorageMock = {}
    global.sessionStorage = {
      getItem: vi.fn((key: string) => sessionStorageMock[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStorageMock[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete sessionStorageMock[key]
      }),
      clear: vi.fn(() => {
        sessionStorageMock = {}
      }),
      length: 0,
      key: vi.fn(() => null)
    } as any

    testSchema = {
      source: 'pdf',
      form_metadata: {
        title: 'Test I-90 Form',
        version: '1.0.0',
        language: 'en',
        form_number: 'I-90',
        edition_date: '01/20/25',
        page_count: 2
      },
      parts: [
        {
          id: 'part-1',
          label: 'Personal Information',
          description: 'Basic information',
          order: 1,
          section_ids: ['section-1a'],
          required: true
        },
        {
          id: 'part-2',
          label: 'Address Information',
          description: 'Contact details',
          order: 2,
          section_ids: ['section-2a'],
          required: true
        }
      ],
      sections: [
        {
          id: 'section-1a',
          label: 'Name',
          order: 1,
          fields: ['field-1', 'field-2']
        },
        {
          id: 'section-2a',
          label: 'Current Address',
          order: 2,
          fields: ['field-3', 'field-4']
        }
      ],
      fields: [
        { id: 'field-1', name: 'First Name', spoken_name: 'first name', type: 'text', section_id: 'section-1a' },
        { id: 'field-2', name: 'Last Name', spoken_name: 'last name', type: 'text', section_id: 'section-1a' },
        { id: 'field-3', name: 'Street Address', spoken_name: 'street address', type: 'text', section_id: 'section-2a' },
        { id: 'field-4', name: 'City', spoken_name: 'city', type: 'text', section_id: 'section-2a' }
      ]
    }
  })

  // ---------------------------------------------------------------------------
  // (a) Section-based state contract
  //
  // The factory must initialize SchemaFormStateManager on creation and persist
  // it under the canonical sessionStorage key, using the SECTION naming the
  // rename (gfb.4) settled on -- currentSectionId, NOT the removed currentPartId.
  // ---------------------------------------------------------------------------
  describe('state initialization (section-based)', () => {
    it('persists initial state under schema_form_state, anchored to the first SECTION', () => {
      createConnectionManager(testSchema, vi.fn(), 'English')

      const stored = sessionStorage.getItem('schema_form_state')
      expect(stored).not.toBeNull()

      const state = JSON.parse(stored as string)
      expect(state.schema.form_metadata.form_number).toBe('I-90')
      // SECTION is the navigation unit -- the position field is currentSectionId,
      // initialized to the first section's id. The removed currentPartId must NOT
      // appear (it would mean the part/section rename regressed).
      expect(state.currentSectionId).toBe('section-1a')
      expect(state.currentPartId).toBeUndefined()
    })

    it('migrates a legacy currentPartId payload forward to currentSectionId on load', () => {
      // A session persisted before the rename (gfb.4) carries currentPartId; the
      // loader must translate it forward so the old key never resurfaces in the
      // in-memory state the factory then drives. NOTE: the migration is lazy --
      // load() rewrites the field in memory but does not re-persist, so we assert
      // on the manager's load() contract directly (the factory consumes exactly
      // this), not on the still-legacy bytes left in sessionStorage.
      sessionStorageMock['schema_form_state'] = JSON.stringify({
        schema: testSchema,
        fieldValues: {},
        currentPartId: 'section-2a',
        completedSections: [],
        validationErrors: {},
        lastUpdated: Date.now(),
        formSessionId: 'fss_legacy',
        loadedFieldIds: [],
        jitModeEnabled: false,
        disclaimerAccepted: false
      })

      // The factory uses SchemaFormStateManager.load() as its state source.
      createConnectionManager(testSchema, vi.fn(), 'English')
      const loaded = SchemaFormStateManager.load()

      expect(loaded?.currentSectionId).toBe('section-2a')
      expect((loaded as any)?.currentPartId).toBeUndefined()

      // Pin the LAZINESS explicitly (so a future change that starts persisting
      // the migration -- or one that clobbers the session with a fresh
      // non-migrated payload -- is a visible diff here, not a silent one): the
      // factory does NOT re-persist the migration, so the raw bytes still carry
      // the legacy currentPartId until the next save().
      const rawBytes = JSON.parse(sessionStorageMock['schema_form_state'])
      expect(rawBytes.currentPartId).toBe('section-2a')
      expect(rawBytes.currentSectionId).toBeUndefined()
    })

    it('reuses persisted state across manager recreations (survives reconnect)', () => {
      createConnectionManager(testSchema, vi.fn(), 'English')
      const first = sessionStorage.getItem('schema_form_state')

      createConnectionManager(testSchema, vi.fn(), 'English')
      const second = sessionStorage.getItem('schema_form_state')

      // Same form + version + recent => the second manager loads the existing
      // state rather than re-initializing (the stateless-reconnect contract).
      const a = JSON.parse(first as string)
      const b = JSON.parse(second as string)
      expect(b.formSessionId).toBe(a.formSessionId)
    })
  })

  // ---------------------------------------------------------------------------
  // (b2) Shared audio rehydration across reconnect paths (bd polyglot-pdf-z9bc)
  //
  // Every reconnect / session-restart cause funnels through ONE rehydrateAudio
  // routine. The AUTOMATIC/INTERNAL reconnects (GoAway, auto-drop) surface via
  // onSessionReady; the warm restart via onSessionRestarted. Audio self-heals on
  // those paths, so the routine must be idempotent: arm the mic only when NOT
  // already recording, and always re-sync PTT -- never double-arm a path that
  // armed just before the ready event.
  // ---------------------------------------------------------------------------
  describe('shared audio rehydration (reconnect consolidation, bd z9bc)', () => {
    async function connected() {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      await manager.connect()
      expect(capturedCallbacks).not.toBeNull()
      // Clear the arm calls made during initial connect so each assertion is scoped
      // to the reconnect callback under test.
      audioManagerMock.startRecording.mockClear()
      audioManagerMock.setPTTMode.mockClear()
      return manager
    }

    it('onSessionReady (GoAway / auto-drop) arms the mic + applies resting mute when NOT already recording', async () => {
      await connected()
      audioManagerMock.isRecording.mockReturnValue(false)
      // Default session is PTT-on, so a freshly-armed mic must start muted (resting).
      audioManagerMock.muteInput.mockClear()

      capturedCallbacks.onSessionReady('sess-1')
      // rehydrateAudio is fire-and-forget from the sync callback; let its microtask run.
      await Promise.resolve()
      await Promise.resolve()

      expect(audioManagerMock.startRecording).toHaveBeenCalledTimes(1)
      // PTT re-synced after arming; a fresh arm (starts unmuted) gets the PTT
      // resting mute applied.
      expect(audioManagerMock.setPTTMode).toHaveBeenCalled()
      expect(audioManagerMock.muteInput).toHaveBeenCalled()
    })

    it('onSessionReady does NOT touch mute state when already recording (preserves an active PTT hold)', async () => {
      await connected()
      // On a real GoAway/auto-drop the worklet survives, so isRecording() stays true.
      // The user could be mid-hold (mic unmuted); re-muting here would truncate speech.
      audioManagerMock.isRecording.mockReturnValue(true)
      audioManagerMock.muteInput.mockClear()
      audioManagerMock.unmuteInput.mockClear()

      capturedCallbacks.onSessionReady('sess-2')
      await Promise.resolve()
      await Promise.resolve()

      // Does NOT re-arm (the failure PR #339 had was the inverse -- an isRecording()
      // guard that skipped the WHOLE arm; here the routine still runs, it just does
      // not duplicate getUserMedia).
      expect(audioManagerMock.startRecording).not.toHaveBeenCalled()
      // PTT gate MODE is still re-synced to the worklet...
      expect(audioManagerMock.setPTTMode).toHaveBeenCalled()
      // ...but mute/unmute is NOT touched: the mic's current mute/hold state is
      // preserved (bd polyglot-pdf-z9bc fresh-eyes gap -- do not truncate an
      // in-progress utterance on a mid-hold reconnect).
      expect(audioManagerMock.muteInput).not.toHaveBeenCalled()
      expect(audioManagerMock.unmuteInput).not.toHaveBeenCalled()
    })

    it('onSessionRestarted (warm restart) also routes through the shared routine', async () => {
      await connected()
      audioManagerMock.isRecording.mockReturnValue(true) // warm restart keeps the mic

      capturedCallbacks.onSessionRestarted()
      await Promise.resolve()
      await Promise.resolve()

      // Warm restart never stopped the mic -> no re-arm, just a PTT re-sync.
      expect(audioManagerMock.startRecording).not.toHaveBeenCalled()
      expect(audioManagerMock.setPTTMode).toHaveBeenCalled()
    })

    it('rehydrate is skipped while paused (a paused session must not re-open the mic)', async () => {
      const manager = await connected()
      audioManagerMock.isRecording.mockReturnValue(true)
      // Pause stops the mic and sets the paused flag.
      manager.pause()
      audioManagerMock.startRecording.mockClear()
      audioManagerMock.setPTTMode.mockClear()
      audioManagerMock.isRecording.mockReturnValue(false)

      capturedCallbacks.onSessionReady('sess-3')
      await Promise.resolve()
      await Promise.resolve()

      // Paused -> the shared routine bails before arming or touching PTT.
      expect(audioManagerMock.startRecording).not.toHaveBeenCalled()
      expect(audioManagerMock.setPTTMode).not.toHaveBeenCalled()
    })

    it('resume() un-blocks AI playback that pause() flushed (bd audio-resume)', async () => {
      const manager = await connected()
      // Pause flushes the AI audio queue, which sets playbackBlocked=true so any
      // in-flight AI audio is discarded.
      manager.pause()
      expect(audioManagerMock.flushAudioQueue).toHaveBeenCalled()
      audioManagerMock.resumePlayback.mockClear()

      // resume() must clear that block; otherwise every AI audio chunk after resume
      // is silently dropped in playAudio() -- the mic comes back but the AI's voice
      // never does. Nothing else clears it on the default path (onVADSpeechEnd early-
      // returns under PTT, the only mode).
      await manager.resume()
      expect(audioManagerMock.resumePlayback).toHaveBeenCalled()
    })

    it('resume() on a CLOSED socket routes to reconnect, not a false "resumed" (bd l8z7)', async () => {
      const manager = await connected()
      manager.pause()

      // The tester repro (22:49Z): an idle-timeout landed during the pause, so
      // the socket is CLOSED even though the manager still offered a resume. The
      // old gate trusted getStatus() alone and could log "Resumed successfully"
      // onto a dead socket, re-arming the mic into a black hole. resume() must
      // instead see the closed socket and hand off to the full reconnect.
      webFormConnectionMock.isSocketOpen.mockReturnValue(false)
      webFormConnectionMock.getStatus.mockReturnValue('idle_timeout')
      webFormConnectionMock.connect.mockClear()

      await manager.resume()

      // Routed to connect()'s full-reconnect path (dead socket -> not the warm
      // restart_gemini_session shortcut), which drives a real WS reconnect...
      expect(webFormConnectionMock.connect).toHaveBeenCalled()
      // ...and the paused flag is cleared so connect() does not re-enter resume.
      expect(manager.isPaused()).toBe(false)
    })

    it('resume() reads isSocketOpen, NOT getStatus: an OPEN socket resumes in place even when status != connected (bd l8z7)', async () => {
      const manager = await connected()
      manager.pause()
      // The DISCRIMINATING case that makes this non-vacuous: the socket is OPEN
      // but getStatus() reads something other than 'connected' (e.g. a transient
      // 'reconnecting' between a warm session_ready and the status settling).
      // The OLD gate (getStatus() !== 'connected') would wrongly bail to a full
      // reconnect here; the fixed gate (isSocketOpen) correctly resumes in place.
      webFormConnectionMock.isSocketOpen.mockReturnValue(true)
      webFormConnectionMock.getStatus.mockReturnValue('reconnecting')
      webFormConnectionMock.connect.mockClear()

      await manager.resume()

      // Warm resume: no full reconnect, mic re-armed via the shared rehydrate.
      expect(webFormConnectionMock.connect).not.toHaveBeenCalled()
      expect(audioManagerMock.resumePlayback).toHaveBeenCalled()
    })

    it('a session (re)establishment clears a STALE playback block (bd nm7z: pause -> idle-timeout -> reconnect)', async () => {
      const manager = await connected()
      // The tester-reproduced kill chain (bugs 0/7): pause() flushes
      // (playbackBlocked=true), the warm connection idle-times-out DURING the
      // pause, and the user comes back via connect() -- so resume(), the only
      // unblocker on that path, never runs. The reconnect's onSessionReady must
      // clear the stale block via the shared rehydrate routine, or every AI
      // chunk after the reconnect is silently discarded (mic works, the AI's
      // voice never returns).
      manager.pause()
      expect(audioManagerMock.flushAudioQueue).toHaveBeenCalled()
      // The idle timeout closed the socket, so the WS reports a non-connected
      // status and connect() takes the FULL-reconnect path (not the warm
      // restart_gemini_session shortcut) -- matching the tester's console trace.
      webFormConnectionMock.getStatus.mockReturnValue('idle_timeout')
      // The reconnect path clears `paused` in connect() (the overlay's Reconnect
      // button), NOT via resume().
      await manager.connect()
      webFormConnectionMock.getStatus.mockReturnValue('connected')
      audioManagerMock.resumePlayback.mockClear()
      audioManagerMock.isRecording.mockReturnValue(false)

      capturedCallbacks.onSessionReady('sess-after-timeout')
      await Promise.resolve()
      await Promise.resolve()

      expect(audioManagerMock.resumePlayback).toHaveBeenCalled()
    })

    it('a MID-PAUSE session-ready does NOT clear the pause block (paused guard runs first)', async () => {
      const manager = await connected()
      manager.pause()
      audioManagerMock.resumePlayback.mockClear()

      // While still paused, a stray ready-callback must not unblock playback --
      // the pause's own flush is intentional; resume() clears it when the user
      // actually resumes.
      capturedCallbacks.onSessionReady('sess-mid-pause')
      await Promise.resolve()
      await Promise.resolve()

      expect(audioManagerMock.resumePlayback).not.toHaveBeenCalled()
    })

    it('a PTT press landing DURING the fresh-arm await is NOT clobbered by the resting-mute (bd qt7w)', async () => {
      const manager = await connected()
      // Fresh-arm branch: mic not yet recording at the reconnect ready-callback.
      audioManagerMock.isRecording.mockReturnValue(false)
      audioManagerMock.muteInput.mockClear()
      audioManagerMock.unmuteInput.mockClear()

      // Hold startRecording open so a "press" can land while rehydrateAudio is
      // mid-await (the real getUserMedia + addModule span). This is the race window.
      let releaseArm!: () => void
      audioManagerMock.startRecording.mockImplementationOnce(
        () => new Promise<void>((resolve) => { releaseArm = () => resolve() })
      )

      capturedCallbacks.onSessionReady('sess-race')
      await Promise.resolve() // let rehydrateAudio reach the await

      // USER PRESSES PTT mid-arm: the overlay records the hold + unmutes.
      manager.setPushToTalkHeld(true)

      // Arm completes -> rehydrateAudio applies its post-await mute decision.
      releaseArm()
      await Promise.resolve()
      await Promise.resolve()

      // The press wins: because the hold is read AFTER the await, the fresh mic is
      // left UNMUTED, not re-muted -- the user's in-progress utterance is preserved.
      expect(audioManagerMock.startRecording).toHaveBeenCalledTimes(1)
      expect(audioManagerMock.unmuteInput).toHaveBeenCalled()
      expect(audioManagerMock.muteInput).not.toHaveBeenCalled()
    })

    it('a released hold (setPushToTalkHeld(false)) makes the next fresh-arm mute -- no stale-true (bd qt7w)', async () => {
      const manager = await connected()
      audioManagerMock.isRecording.mockReturnValue(false)
      // Simulate a full press-then-release cycle: the overlay set held=true on press
      // and clears it SYNCHRONOUSLY at release (not in a cancellable timeout), so by
      // the time any later reconnect fresh-arms, the flag must read false.
      manager.setPushToTalkHeld(true)
      manager.setPushToTalkHeld(false)
      audioManagerMock.muteInput.mockClear()
      audioManagerMock.unmuteInput.mockClear()

      capturedCallbacks.onSessionReady('sess-released')
      await Promise.resolve()
      await Promise.resolve()

      // Released -> resting mute applies (the mic is NOT wrongly left unmuted).
      expect(audioManagerMock.muteInput).toHaveBeenCalled()
      expect(audioManagerMock.unmuteInput).not.toHaveBeenCalled()
    })

    it('fresh-arm with NO concurrent press still applies the PTT resting mute (bd qt7w -- no regression)', async () => {
      const manager = await connected()
      audioManagerMock.isRecording.mockReturnValue(false)
      audioManagerMock.muteInput.mockClear()
      audioManagerMock.unmuteInput.mockClear()
      // No hold in progress (the normal reconnect-while-idle case).
      manager.setPushToTalkHeld(false)

      capturedCallbacks.onSessionReady('sess-noPress')
      await Promise.resolve()
      await Promise.resolve()

      // No press -> PTT mode applies its resting mute on the fresh mic.
      expect(audioManagerMock.muteInput).toHaveBeenCalled()
      expect(audioManagerMock.unmuteInput).not.toHaveBeenCalled()
    })
  })

  // ---------------------------------------------------------------------------
  // (c) Audio-queue barge-in (flush on speech start, resume on speech end)
  //
  // In manual/Silero VAD with PTT OFF, a VAD speech-start while Gemini is
  // speaking must flush the playback queue immediately (instant barge-in); the
  // matching speech-end resumes playback once Gemini has stopped.
  // ---------------------------------------------------------------------------
  describe('audio-queue barge-in (manual VAD, PTT off)', () => {
    async function connectedAutoMode() {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      await manager.connect()
      // PTT defaults ON (hallucination reduction); disable it so the
      // energy/Silero barge-in path is live.
      manager.setPushToTalkMode(false)
      return manager
    }

    it('flushes the audio queue on VAD speech-start while Gemini is speaking', async () => {
      const manager = await connectedAutoMode()
      // The FLUSH site reads isModelSpeaking (bd polyglot-pdf-uxc6s): a clip
      // overlapping the model's PCM makes isSpeaking false while the model is
      // still mid-utterance, which used to skip this flush entirely.
      audioManagerMock.isModelSpeaking.mockReturnValue(true)

      manager.onVADSpeechStart()
      expect(audioManagerMock.flushAudioQueue).toHaveBeenCalled()
    })

    it('does NOT flush on speech-start when Gemini is silent', async () => {
      const manager = await connectedAutoMode()
      audioManagerMock.isModelSpeaking.mockReturnValue(false)

      manager.onVADSpeechStart()
      expect(audioManagerMock.flushAudioQueue).not.toHaveBeenCalled()
    })

    it('resumes playback on VAD speech-end once Gemini has stopped', async () => {
      const manager = await connectedAutoMode()
      // DELIBERATELY isSpeaking: onVADSpeechEnd is the RESUME half of the
      // deadlock pair and must stay the exact complement of the suspend sites
      // (bd s1iex.4 / polyglot-pdf-uxc6s). Do not "fix" this to isModelSpeaking.
      audioManagerMock.isSpeaking.mockReturnValue(false)

      manager.onVADSpeechEnd()
      expect(audioManagerMock.resumePlayback).toHaveBeenCalled()
      expect(audioManagerMock.resumeAudioContext).toHaveBeenCalled()
    })

    it('suppresses barge-in entirely while PTT is ON (the default)', async () => {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      await manager.connect()
      // PTT left at its default (ON): the VAD barge-in path is gated off.
      // Set BOTH signals true so this passes because the PTT gate held, never
      // because a signal happened to read false (bd polyglot-pdf-uxc6s).
      audioManagerMock.isSpeaking.mockReturnValue(true)
      audioManagerMock.isModelSpeaking.mockReturnValue(true)

      manager.onVADSpeechStart()
      expect(audioManagerMock.flushAudioQueue).not.toHaveBeenCalled()
    })
  })

  // ---------------------------------------------------------------------------
  // (d) Debounced post-unpause re-prompt (bd polyglot-pdf-yo5t)
  //
  // pause() discards Gemini's in-flight question CLIENT-side only, so after a
  // warm resume both sides sit waiting. resume() therefore arms a debounce
  // timer that asks the backend (recovery_prompt level 1) to have Gemini
  // re-ask the current field -- unless the user re-paused, the AI is already
  // talking, or the user started answering themselves. The reconnect-routed
  // resume path must NOT arm it (the backend RESUME initiating message
  // already re-prompts there).
  // ---------------------------------------------------------------------------
  describe('debounced post-unpause re-prompt (bd yo5t)', () => {
    async function pausedManager() {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      await manager.connect()
      manager.pause()
      // Default mock has Gemini speaking; the re-prompt only fires into
      // silence, so these tests start from a quiet session. The guard reads
      // isModelSpeaking (bd polyglot-pdf-uxc6s).
      audioManagerMock.isModelSpeaking.mockReturnValue(false)
      return manager
    }

    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('fires exactly ONE level-1 recovery prompt ~1.5s after a settled warm resume', async () => {
      const manager = await pausedManager()

      await manager.resume()
      // Not yet -- the debounce window is still open.
      vi.advanceTimersByTime(1400)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()

      vi.advanceTimersByTime(200)
      expect(webFormConnectionMock.sendRecoveryPrompt).toHaveBeenCalledTimes(1)
      expect(webFormConnectionMock.sendRecoveryPrompt).toHaveBeenCalledWith(1)

      // The window closed; nothing further fires.
      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).toHaveBeenCalledTimes(1)
    })

    it('pause/unpause flutter reschedules ONE re-prompt instead of stacking them', async () => {
      const manager = await pausedManager()

      // Three rapid pause/resume cycles inside the window.
      await manager.resume()
      vi.advanceTimersByTime(500)
      manager.pause()
      await manager.resume()
      vi.advanceTimersByTime(500)
      manager.pause()
      await manager.resume()

      // Only the LAST resume's timer survives: nothing at +1.4s...
      vi.advanceTimersByTime(1400)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
      // ...one prompt once it settles.
      vi.advanceTimersByTime(200)
      expect(webFormConnectionMock.sendRecoveryPrompt).toHaveBeenCalledTimes(1)
    })

    it('a re-pause inside the window cancels the pending re-prompt', async () => {
      const manager = await pausedManager()

      await manager.resume()
      manager.pause()

      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })

    it('does NOT arm on the reconnect-routed resume path (dead socket)', async () => {
      const manager = await pausedManager()
      webFormConnectionMock.isSocketOpen.mockReturnValue(false)
      webFormConnectionMock.getStatus.mockReturnValue('idle_timeout')

      await manager.resume()

      vi.advanceTimersByTime(5000)
      // The reconnect path re-prompts via the backend RESUME initiating
      // message; a client re-prompt on top would double-speak.
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })

    it('stays silent when the AI is already talking at fire time', async () => {
      const manager = await pausedManager()

      await manager.resume()
      // Gemini's audio came back on its own (e.g. a turn still streaming).
      audioManagerMock.isModelSpeaking.mockReturnValue(true)

      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })

    it('a PTT press inside the window cancels the re-prompt (user is answering)', async () => {
      const manager = await pausedManager()

      await manager.resume()
      manager.setPushToTalkHeld(true)

      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })

    it('a VAD speech-start inside the window cancels the re-prompt (user is answering)', async () => {
      const manager = await pausedManager()

      await manager.resume()
      manager.onVADSpeechStart()

      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })

    it('sendActivityStart (the overlays REAL speech-start wiring) cancels the re-prompt', async () => {
      // The production overlays call connectionManager.sendActivityStart()
      // directly from their VAD speech-start handlers and never route through
      // onVADSpeechStart (fresh-eyes gap) -- the cancel must live on the path
      // the real UI actually drives.
      const manager = await pausedManager()

      await manager.resume()
      manager.sendActivityStart()

      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })

    it('sendActivityStart cancels the pending re-prompt', async () => {
      // The user speaking supersedes a queued post-resume re-prompt (bd
      // polyglot-pdf-yo5t). This used to also assert the signal itself was
      // SUPPRESSED under native VAD; that mode is gone (bd polyglot-pdf-v1m8g),
      // so the signal is now always forwarded -- and the cancel still happens.
      const manager = await pausedManager()

      await manager.resume()
      manager.sendActivityStart()
      expect(webFormConnectionMock.sendActivityStart).toHaveBeenCalled()

      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })

    it('disconnect inside the window cancels the re-prompt', async () => {
      const manager = await pausedManager()

      await manager.resume()
      manager.disconnect()

      vi.advanceTimersByTime(5000)
      expect(webFormConnectionMock.sendRecoveryPrompt).not.toHaveBeenCalled()
    })
  })

  // ---------------------------------------------------------------------------
  // Reconnect / status surface
  //
  // Status is delegated to the live WebFormConnection; before any connect it
  // reports 'disconnected'. (Backoff/token-refetch reconnect lives inside
  // WebFormConnection -- specced in its own suite; here we pin the manager's
  // delegation contract.)
  // ---------------------------------------------------------------------------
  describe('status delegation', () => {
    it('reports disconnected before connect, and delegates to the live connection after', async () => {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      expect(manager.getStatus()).toBe('disconnected')

      await manager.connect()
      expect(manager.getStatus()).toBe('connected')
      expect(webFormConnectionMock.getStatus).toHaveBeenCalled()
    })
  })

  /**
   * Manual/voice mode notification (bd polyglot-pdf-wurj8).
   *
   * The mode changes WITHOUT any UI click -- a PTT press auto-leaves manual mode --
   * so a UI that only tracks its own clicks renders a stale label: "quiet" while
   * the assistant is live and about to speak. These drive the REAL manager (the
   * overlay suite uses a mock, which can only pin the subscriber half).
   */
  describe('voice mode change notification', () => {
    it('notifies subscribers when the mode is set', () => {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      const seen: string[] = []
      manager.onVoiceModeChange((m) => seen.push(m))

      manager.setVoiceMode('manual')

      expect(seen).toEqual(['manual'])
    })

    it('notifies on the PTT auto-unmute, which no click produced', () => {
      // The case a UI cannot observe on its own, and the reason this subscription
      // exists at all.
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      manager.setVoiceMode('manual')
      const seen: string[] = []
      manager.onVoiceModeChange((m) => seen.push(m))

      manager.sendActivityStart()

      expect(seen).toEqual(['voice'])
      expect(manager.getVoiceMode()).toBe('voice')
    })

    it('does not notify when the mode does not actually change', () => {
      // setVoiceMode is idempotent-guarded; a redundant call must not churn the UI.
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      manager.setVoiceMode('manual')
      const seen: string[] = []
      manager.onVoiceModeChange((m) => seen.push(m))

      manager.setVoiceMode('manual')

      expect(seen).toEqual([])
    })

    it('unsubscribes cleanly, and one listener cannot drop another', () => {
      // A remounted overlay unsubscribes; a sibling's listener must survive it.
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      const a: string[] = []
      const b: string[] = []
      const offA = manager.onVoiceModeChange((m) => a.push(m))
      manager.onVoiceModeChange((m) => b.push(m))

      offA()
      manager.setVoiceMode('manual')

      expect(a).toEqual([])
      expect(b).toEqual(['manual'])
    })

    it('a throwing listener does not abort the mode change or starve the others', () => {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      const seen: string[] = []
      manager.onVoiceModeChange(() => { throw new Error('listener blew up') })
      manager.onVoiceModeChange((m) => seen.push(m))

      manager.setVoiceMode('manual')

      expect(manager.getVoiceMode()).toBe('manual')
      expect(seen).toEqual(['manual'])
    })
  })
})
