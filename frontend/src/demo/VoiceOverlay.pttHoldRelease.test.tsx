// @vitest-environment jsdom
//
// bd polyglot-pdf-qt7w: the PTT-hold flag on the shared ConnectionManager
// (setPushToTalkHeld) must be CLEARED SYNCHRONOUSLY on release -- NOT inside the
// 500ms post-release grace timeout. If it were deferred into that (cancellable)
// timeout, an unmount during the grace window (e.g. the desktop<->mobile resize
// flip, which cancels pending timeouts) would leave the flag stale-true, and a
// later fresh-arm reconnect would wrongly leave the mic UNMUTED when the user is
// not holding -- a privacy/cost exposure.
//
// This test drives a real press+release via the spacebar PTT path and asserts the
// clear happens WITHOUT advancing timers (i.e. synchronously at release), which is
// exactly the production of the flag-clear that the connection.test.ts consumer
// test cannot cover. A regression that moved the clear back into the timeout would
// fail here (the assertion runs before any timer fires).
import { render, cleanup, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { ConnectionManager } from '../shared/connection'
import { VoiceOverlay } from './VoiceOverlay'

// The VAD hook touches getUserMedia + WASM -- stub it for jsdom.
vi.mock('./useDemoVAD', () => ({
  useDemoVAD: () => ({
    userSpeaking: false,
    loading: false,
    errored: false as const,
    pause: vi.fn(),
    start: vi.fn(),
  }),
}))

vi.mock('../schema-forms/utils/pdfFiller', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../schema-forms/utils/pdfFiller')>()
  return { ...actual, getBackendHttpUrl: () => 'http://localhost:8000' }
})

const MINIMAL_SCHEMA: FormSchema = {
  source: 'pdf',
  form_metadata: {
    title: 'T', version: '1', language: 'en', form_number: 'X',
    edition_date: '01/01/25', page_count: 1,
  },
  parts: [{ id: 'part_1', label: 'P', description: '', order: 1, section_ids: ['section_1'], required: true }],
  sections: [{ id: 'section_1', label: 'S', order: 1, fields: ['field_1'] }],
  fields: [{ id: 'field_1', name: 'F', spoken_name: 'f', type: 'text', section_id: 'section_1' }],
} as any

function makeConnectedMock() {
  const heldSpy = vi.fn()
  const am = {
    muteInput: vi.fn(), unmuteInput: vi.fn(), flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(), resumeAudioContext: vi.fn(), isSpeaking: vi.fn(() => false),
    setPTTMode: vi.fn(), isRecording: vi.fn(() => true),
  }
  const manager = {
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    getStatus: vi.fn(() => 'connected'),
    isPaused: vi.fn(() => false),
    getAudioManager: vi.fn(() => am),
    rearmAudioCapture: vi.fn(async () => {}),
    sendActivityStart: vi.fn(),
    sendActivityEnd: vi.fn(async () => {}),
    setPushToTalkMode: vi.fn(),
    setPushToTalkHeld: heldSpy,
    getPushToTalkMode: vi.fn(() => true),
    isNativeVad: vi.fn(() => false),
    getFieldManager: vi.fn(() => null),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => true),
    onVADSpeechStart: vi.fn(),
    onVADSpeechEnd: vi.fn(),
  } as unknown as ConnectionManager & { setPushToTalkHeld: ReturnType<typeof vi.fn> }
  return { manager, heldSpy, am }
}

describe('VoiceOverlay PTT-hold flag is set/cleared synchronously (bd qt7w)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(SchemaFormStateManager, 'load').mockImplementation(() => ({
      schema: MINIMAL_SCHEMA, fieldValues: {}, currentSectionId: 'section_1',
      completedSections: new Set<string>(), validationErrors: {}, lastUpdated: 0,
      formSessionId: 'fss_test', loadedFieldIds: new Set<string>(), jitModeEnabled: false,
      disclaimerAccepted: true, selectedLanguage: 'English',
    } as any))
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})
  })
  afterEach(() => {
    cleanup()
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('spacebar press sets held=true, and release clears it synchronously (before the 500ms timer)', () => {
    const { manager, heldSpy } = makeConnectedMock()
    render(
      <VoiceOverlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status="connected"
        initialLanguage="English"
      />
    )
    heldSpy.mockClear()

    // PRESS (spacebar keydown on window -- the keyboard PTT path).
    fireEvent.keyDown(window, { code: 'Space' })
    expect(heldSpy).toHaveBeenCalledWith(true)

    heldSpy.mockClear()

    // RELEASE (spacebar keyup). The flag must be cleared NOW, synchronously --
    // WITHOUT advancing the 500ms grace timer. This is the invariant the fix
    // guarantees: the clear does not live inside the cancellable release timeout.
    fireEvent.keyUp(window, { code: 'Space' })
    expect(heldSpy).toHaveBeenCalledWith(false)
  })
})
