// @vitest-environment jsdom
//
// Regression test for the resize-flip mic re-arm bug (bd polyglot-pdf-nlfc).
//
// When the browser is resized across the 768px breakpoint mid-session,
// SchemaForm.tsx swaps VoiceOverlay <-> VoiceOverlayMobile. The new overlay
// mounts onto the shared, still-live ConnectionManager. The old overlay's unmount
// tears down audio capture (stopRecording), so the new overlay's alreadyLive
// early-return MUST call connectionManager.rearmAudioCapture() to restart the mic.
// The WebSocket/Gemini session must NOT be reconnected.
//
// Two scenarios exercised for each overlay:
//   A. alreadyLive remount (disclaimer accepted): rearmAudioCapture fires, connect does not.
//   B. fresh mount (status disconnected): rearmAudioCapture does NOT fire.
//
// bd polyglot-pdf-d0k: both overlays now require a connectionManager prop --
// there is no standalone (tokenless) creation path -- so scenario B mounts with
// a disconnected mock manager instead of omitting the prop.
import { render, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { ConnectionManager } from '../shared/connection'

// --- mock the VAD hook: the real one calls navigator.mediaDevices.getUserMedia
//     and loads WASM, neither of which works in jsdom.
vi.mock('./useDemoVAD', () => ({
  useDemoVAD: () => ({
    userSpeaking: false,
    loading: false,
    errored: false as const,
    pause: vi.fn(),
    start: vi.fn(),
  }),
}))

// --- mock the backend-URL helper (reads import.meta.env / window.location).
vi.mock('../schema-forms/utils/pdfFiller', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../schema-forms/utils/pdfFiller')>()
  return { ...actual, getBackendHttpUrl: () => 'http://localhost:8000' }
})

import { VoiceOverlay } from './VoiceOverlay'
import { VoiceOverlayMobile } from './VoiceOverlayMobile'

const MINIMAL_SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { title: 'Test Form', version: '1.0', language: 'en' },
  sections: [{ id: 'section_1', label: 'Section 1', order: 1, fields: [] }],
  fields: [],
} as unknown as FormSchema

/**
 * Build a minimal mock ConnectionManager for the resize-flip tests.
 * rearmAudioCapture is tracked; connect must NOT be called on an alreadyLive remount.
 */
function makeResizeFlipMock(): ConnectionManager & {
  __rearmSpy: ReturnType<typeof vi.fn>
  __setEnergyCbSpy: ReturnType<typeof vi.fn>
} {
  const rearmSpy = vi.fn(async () => {})
  const setEnergyCbSpy = vi.fn()
  const audioManager = {
    setPTTMode: vi.fn(),
    setVADActive: vi.fn(),
    setNativeVad: vi.fn(),
    setEnergyCallback: setEnergyCbSpy,
    isSpeaking: vi.fn(() => false),
    muteInput: vi.fn(),
    unmuteInput: vi.fn(),
    pauseAudioContext: vi.fn(),
    resumeAudioContext: vi.fn(),
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    getStream: vi.fn(() => null),
    isRecording: vi.fn(() => false),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    playAudio: vi.fn(async () => {}),
    destroy: vi.fn(),
  }
  const manager = {
    __rearmSpy: rearmSpy,
    __setEnergyCbSpy: setEnergyCbSpy,
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(async () => {}),
    getStatus: vi.fn(() => 'connected' as const),
    getThinking: vi.fn(() => false),  // bd polyglot-pdf-wpw.5
    isSendingMicAudio: vi.fn(() => true),
    sendAudio: vi.fn(),
    sendActivityStart: vi.fn(),
    sendActivityEnd: vi.fn(async () => {}),
    sendPrompt: vi.fn(),
    sendRecoveryPrompt: vi.fn(),
    endGeminiSession: vi.fn(),
    setPushToTalkMode: vi.fn(),
    setPushToTalkHeld: vi.fn(),
    getPushToTalkMode: vi.fn(() => true),
    isNativeVad: vi.fn(() => false),
    getFieldManager: vi.fn(() => null),
    getAudioManager: vi.fn(() => audioManager),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => false),
    isPaused: vi.fn(() => false),
    rearmAudioCapture: rearmSpy,
    changeFillLanguage: vi.fn(async () => {}),
    changeSpokenLanguage: vi.fn(),
    readDisclaimer: vi.fn(),
    switchToFirstSection: vi.fn(async () => {}),
    startSection: vi.fn(async () => {}),
    switchToSection: vi.fn(async () => {}),
    completeSection: vi.fn(async () => {}),
    getCurrentSectionId: vi.fn(() => 'section_1'),
    getCompletedSectionIds: vi.fn(() => new Set<string>()),
    onVADSpeechStart: vi.fn(),
    onVADSpeechEnd: vi.fn(),
  }
  return manager as unknown as ConnectionManager & {
    __rearmSpy: ReturnType<typeof vi.fn>
    __setEnergyCbSpy: ReturnType<typeof vi.fn>
  }
}

