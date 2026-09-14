/**
 * createConnectionManager's onFormComplete callback (bd polyglot-pdf-8v8i7).
 *
 * SchemaForm.tsx passes this to auto-clear browser storage the moment
 * WebFormConnection reports every section done. Mirrors connection.test.ts's
 * mocking pattern: WebFormConnection is mocked, so the backend-driven
 * onFormComplete handshake callback is simulated by capturing the callbacks
 * object the factory hands to the WebFormConnection constructor and invoking
 * it directly.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createConnectionManager } from './connection'
import type { FormSchema } from '../schema-forms/types/schema'

let capturedCallbacks: any = null

vi.mock('./fieldManager', () => ({
  createFieldManager: vi.fn(() => ({ cleanup: vi.fn(), destroy: vi.fn() }))
}))

vi.mock('./audioManager', () => ({
  createAudioManager: vi.fn(() => ({
    playAudio: vi.fn(() => Promise.resolve()),
    stopRecording: vi.fn(),
    startRecording: vi.fn(() => Promise.resolve()),
    getPlaybackBacklog: vi.fn(() => ({})),
    isAnyAudioPlaying: vi.fn(() => false),
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    resumeAudioContext: vi.fn(),
    setPTTMode: vi.fn(),
    muteInput: vi.fn(),
    unmuteInput: vi.fn()
  }))
}))

vi.mock('../webFormConnection', () => ({
  WebFormConnection: vi.fn(function (this: any, _schema: any, callbacks: any) {
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
    this.setVoiceMode = vi.fn()
    this.setGetToken = vi.fn()
    this.getState = vi.fn()
    return this
  })
}))

describe('createConnectionManager onFormComplete (bd polyglot-pdf-8v8i7)', () => {
  let sessionStorageMock: { [key: string]: string }
  let testSchema: FormSchema

  beforeEach(() => {
    capturedCallbacks = null
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
        title: 'Test Form', version: '1.0.0', language: 'en',
        form_number: 'TEST', edition_date: '01/01/25', page_count: 1
      },
      sections: [
        { id: 's1', label: 'Section 1', order: 1, fields: [] }
      ],
      fields: []
    } as any
  })

  it('invokes the caller-supplied onFormComplete when WebFormConnection reports form complete', async () => {
    const onFormComplete = vi.fn()
    const manager = createConnectionManager(
      testSchema,
      vi.fn(),
      'English',
      undefined,
      undefined,
      undefined,
      undefined,
      onFormComplete
    )
    await manager.connect()

    expect(capturedCallbacks).toBeTruthy()
    capturedCallbacks.onFormComplete()

    expect(onFormComplete).toHaveBeenCalledTimes(1)
  })

  it('does not throw when no onFormComplete callback is supplied (existing callers unaffected)', async () => {
    const manager = createConnectionManager(testSchema, vi.fn(), 'English')
    await manager.connect()

    expect(() => capturedCallbacks.onFormComplete()).not.toThrow()
  })
})
