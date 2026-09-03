// @vitest-environment jsdom
//
// Manual/voice mode toggle (bd polyglot-pdf-wurj8) -- the control that REPLACED
// the Pause button, and the sticky half of the two-control voice UI (PTT is the
// other, and is non-sticky).
//
// What matters here is the difference from what it replaced. pause() SUSPENDED
// the session: it tore the mic down (so the user went mute, not merely deaf),
// discarded Gemini's in-flight question client-side, and made coming back cost a
// paid re-ask. Manual mode keeps the session live and the mic usable, and
// suppresses only the model's proactive speech. So these tests assert both
// halves: that the toggle drives the mode, AND that it does NOT touch the
// session or the microphone.
//
// Both overlays are covered because they are deliberate near-duplicates -- a fix
// applied to one and not the other is this repo's recurring shape.
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'
import { OVERLAY_TRANSLATIONS } from './overlayTranslations'

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

vi.mock('../shared/connection', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../shared/connection')>()
  return { ...actual, createConnectionManager: vi.fn() }
})

import { VoiceOverlay } from './VoiceOverlay'
import { VoiceOverlayMobile } from './VoiceOverlayMobile'

const MINIMAL_SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { title: 'Test Form', version: '1.0', language: 'en' },
  sections: [{ id: 'section_1', label: 'Section 1', order: 1, fields: [] }],
  fields: [],
} as unknown as FormSchema

const EN = OVERLAY_TRANSLATIONS['English']

function makeManager(initialMode: 'manual' | 'voice' = 'voice') {
  let mode = initialMode
  // Mirrors the real manager's listener set: the mode also changes WITHOUT a
  // click (a PTT press auto-unmutes), and the UI can only learn that by being
  // told. A mock that silently dropped the notification would hide the very bug
  // these tests exist to pin.
  const listeners = new Set<(m: 'manual' | 'voice') => void>()
  const audioManager = {
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    resetPlaybackClock: vi.fn(),
    setPTTMode: vi.fn(),
    setVADActive: vi.fn(),
    setEnergyCallback: vi.fn(),
    isSpeaking: vi.fn(() => false),
    muteInput: vi.fn(),
    unmuteInput: vi.fn(),
    pauseAudioContext: vi.fn(),
    resumeAudioContext: vi.fn(),
    getStream: vi.fn(() => null),
    isRecording: vi.fn(() => true),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    playAudio: vi.fn(async () => {}),
    destroy: vi.fn(),
  }
  return {
    getStatus: vi.fn(() => 'connected'),
    isSendingMicAudio: vi.fn(() => false),
    getAudioManager: vi.fn(() => audioManager),
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(async () => {}),
    isPaused: vi.fn(() => false),
    setVoiceMode: vi.fn((m: 'manual' | 'voice') => {
      mode = m
      for (const l of listeners) l(m)
    }),
    getVoiceMode: vi.fn(() => mode),
    onVoiceModeChange: vi.fn((l: (m: 'manual' | 'voice') => void) => {
      listeners.add(l)
      return () => { listeners.delete(l) }
    }),
    // The real manager auto-unmutes here (connection.ts sendActivityStart); the
    // mock does the same so a PTT press in a test exercises the real path.
    sendActivityStart: vi.fn(() => {
      if (mode !== 'voice') {
        mode = 'voice'
        for (const l of listeners) l('voice')
      }
    }),
    sendActivityEnd: vi.fn(async () => {}),
    switchToFirstSection: vi.fn(async () => {}),
    sendAudio: vi.fn(),
    sendPrompt: vi.fn(),
    sendRecoveryPrompt: vi.fn(),
    endGeminiSession: vi.fn(),
    setPushToTalkMode: vi.fn(),
    setPushToTalkHeld: vi.fn(),
    getPushToTalkMode: vi.fn(() => true),
    getFieldManager: vi.fn(() => null),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => true),
    changeFillLanguage: vi.fn(async () => {}),
    readDisclaimer: vi.fn(),
    startSection: vi.fn(async () => {}),
    switchToSection: vi.fn(async () => {}),
    completeSection: vi.fn(async () => {}),
    getCurrentSectionId: vi.fn(() => 'section_1'),
    getCompletedSectionIds: vi.fn(() => new Set<string>()),
    onVADSpeechStart: vi.fn(),
    onVADSpeechEnd: vi.fn(),
    rearmAudioCapture: vi.fn(async () => {}),
    _audioManager: audioManager,
  } as any
}

async function renderDesktop(manager: any) {
  render(
    <VoiceOverlay
      schema={MINIMAL_SCHEMA}
      connectionManager={manager}
      status="connected"
      initialLanguage="English"
    />
  )
  return await screen.findByRole('button', { name: new RegExp(EN.switchToManual) })
}

async function renderMobile(manager: any) {
  const { container } = render(
    <VoiceOverlayMobile
      schema={MINIMAL_SCHEMA}
      connectionManager={manager}
      status="connected"
      initialLanguage="English"
    />
  )
  const fab = container.querySelector('.vff-fab') as HTMLElement
  fireEvent.click(fab)
  return await screen.findByRole('button', { name: new RegExp(EN.switchToManual) })
}

