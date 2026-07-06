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
 * three behaviors the bead names: (a) the section-based state contract,
 * (b) activity-signal suppression in native-VAD mode, and (c) audio-queue
 * barge-in flush/resume.
 *
 * WebFormConnection is mocked, so the backend-driven onNativeVadMode handshake
 * is simulated by capturing the callbacks object the factory passes into the
 * WebFormConnection constructor and invoking it directly.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createConnectionManager } from './connection'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'

// Capture the most recent ConnectionCallbacks the factory hands to
// WebFormConnection, plus the AudioManager mock, so a test can drive the
// backend-originated callbacks (onNativeVadMode, etc.) and assert on the
// audio layer the factory wires up.
let capturedCallbacks: any = null
let audioManagerMock: any = null
let webFormConnectionMock: any = null

vi.mock('./fieldManager', () => ({
  createFieldManager: vi.fn(() => ({
    cleanup: vi.fn()
  }))
}))

vi.mock('./audioManager', () => ({
  createAudioManager: vi.fn(() => {
    audioManagerMock = {
      cleanup: vi.fn(),
      startRecording: vi.fn(),
      stopRecording: vi.fn(),
      isRecording: vi.fn(() => false),
      // Default: Gemini IS speaking, so a barge-in flush is expected.
      isSpeaking: vi.fn(() => true),
      flushAudioQueue: vi.fn(),
      resumePlayback: vi.fn(),
      resumeAudioContext: vi.fn(),
      setNativeVad: vi.fn(),
      // Used by the reconnect audio re-arm path (bd polyglot-pdf-z9bc).
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
    // backend handshake events (onNativeVadMode) by hand.
    capturedCallbacks = callbacks
    this.connect = vi.fn(() => Promise.resolve())
    this.disconnect = vi.fn()
    this.getStatus = vi.fn(() => 'connected')
    this.isSocketOpen = vi.fn(() => true)
    this.sendAudio = vi.fn()
    this.sendActivityStart = vi.fn()
    this.sendActivityEnd = vi.fn(() => Promise.resolve())
    this.sendPrompt = vi.fn()
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
  // (b) Activity-signal suppression in native-VAD mode (bd polyglot-pdf-333/zivv)
  //
  // When the backend reports native VAD, Gemini owns turn detection: the client
  // must suppress ALL manual turn signals -- activity_start AND activity_end (and
  // the Silero barge-in callbacks). Native automatic VAD and the manual signals
  // are mutually exclusive; forwarding activity_end (mapped to audio_stream_end on
  // the backend) into the continuous native stream interrupts Gemini's response
  // ("Gemini stops responding after PTT press" -- bd zivv). PTT under native VAD
  // is ONLY an audio gate: audioManager streams SILENCE while the button is
  // released so native VAD finds the boundary itself -- no manual end needed. This
  // supersedes the earlier bd-6vo audio_stream_end behavior.
  // ---------------------------------------------------------------------------
  describe('native-VAD activity-signal suppression', () => {
    async function connected() {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      await manager.connect()
      // The factory created WebFormConnection and we captured its callbacks.
      expect(capturedCallbacks).not.toBeNull()
      return manager
    }

    it('forwards activity_start when NOT in native-VAD mode', async () => {
      const manager = await connected()
      manager.sendActivityStart()
      expect(webFormConnectionMock.sendActivityStart).toHaveBeenCalledTimes(1)
    })

    it('suppresses activity_start once the backend reports native VAD', async () => {
      const manager = await connected()
      capturedCallbacks.onNativeVadMode(true)

      manager.sendActivityStart()
      expect(webFormConnectionMock.sendActivityStart).not.toHaveBeenCalled()
      // Native mode reconfigures the audio layer to stream continuous audio.
      expect(audioManagerMock.setNativeVad).toHaveBeenCalledWith(true)
    })

    it('suppresses activity_end in native-VAD mode (bd zivv -- no manual turn signal)', async () => {
      const manager = await connected()
      capturedCallbacks.onNativeVadMode(true)

      await manager.sendActivityEnd()
      // activity_end IS suppressed under native VAD: forwarding it (backend maps to
      // audio_stream_end) into the continuous stream interrupts Gemini's response.
      // The turn closes from the trailing SILENCE the audio layer streams while PTT
      // is released, not from a manual end signal.
      expect(webFormConnectionMock.sendActivityEnd).not.toHaveBeenCalled()
    })

    it('still forwards activity_end in MANUAL-VAD mode (real activity_end)', async () => {
      const manager = await connected()
      // No native-VAD report -> manual mode; activity_end must still flow.
      await manager.sendActivityEnd()
      expect(webFormConnectionMock.sendActivityEnd).toHaveBeenCalledTimes(1)
    })

    it('suppresses the Silero barge-in callbacks in native-VAD mode', async () => {
      const manager = await connected()
      capturedCallbacks.onNativeVadMode(true)

      manager.onVADSpeechStart()
      manager.onVADSpeechEnd()
      // No client-side flush/resume: Gemini owns interruption in native mode.
      expect(audioManagerMock.flushAudioQueue).not.toHaveBeenCalled()
      expect(audioManagerMock.resumePlayback).not.toHaveBeenCalled()
      // And the Silero end-path must NOT forward activity_end in native mode --
      // only the PTT wrapper (manager.sendActivityEnd) does, per criterion 2(b).
      // Without the nativeVad gate on onVADSpeechEnd this would spuriously fire.
      expect(webFormConnectionMock.sendActivityEnd).not.toHaveBeenCalled()
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
      audioManagerMock.isSpeaking.mockReturnValue(true)

      manager.onVADSpeechStart()
      expect(audioManagerMock.flushAudioQueue).toHaveBeenCalled()
    })

    it('does NOT flush on speech-start when Gemini is silent', async () => {
      const manager = await connectedAutoMode()
      audioManagerMock.isSpeaking.mockReturnValue(false)

      manager.onVADSpeechStart()
      expect(audioManagerMock.flushAudioQueue).not.toHaveBeenCalled()
    })

    it('resumes playback on VAD speech-end once Gemini has stopped', async () => {
      const manager = await connectedAutoMode()
      audioManagerMock.isSpeaking.mockReturnValue(false)

      manager.onVADSpeechEnd()
      expect(audioManagerMock.resumePlayback).toHaveBeenCalled()
      expect(audioManagerMock.resumeAudioContext).toHaveBeenCalled()
    })

    it('suppresses barge-in entirely while PTT is ON (the default)', async () => {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      await manager.connect()
      // PTT left at its default (ON): the VAD barge-in path is gated off.
      audioManagerMock.isSpeaking.mockReturnValue(true)

      manager.onVADSpeechStart()
      expect(audioManagerMock.flushAudioQueue).not.toHaveBeenCalled()
    })
  })

  // ---------------------------------------------------------------------------
  // Reconnect audio re-arm (bd polyglot-pdf-z9bc)
  //
  // The AUTOMATIC/internal reconnects -- GoAway pre-emptive resume (l3a.2) and
  // auto-reconnect on a dropped socket -- reach the manager only through the
  // backend-driven session-ready callbacks (onSessionReady / onSessionRestarted),
  // NOT through the overlay's connect+startRecording wrapper. Before this fix
  // those callbacks did not re-arm audio, so the AI's voice + the mic stayed dead
  // after such a reconnect. The callbacks must now re-arm audio, idempotently.
  // ---------------------------------------------------------------------------
  describe('reconnect audio re-arm', () => {
    async function connected() {
      const manager = createConnectionManager(testSchema, vi.fn(), 'English')
      await manager.connect()
      expect(capturedCallbacks).not.toBeNull()
      // The initial connect's overlay wrapper is not modeled here; simulate the
      // post-initial-connect state where audio is NOT yet armed.
      audioManagerMock.startRecording.mockClear()
      audioManagerMock.isRecording.mockReturnValue(false)
      return manager
    }

    it('re-arms audio on onSessionReady when not already recording (GoAway / auto-reconnect)', async () => {
      await connected()
      await capturedCallbacks.onSessionReady('sess-1')
      expect(audioManagerMock.startRecording).toHaveBeenCalledTimes(1)
    })

    it('re-arms audio on onSessionRestarted (warm restart path)', async () => {
      await connected()
      await capturedCallbacks.onSessionRestarted()
      expect(audioManagerMock.startRecording).toHaveBeenCalledTimes(1)
    })

    it('does NOT double-arm when audio is already recording (idempotent -- protects the manual / section-switch paths)', async () => {
      await connected()
      // A user-initiated or section-switch path armed audio just before the
      // session-ready event fires.
      audioManagerMock.isRecording.mockReturnValue(true)

      await capturedCallbacks.onSessionReady('sess-2')
      expect(audioManagerMock.startRecording).not.toHaveBeenCalled()
    })

    it('re-applies PTT/mute state after re-arming (mic gated per stored mode)', async () => {
      await connected()
      // PTT defaults ON, so the input must be muted after a re-arm.
      await capturedCallbacks.onSessionReady('sess-3')
      expect(audioManagerMock.setPTTMode).toHaveBeenCalledWith(true)
      expect(audioManagerMock.muteInput).toHaveBeenCalled()
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
})