describe('VoiceOverlay resize-flip mic re-arm (bd polyglot-pdf-nlfc)', () => {
  beforeEach(() => {
    // Stub sessionStorage so SchemaFormStateManager does not throw in jsdom.
    const store: Record<string, string> = {}
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  /**
   * Scenario A: overlay remounted onto an alreadyLive session (disclaimer accepted).
   * Asserts rearmAudioCapture fires; connect must NOT be called.
   */
  async function assertRearmOnAlreadyLive(
    Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile
  ) {
    const manager = makeResizeFlipMock()

    // Pre-seed a disclaimer-accepted state so the alreadyLive branch skips the
    // modal and calls rearmAudioCapture() directly (no disclaimer detour).
    vi.spyOn(SchemaFormStateManager, 'load').mockImplementation(() => ({
      schema: MINIMAL_SCHEMA,
      fieldValues: {},
      currentSectionId: 'section_1',
      completedSections: new Set<string>(),
      validationErrors: {},
      lastUpdated: 0,
      formSessionId: 'fss_test',
      loadedFieldIds: new Set<string>(),
      jitModeEnabled: false,
      disclaimerAccepted: true,
      selectedLanguage: 'English',
    } as any))
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})

    render(
      <Overlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status="connected"
        initialLanguage="English"
      />
    )

    // Wait for the mount useEffect to run (it calls rearmAudioCapture via the
    // alreadyLive branch). The call is async but the effect fires synchronously
    // on mount in jsdom; waitFor gives it a tick to settle.
    await waitFor(() => {
      expect(manager.__rearmSpy).toHaveBeenCalledTimes(1)
    })

    // The WebSocket/Gemini session must NOT be reconnected on an alreadyLive remount.
    expect(manager.connect).not.toHaveBeenCalled()
  }

  /**
   * Scenario B: fresh mount on a disconnected manager (bd polyglot-pdf-d0k: the
   * standalone/tokenless creation path is gone -- connectionManager is now a
   * required prop -- so a "fresh mount" means a disconnected manager was passed
   * in, not that no manager exists). The alreadyLive branch is not taken, so
   * rearmAudioCapture must NOT be called.
   */
  async function assertNoRearmOnFreshMount(
    Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile
  ) {
    const manager = makeResizeFlipMock()
    // A fresh mount starts disconnected (no live session to re-arm).
    ;(manager as any).getStatus = vi.fn(() => 'disconnected')

    render(
      <Overlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        initialLanguage="English"
      />
    )

    // Give effects a tick to settle.
    await new Promise(resolve => setTimeout(resolve, 50))

    // The alreadyLive re-arm path is only reached when status is 'connected' (or
    // one of the other "live" states). On a fresh/disconnected mount it must NOT
    // fire -- pin that explicitly so a guard regression that re-arms
    // unconditionally fails.
    expect(manager.__rearmSpy).not.toHaveBeenCalled()
  }

  it('desktop (VoiceOverlay): calls rearmAudioCapture on alreadyLive remount', async () => {
    await assertRearmOnAlreadyLive(VoiceOverlay)
  })

  it('mobile (VoiceOverlayMobile): calls rearmAudioCapture on alreadyLive remount', async () => {
    await assertRearmOnAlreadyLive(VoiceOverlayMobile)
  })

  it('desktop (VoiceOverlay): does NOT call rearmAudioCapture on fresh/disconnected mount', async () => {
    await assertNoRearmOnFreshMount(VoiceOverlay)
  })

  it('mobile (VoiceOverlayMobile): does NOT call rearmAudioCapture on fresh/disconnected mount', async () => {
    await assertNoRearmOnFreshMount(VoiceOverlayMobile)
  })

  /**
   * Mic-energy meter subscription (bd polyglot-pdf-s3zv). On a connected mount the
   * overlay must subscribe to the audio manager's energy stream via
   * setEnergyCallback, and unsubscribe (callback set to null) on unmount. This pins
   * the OVERLAY side of the wiring -- audioEnergyCallback.test.ts covers the manager
   * side, but nothing asserted the overlay actually calls setEnergyCallback until a
   * fresh-eyes note (a stub without the method silently skipped the path).
   */
  async function assertEnergySubscribed(
    Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile
  ) {
    const manager = makeResizeFlipMock()
    vi.spyOn(SchemaFormStateManager, 'load').mockImplementation(() => ({
      schema: MINIMAL_SCHEMA, fieldValues: {}, currentSectionId: 'section_1',
      completedSections: new Set<string>(), validationErrors: {}, lastUpdated: 0,
      formSessionId: 'fss_test', loadedFieldIds: new Set<string>(),
      jitModeEnabled: false, disclaimerAccepted: true, selectedLanguage: 'English',
    } as any))
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})

    const { unmount } = render(
      <Overlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status="connected"
        initialLanguage="English"
      />
    )

    // Subscribed on mount with a function callback. (Index from the end with
    // [length-1] rather than Array.prototype.at -- the tsconfig lib targets ES2020,
    // where `.at` is not typed; Codex PR #203, P0.)
    await waitFor(() => {
      expect(manager.__setEnergyCbSpy).toHaveBeenCalled()
    })
    const subCalls = manager.__setEnergyCbSpy.mock.calls
    const lastSubArg = subCalls[subCalls.length - 1]?.[0]
    expect(typeof lastSubArg).toBe('function')

    // Unsubscribed (null) on unmount, so a torn-down overlay leaks no callback.
    unmount()
    await waitFor(() => {
      const calls = manager.__setEnergyCbSpy.mock.calls
      const lastArg = calls[calls.length - 1]?.[0]
      expect(lastArg).toBeNull()
    })
  }

  it('desktop (VoiceOverlay): subscribes to + unsubscribes from the energy stream', async () => {
    await assertEnergySubscribed(VoiceOverlay)
  })

  it('mobile (VoiceOverlayMobile): subscribes to + unsubscribes from the energy stream', async () => {
    await assertEnergySubscribed(VoiceOverlayMobile)
  })
})
