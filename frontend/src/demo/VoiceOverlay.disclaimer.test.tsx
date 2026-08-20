// @vitest-environment jsdom
//
// Component test for VoiceOverlay's disclaimer-agree interrupt ordering
// (bd polyglot-pdf-ovi6; Codex finding on PR #146 / zq9l). When the user taps
// "I Agree", handleDisclaimerAgree must INTERRUPT first -- sendActivityStart()
// then flushAudioQueue() -- and only AFTER that drive the section transition
// (resumePlayback -> sendActivityEnd -> switchToFirstSection). This locks the
// ordering desktop adopted from mobile (zq9l) so a future refactor can't silently
// reorder the interrupt after the switch.
//
// The handler is an inline closure, so we render the real VoiceOverlay, force the
// disclaimer modal open (initialLanguage + a not-yet-accepted stored state), and
// click its real "I Agree" button (onAgree={handleDisclaimerAgree}). The heavy /
// browser-only deps are mocked: useDemoVAD (getUserMedia), getBackendHttpUrl +
// global fetch (the acceptance POST), and createConnectionManager (we inject our
// own mock manager as the connectionManager prop instead).
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'

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

// --- mock createConnectionManager so the component never builds a real one; we
//     inject our recording mock as the connectionManager prop instead.
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

/**
 * Build a mock ConnectionManager whose relevant methods push a label into a
 * shared `calls` array when invoked, so the test can assert relative ordering.
 * getStatus() reports 'connected' until __forceStale() is called; after that it
 * reports 'disconnected' until connect() reconnects it. The reconnect test calls
 * __forceStale() between mount and the Agree click to model a connection that
 * went stale during the disclaimer read (bd polyglot-pdf-ala0).
 */