// Renders the MANUAL-mode variant of the toggle, for the seed-from-manager case.
async function renderDesktopManual(manager: any) {
  render(
    <VoiceOverlay
      schema={MINIMAL_SCHEMA}
      connectionManager={manager}
      status="connected"
      initialLanguage="English"
    />
  )
  return await screen.findByRole('button', { name: new RegExp(EN.switchToVoice) })
}

async function renderMobileManual(manager: any) {
  const { container } = render(
    <VoiceOverlayMobile
      schema={MINIMAL_SCHEMA}
      connectionManager={manager}
      status="connected"
      initialLanguage="English"
    />
  )
  const fab = container.querySelector('.vff-fab') as HTMLElement
  fireEvent.click(fab)
  return await screen.findByRole('button', { name: new RegExp(EN.switchToVoice) })
}

const OVERLAYS: Array<[string, (m: any) => Promise<HTMLElement>, (m: any) => Promise<HTMLElement>]> = [
  ['desktop', renderDesktop, renderDesktopManual],
  ['mobile', renderMobile, renderMobileManual],
]

beforeEach(() => {
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

describe.each(OVERLAYS)('manual/voice mode toggle (%s overlay)', (_name, renderOverlay, renderOverlayManual) => {
  it('a connected session offers the toggle, showing what a click switches TO', async () => {
    const manager = makeManager('voice')
    const btn = await renderOverlay(manager)
    expect(btn).toBeTruthy()
    expect(btn.getAttribute('aria-pressed')).toBe('false')
  })

  it('clicking it puts the session into manual mode', async () => {
    const manager = makeManager('voice')
    const btn = await renderOverlay(manager)

    fireEvent.click(btn)

    expect(manager.setVoiceMode).toHaveBeenCalledWith('manual')
  })

  it('the label and pressed state flip, so a silent assistant never looks broken', async () => {
    const manager = makeManager('voice')
    const btn = await renderOverlay(manager)

    fireEvent.click(btn)

    const back = await screen.findByRole('button', { name: new RegExp(EN.switchToVoice) })
    expect(back.getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByRole('button', { name: new RegExp(EN.switchToManual) })).toBeNull()
  })

  it('clicking again returns to voice mode', async () => {
    const manager = makeManager('voice')
    const btn = await renderOverlay(manager)
    fireEvent.click(btn)

    fireEvent.click(await screen.findByRole('button', { name: new RegExp(EN.switchToVoice) }))

    expect(manager.setVoiceMode).toHaveBeenLastCalledWith('voice')
    expect(await screen.findByRole('button', { name: new RegExp(EN.switchToManual) })).toBeTruthy()
  })

  it('entering manual mode does NOT suspend the session or tear down the mic', async () => {
    // The whole point of replacing pause(): the assistant goes quiet, it does
    // not go away. A regression here is the one that makes the user MUTE as
    // well as deaf, which is what pause() did and why it had to go.
    //
    // muteInput is measured as a DELTA, not an absolute: PTT holds the mic at a
    // resting mute between presses, so it is already called once at mount. The
    // claim under test is that the TOGGLE adds none of its own -- an absolute
    // assertion here would be measuring PTT, not this control.
    const manager = makeManager('voice')
    const btn = await renderOverlay(manager)
    const am = manager._audioManager
    const muteBefore = am.muteInput.mock.calls.length
    const stopBefore = am.stopRecording.mock.calls.length

    fireEvent.click(btn)

    expect(manager.pause).not.toHaveBeenCalled()
    expect(manager.disconnect).not.toHaveBeenCalled()
    expect(manager.endGeminiSession).not.toHaveBeenCalled()
    expect(manager.stopRecording).not.toHaveBeenCalled()
    expect(am.stopRecording.mock.calls.length).toBe(stopBefore)
    expect(am.muteInput.mock.calls.length).toBe(muteBefore)
  })

  it('a PTT press updates the LABEL, not just the session', async () => {
    // The mode changes without a click, so the button has to be told. If it is
    // not, it keeps saying "quiet" while the assistant is live and about to
    // speak -- which is worse than having no indicator at all, because the user
    // is actively told the opposite of the truth.
    const manager = makeManager('voice')
    const btn = await renderOverlay(manager)
    fireEvent.click(btn)
    await screen.findByRole('button', { name: new RegExp(EN.switchToVoice) })

    // The user presses to talk instead of finding the toggle.
    act(() => {
      manager.sendActivityStart()
    })

    expect(manager.getVoiceMode()).toBe('voice')
    const back = await screen.findByRole('button', { name: new RegExp(EN.switchToManual) })
    expect(back.getAttribute('aria-pressed')).toBe('false')
    expect(screen.queryByRole('button', { name: new RegExp(EN.switchToVoice) })).toBeNull()
  })

  it('a remount onto a live session restores manual mode rather than resetting it', async () => {
    // A desktop<->mobile breakpoint flip remounts the overlay onto a session
    // that is still running. Seeding from the manager is what stops the
    // assistant from silently starting to talk again.
    const manager = makeManager('manual')
    const btn = await renderOverlayManual(manager)

    expect(btn.getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByRole('button', { name: new RegExp(EN.switchToManual) })).toBeNull()
  })
})
