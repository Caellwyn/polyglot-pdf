// @vitest-environment jsdom
//
// bd polyglot-pdf-ibxz: the voice-overlay control panel (Hold to Talk, Pause /
// Resume / Reconnect, Clear Form, input-mode row, field counter, clear-form
// confirm) rendered hardcoded English in every session language (tester bug 3,
// Spanish session 2026-07-15). The panel copy now comes from
// overlayTranslations.ts, keyed on the overlay's selectedLanguage with an
// English fallback. Pure map coverage + a render check per overlay.
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'
import {
  OVERLAY_TRANSLATIONS,
  getOverlayStrings,
  formatFieldsCompleted,
} from './overlayTranslations'

// The VAD hook touches getUserMedia / WASM -- unavailable in jsdom.
vi.mock('./useDemoVAD', () => ({
  useDemoVAD: () => ({
    userSpeaking: false,
    loading: false,
    errored: false as const,
    pause: vi.fn(),
    start: vi.fn(),
  }),
}))

// getBackendHttpUrl reads import.meta.env / window.location.
vi.mock('../schema-forms/utils/pdfFiller', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../schema-forms/utils/pdfFiller')>()
  return { ...actual, getBackendHttpUrl: () => 'http://localhost:8000' }
})

// Never build a real connection manager; we inject our mock as the prop.
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

function makeMockManager() {
  const audioManager = {
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    setPTTMode: vi.fn(),
    setVADActive: vi.fn(),
    setNativeVad: vi.fn(),
    setEnergyCallback: vi.fn(),
    isSpeaking: vi.fn(() => false),
    muteInput: vi.fn(),
    unmuteInput: vi.fn(),
    pauseAudioContext: vi.fn(),
    resumeAudioContext: vi.fn(),
    getStream: vi.fn(() => null),
    isRecording: vi.fn(() => false),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    playAudio: vi.fn(async () => {}),
    destroy: vi.fn(),
  }
  return {
    getStatus: vi.fn(() => 'disconnected'),
    isSendingMicAudio: vi.fn(() => false),
    getAudioManager: vi.fn(() => audioManager),
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(async () => {}),
    isPaused: vi.fn(() => false),
    sendActivityStart: vi.fn(),
    sendActivityEnd: vi.fn(async () => {}),
    switchToFirstSection: vi.fn(async () => {}),
    sendAudio: vi.fn(),
    sendPrompt: vi.fn(),
    sendRecoveryPrompt: vi.fn(),
    endGeminiSession: vi.fn(),
    setPushToTalkMode: vi.fn(),
    setPushToTalkHeld: vi.fn(),
    getPushToTalkMode: vi.fn(() => false),
    isNativeVad: vi.fn(() => true),
    getFieldManager: vi.fn(() => null),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => false),
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
  } as any
}

describe('overlayTranslations map', () => {
  it('every language carries every key, non-empty', () => {
    const englishKeys = Object.keys(OVERLAY_TRANSLATIONS['English']).sort()
    for (const [lang, strings] of Object.entries(OVERLAY_TRANSLATIONS)) {
      expect(Object.keys(strings).sort(), `keys for ${lang}`).toEqual(englishKeys)
      for (const [key, value] of Object.entries(strings)) {
        expect(value, `${lang}.${key}`).toBeTruthy()
      }
    }
  })

  it('covers the same language names as the disclaimer button map', async () => {
    const { BUTTON_TRANSLATIONS } = await import(
      '../schema-forms/components/DisclaimerModal'
    )
    expect(Object.keys(OVERLAY_TRANSLATIONS).sort()).toEqual(
      Object.keys(BUTTON_TRANSLATIONS).sort()
    )
  })

  it('falls back to English for unknown / empty languages', () => {
    expect(getOverlayStrings('Klingon')).toBe(OVERLAY_TRANSLATIONS['English'])
    expect(getOverlayStrings('')).toBe(OVERLAY_TRANSLATIONS['English'])
    expect(getOverlayStrings(undefined)).toBe(OVERLAY_TRANSLATIONS['English'])
    expect(getOverlayStrings('Spanish')).toBe(OVERLAY_TRANSLATIONS['Spanish'])
  })

  it('formatFieldsCompleted substitutes both placeholders', () => {
    expect(formatFieldsCompleted(OVERLAY_TRANSLATIONS['English'], 3, 10))
      .toBe('3 of 10 fields completed')
    expect(formatFieldsCompleted(OVERLAY_TRANSLATIONS['Spanish'], 3, 10))
      .toBe('3 de 10 campos completados')
  })

  it('templates keep their placeholders in every language', () => {
    for (const [lang, strings] of Object.entries(OVERLAY_TRANSLATIONS)) {
      expect(strings.fieldsCompleted, lang).toContain('{filled}')
      expect(strings.fieldsCompleted, lang).toContain('{total}')
      expect(strings.fieldsRequiredInfo, lang).toContain('{count}')
      expect(strings.fieldsRequiredInfo, lang).toContain('{required}')
    }
  })
})

describe('overlay panels render translated copy (Spanish)', () => {
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

  it('desktop (VoiceOverlay): Spanish session shows Spanish panel labels', async () => {
    const manager = makeMockManager()
    render(
      <VoiceOverlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status="disconnected"
        initialLanguage="Spanish"
      />
    )
    expect(await screen.findByText(/Reconectar/)).toBeTruthy()
    expect(screen.getByText(/Borrar formulario/)).toBeTruthy()
    expect(screen.getByText(/Modo de entrada:/)).toBeTruthy()
  })

  it('mobile (VoiceOverlayMobile): Spanish session shows Spanish panel labels', async () => {
    const manager = makeMockManager()
    const { container } = render(
      <VoiceOverlayMobile
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status="disconnected"
        initialLanguage="Spanish"
      />
    )
    const fab = container.querySelector('.vff-fab') as HTMLElement
    expect(fab).toBeTruthy()
    fireEvent.click(fab)
    expect(await screen.findByText(/Reconectar/)).toBeTruthy()
    expect(screen.getByText(/Borrar formulario/)).toBeTruthy()
  })
})