function makeMockManager(calls: string[]) {
  const audioManager = {
    // tracked for the ordering assertion:
    flushAudioQueue: vi.fn(() => calls.push('flushAudioQueue')),
    resumePlayback: vi.fn(() => calls.push('resumePlayback')),
    // no-op stubs for the methods VoiceOverlay touches during render / mount
    // effects (PTT/VAD wiring) so it does not crash before we reach Agree:
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
  // getStatus reports 'connected' until __forceStale() is called, after which it
  // reports 'disconnected' until connect() reconnects it. The component's
  // mount-time auto-connect would otherwise leave it 'connected' the whole time,
  // so the reconnect test calls manager.__forceStale() AFTER mount but BEFORE the
  // Agree click to model a connection that went stale during the disclaimer read.
  let connected = true
  const manager: any = {
    __forceStale: () => { connected = false },
    // tracked for the ordering assertion:
    getStatus: vi.fn(() => (connected ? 'connected' : 'disconnected')),
    getThinking: vi.fn(() => false),  // bd polyglot-pdf-wpw.5
    isSendingMicAudio: vi.fn(() => connected),
    sendActivityStart: vi.fn(() => calls.push('sendActivityStart')),
    sendActivityEnd: vi.fn(async () => { calls.push('sendActivityEnd') }),
    switchToFirstSection: vi.fn(async () => { calls.push('switchToFirstSection') }),
    getAudioManager: vi.fn(() => audioManager),
    // Every other ConnectionManager method the component's render/mount effects
    // may touch -- harmless stubs so rendering reaches the Agree click. (Full
    // interface stubbed to avoid is-not-a-function crashes from effects we are
    // not exercising, e.g. the pendingDisclaimerRead effect's readDisclaimer.)
    connect: vi.fn(async () => { connected = true; calls.push('connect') }),
    disconnect: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(async () => {}),
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
    isPaused: vi.fn(() => false),
    changeFillLanguage: vi.fn(async () => {}),
    readDisclaimer: vi.fn(),
    startSection: vi.fn(async () => {}),
    switchToSection: vi.fn(async () => {}),
    completeSection: vi.fn(async () => {}),
    getCurrentSectionId: vi.fn(() => 'section_1'),
    getCompletedSectionIds: vi.fn(() => new Set<string>()),
    onVADSpeechStart: vi.fn(),
    onVADSpeechEnd: vi.fn(),
    // bd polyglot-pdf-nlfc: new method called from the alreadyLive branch.
    rearmAudioCapture: vi.fn(async () => {}),
  }
  return manager
}

describe('VoiceOverlay disclaimer-agree interrupt ordering (bd ovi6)', () => {
  beforeEach(() => {
    // jsdom has no sessionStorage by default in this config path; provide a stub
    // store so SchemaFormStateManager (which reads/writes it) does not throw.
    const store: Record<string, string> = {}
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    })
    // fetch for the /api/disclaimer-acceptance POST.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  /**
   * Render `Overlay`, force the disclaimer modal open (initialLanguage + a
   * not-yet-accepted stored state), click "I Agree", and assert the interrupt
   * (sendActivityStart -> flushAudioQueue) fires BEFORE the turn-completion /
   * section-switch (sendActivityEnd -> switchToFirstSection). Shared by both
   * overlays since they now run the same sequence (bd zq9l / ovi6).
   */
  async function assertInterruptOrdering(Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile) {
    const calls: string[] = []
    const manager = makeMockManager(calls)

    // The modal gate reads SchemaFormStateManager.load(): a stored state with
    // disclaimerAccepted=false (and a matching selectedLanguage) lets the modal
    // open instead of auto-skipping to the connected flow. Use mockImplementation
    // (a FRESH object per call), not mockReturnValue: handleDisclaimerAgree
    // mutates the loaded state (state.disclaimerAccepted = true), so a single
    // shared reference would leak that mutation into later load() calls.
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
      disclaimerAccepted: false,
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

    // The disclaimer modal should mount with its "I Agree" button.
    const agreeButton = await screen.findByText('I Agree')

    // Canary: nothing in the tracked sequence should have fired during mount.
    // indexOf below finds the FIRST occurrence, so a spurious mount-time
    // sendActivityStart/flushAudioQueue (e.g. from a VAD effect) would point the
    // ordering checks at the wrong call. Assert a clean slate before the click.
    expect(calls).toHaveLength(0)

    fireEvent.click(agreeButton)

    // handleDisclaimerAgree is async (awaits the fetch + the section switch);
    // wait until the terminal call lands, then assert the relative order.
    await waitFor(() => expect(calls).toContain('switchToFirstSection'))

    expect(manager.sendActivityStart).toHaveBeenCalled()
    expect(manager.getAudioManager().flushAudioQueue).toHaveBeenCalled()
    expect(manager.sendActivityEnd).toHaveBeenCalled()
    // The fresh session must restart in the user's language, not undefined.
    expect(manager.switchToFirstSection).toHaveBeenCalledWith('English')

    // THE ORDERING GUARANTEE (the regression this test exists to catch):
    // the interrupt (activity_start, flush) must precede the turn-completion
    // (resumePlayback -> activity_end) and the section switch. zq9l reordered
    // desktop to match mobile; a refactor that moved the interrupt after
    // switchToFirstSection -- or moved resumePlayback past activity_end -- would
    // break it silently.
    const iStart = calls.indexOf('sendActivityStart')
    const iFlush = calls.indexOf('flushAudioQueue')
    const iResume = calls.indexOf('resumePlayback')
    const iEnd = calls.indexOf('sendActivityEnd')
    const iSwitch = calls.indexOf('switchToFirstSection')

    expect(iStart).toBeGreaterThanOrEqual(0)
    expect(iFlush).toBeGreaterThan(iStart)        // flush right after start (the interrupt)
    expect(iResume).toBeGreaterThan(iFlush)       // resume playback after the interrupt
    expect(iEnd).toBeGreaterThan(iResume)         // end-of-turn after resume
    expect(iSwitch).toBeGreaterThan(iEnd)         // section switch last
  }

  /**
   * On the RECONNECT path (connection went stale during the disclaimer read),
   * handleDisclaimerAgree must NOT send activity_end (bd polyglot-pdf-ala0): the
   * earlier sendActivityStart opened the turn on the OLD connection, so the fresh
   * connection has no matching open turn -- an activity_end there is an unmatched
   * signal. It must still reconnect and switchToFirstSection (which drives the new
   * session's turn). This is the regression guard for the ala0 fix.
   */
  async function assertReconnectSkipsActivityEnd(Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile) {
    const calls: string[] = []
    const manager = makeMockManager(calls)

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
      disclaimerAccepted: false,
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

    const agreeButton = await screen.findByText('I Agree')

    // Mark the connection stale NOW (post-mount, pre-Agree): the component
    // auto-connects on mount, so getStatus() would otherwise be 'connected'
    // and the reconnect branch would never run. This models the connection
    // dropping during the (long) disclaimer read.
    manager.__forceStale()

    fireEvent.click(agreeButton)

    // Wait for the terminal call (the section switch) to land.
    await waitFor(() => expect(manager.switchToFirstSection).toHaveBeenCalledWith('English'))

    // The reconnect branch ran (connect() was called)...
    expect(manager.connect).toHaveBeenCalled()
    // ...and the section restart still happened...
    expect(manager.switchToFirstSection).toHaveBeenCalled()
    // ...but NO activity_end was sent on the freshly-reconnected session.
    expect(manager.sendActivityEnd).not.toHaveBeenCalled()
    expect(calls).not.toContain('sendActivityEnd')
  }

  it('desktop (VoiceOverlay): interrupts before the section transition on Agree', async () => {
    await assertInterruptOrdering(VoiceOverlay)
  })

  it('mobile (VoiceOverlayMobile): interrupts before the section transition on Agree', async () => {
    await assertInterruptOrdering(VoiceOverlayMobile)
  })

  it('desktop (VoiceOverlay): skips activity_end on the reconnect path (ala0)', async () => {
    await assertReconnectSkipsActivityEnd(VoiceOverlay)
  })

  it('mobile (VoiceOverlayMobile): skips activity_end on the reconnect path (ala0)', async () => {
    await assertReconnectSkipsActivityEnd(VoiceOverlayMobile)
  })

  /**
   * Soft page-refresh mid-session (bd polyglot-pdf-fn1m): the mount auto-connect
   * fall-through must NOT re-show the disclaimer (nor request it be read aloud)
   * when it was ALREADY accepted -- otherwise the agree screen re-appears while
   * the resumed voice session is speaking mid-section. It must still RECONNECT
   * (to resume the session). Modeled by a stored state with
   * disclaimerAccepted=true and a NOT-yet-live connection at mount (so the
   * alreadyLive guard is skipped and the reload fall-through runs).
   */
  async function assertAcceptedSoftRefreshResumeSkipsDisclaimer(
    Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile,
  ) {
    const calls: string[] = []
    const manager = makeMockManager(calls)
    // Not yet connected at mount, so the alreadyLive guard is false and the
    // reload fall-through path (the one this bead fixes) runs.
    manager.__forceStale()

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
      disclaimerAccepted: true, // already accepted -> a soft-refresh resume
      selectedLanguage: 'English',
    } as any))
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})

    render(
      <Overlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status="disconnected"
        initialLanguage="English"
      />
    )

    // The mount effect reconnects to resume the session...
    await waitFor(() => expect(manager.connect).toHaveBeenCalled())

    // ...but the disclaimer is NOT re-shown (no "I Agree") and is NOT read aloud
    // (readDisclaimer, driven by pendingDisclaimerRead, never fires). Give any
    // pending microtasks/effects a beat to settle before asserting absence.
    await waitFor(() => expect(manager.connect).toHaveBeenCalled())
    expect(screen.queryByText('I Agree')).toBeNull()
    expect(manager.readDisclaimer).not.toHaveBeenCalled()
  }

  it('desktop (VoiceOverlay): soft-refresh resume with disclaimer accepted reconnects WITHOUT re-showing/re-reading the disclaimer (fn1m)', async () => {
    await assertAcceptedSoftRefreshResumeSkipsDisclaimer(VoiceOverlay)
  })

  it('mobile (VoiceOverlayMobile): soft-refresh resume with disclaimer accepted reconnects WITHOUT re-showing/re-reading the disclaimer (fn1m)', async () => {
    await assertAcceptedSoftRefreshResumeSkipsDisclaimer(VoiceOverlayMobile)
  })

  // ---- ONE SOURCE: the register the applicant actually accepts (bd nsb4y) ----
  //
  // Settled by the maintainer 2026-08-19: what the modal RENDERS and what the
  // model SPEAKS must be the same text. Before this, the modal showed "we
  // strongly advise" (advice) while Sol's clip said "you agree to review" (an
  // undertaking) -- two legal registers behind ONE Agree button, decided by
  // whether the user listened or read.
  //
  // These drive the REAL overlay, with no introParagraphs prop, so they
  // exercise the component's own decision about which text to show. A
  // DisclaimerModal-level test cannot: passing the prop explicitly bypasses
  // exactly the gate that was the bug (verified -- that test stayed green
  // through a mutation restoring it).
  async function assertScreenStatesTheUndertaking(Overlay: typeof VoiceOverlay) {
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
      disclaimerAccepted: false,
      selectedLanguage: 'English',
    } as any))
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})

    render(
      <Overlay
        schema={MINIMAL_SCHEMA}
        connectionManager={makeMockManager([])}
        status="connected"
        initialLanguage="English"
      />
    )
    await screen.findByText('I Agree')

    const body = document.body.textContent?.toLowerCase() ?? ''
    // The UNDERTAKING must be on screen...
    expect(body).toContain('agree to review the completed document')
    expect(body).toContain('certified professional')
    // ...and the retired advisory copy must NOT be, or both registers are live
    // at once and the Agree click is ambiguous again.
    expect(body).not.toContain('we strongly advise')
  }

  it('desktop (VoiceOverlay): the SCREEN states the review undertaking, unconditionally (nsb4y)', async () => {
    await assertScreenStatesTheUndertaking(VoiceOverlay)
  })

  it('mobile (VoiceOverlayMobile): the SCREEN states the review undertaking, unconditionally (nsb4y)', async () => {
    await assertScreenStatesTheUndertaking(VoiceOverlayMobile)
  })
})
