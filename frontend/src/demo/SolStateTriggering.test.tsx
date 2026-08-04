// @vitest-environment jsdom
//
// End-to-end state-triggering tests for Sol in the LIVE overlays
// (bd polyglot-pdf-2p4y follow-up; maintainer asked to "test to make sure
// animations are correctly triggering on correct states").
//
// The distinction from the existing Sol test files:
//   - solState.test.ts     pins the PURE mapping function in isolation.
//   - Sol.test.tsx         pins the COMPONENT and the stylesheet text.
//   - THIS file renders the REAL VoiceOverlay / VoiceOverlayMobile, feeds them
//     the same live session signals the app feeds them (status string, thinking
//     flag, audio-playback events, mic send gate), and asserts the avatar that
//     actually reaches the DOM carries the right `data-state`.
//
// That last hop is the one nothing covered: both overlays could wire
// `deriveSolState` to the wrong argument, pass a stale value, or drop a signal
// entirely, and every other test in the suite would still pass. The mapping
// being correct is not the same as the overlays USING it correctly.
//
// `data-state` is the entire CSS API -- every animation in SOL_CSS is selected
// by `.sol[data-state="..."]` -- so asserting the attribute is asserting which
// animation engages. jsdom cannot run the animations themselves; Sol.test.tsx
// covers the stylesheet side (which properties each state drives).
import { render, cleanup, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { ConnectionManager } from '../shared/connection'

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

const LIVE_STATE = {
  schema: MINIMAL_SCHEMA, fieldValues: {}, currentSectionId: 'section_1',
  completedSections: new Set<string>(), validationErrors: {}, lastUpdated: 0,
  formSessionId: 'fss_test', loadedFieldIds: new Set<string>(),
  jitModeEnabled: false, disclaimerAccepted: true, selectedLanguage: 'English',
}

/**
 * A manager whose audio side can be driven: `speaking` controls what
 * `isSpeaking()` reports (the barge-in reconcile source), and `sendingMic`
 * controls the connection send gate that gates Sol's listening state.
 *
 * IMPORTANT -- `micSending` in the overlays needs BOTH halves of the real gate:
 * a worklet frame arriving through `setEnergyCallback` with its own `sending`
 * flag, AND `isSendingMicAudio()` returning true. Stubbing only the latter (as
 * a first draft of this file did) leaves `micSending` false forever and the
 * listening state unreachable -- so the mock actually delivers a frame, the way
 * the audio worklet does ~50x/sec in production.
 */
function makeMockManager(
  status: string,
  opts?: { sendingMic?: boolean; speaking?: boolean },
): ConnectionManager {
  // Cleared on unsubscribe (cb === null) and by the suite's fake-timer reset.
  let energyTimer: number | null = null
  const audioManager = {
    setPTTMode: vi.fn(), setVADActive: vi.fn(), setNativeVad: vi.fn(),
    setEnergyCallback: vi.fn((cb: ((energy: number, sending: boolean) => void) | null) => {
      // Model the worklet's CONTINUOUS delivery (~50x/sec), not a single frame.
      // The overlay treats a frame older than 250ms as stale and decays energy
      // to 0, so a one-shot push makes amplitude assertions flaky-by-design:
      // they pass if checked immediately and fail once the clock advances past
      // the staleness window. Keeping a repeating emitter is what the real audio
      // path does and is what lets --e actually climb.
      if (energyTimer !== null) { clearInterval(energyTimer); energyTimer = null }
      if (cb && opts?.sendingMic) {
        cb(45, true)
        energyTimer = setInterval(() => cb(45, true), 20) as unknown as number
      }
    }),
    isSpeaking: vi.fn(() => opts?.speaking ?? false),
    getOutputEnergy: vi.fn(() => (opts?.speaking ? 60 : 0)),
    muteInput: vi.fn(), unmuteInput: vi.fn(),
    pauseAudioContext: vi.fn(), resumeAudioContext: vi.fn(),
    flushAudioQueue: vi.fn(), resumePlayback: vi.fn(),
    getStream: vi.fn(() => null), isRecording: vi.fn(() => false),
    startRecording: vi.fn(async () => {}), stopRecording: vi.fn(),
    playAudio: vi.fn(async () => {}), destroy: vi.fn(),
  }
  const manager = {
    connect: vi.fn(async () => {}), disconnect: vi.fn(), pause: vi.fn(),
    resume: vi.fn(async () => {}),
    getStatus: vi.fn(() => status),
    getThinking: vi.fn(() => false),
    isSendingMicAudio: vi.fn(() => opts?.sendingMic ?? false),
    sendAudio: vi.fn(), sendActivityStart: vi.fn(),
    sendActivityEnd: vi.fn(async () => {}), sendPrompt: vi.fn(),
    sendRecoveryPrompt: vi.fn(), endGeminiSession: vi.fn(),
    setPushToTalkMode: vi.fn(), setPushToTalkHeld: vi.fn(),
    getPushToTalkMode: vi.fn(() => true),
    isNativeVad: vi.fn(() => true),
    getFieldManager: vi.fn(() => null),
    getAudioManager: vi.fn(() => audioManager),
    startRecording: vi.fn(async () => {}), stopRecording: vi.fn(),
    isRecording: vi.fn(() => false),
    isPaused: vi.fn(() => status === 'paused'),
    rearmAudioCapture: vi.fn(async () => {}),
    changeFillLanguage: vi.fn(async () => {}), readDisclaimer: vi.fn(), switchToFirstSection: vi.fn(async () => {}),
    startSection: vi.fn(async () => {}), switchToSection: vi.fn(async () => {}),
    completeSection: vi.fn(async () => {}),
    getCurrentSectionId: vi.fn(() => 'section_1'),
    getCompletedSectionIds: vi.fn(() => new Set<string>()),
    onVADSpeechStart: vi.fn(), onVADSpeechEnd: vi.fn(),
  }
  return manager as unknown as ConnectionManager
}

/**
 * Let the overlay's mic-energy rAF loop publish one frame. These specs run on
 * fake timers (the overlays have connect-poll setTimeout loops that must not run
 * in real time), so rAF is driven by advancing the fake clock rather than by
 * awaiting a real frame.
 */
async function advanceOneFrame() {
  await act(async () => { vi.advanceTimersByTime(32) })
}

/**
 * Let amplitude propagate all the way to a CSS variable.
 *
 * The MIC path genuinely needs several frames: it has TWO hops, each on its own
 * rAF loop -- the overlay publishes `micEnergy` state from the worklet frame,
 * then Sol's loop exponentially smooths that into --e (`fast += (target - fast)
 * * 0.14`). Measured: --e is unset on frame 1 and 0.063 on frame 2.
 *
 * The OUTPUT path (speaking) has only ONE hop, since Sol pulls the getter
 * directly, and measurably clears zero on a single frame (0.084 from the mock's
 * 60). Those tests therefore do not need this helper -- they use it only for
 * uniformity, and are stricter than required. Stated plainly because an earlier
 * version of this comment claimed one frame was insufficient for BOTH, which is
 * false for the output path and would mislead anyone tuning the frame count.
 */
async function advanceFrames(n = 20) {
  for (let i = 0; i < n; i++) {
    await act(async () => { vi.advanceTimersByTime(16) })
  }
}

function stubEnv() {
  const store: Record<string, string> = {}
  vi.stubGlobal('sessionStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { for (const k of Object.keys(store)) delete store[k] },
    key: () => null, length: 0,
  })
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
  vi.spyOn(SchemaFormStateManager, 'load').mockImplementation(() => ({ ...LIVE_STATE } as any))
  vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})
}

// Every status string the overlays can actually emit, paired with the state Sol
// must show for it. This is the same producer set solState.test.ts enumerates,
// asserted here through the REAL overlay render instead of the pure function.
const STATUS_TO_STATE: Array<[string, string]> = [
  ['Ready', 'idle'],
  ['connecting', 'connecting'],
  ['Setting up audio...', 'connecting'],
  ['warming', 'connecting'],
  ['switching_section', 'connecting'],
  ['reconnecting', 'connecting'],
  ['Reconnecting to section 2', 'connecting'],
  ['connected', 'idle'],           // connected but no activity flags
  ['paused', 'paused'],
  ['disconnected', 'offline'],
  ['error', 'offline'],
  ['idle_timeout', 'offline'],
  ['reconnect_failed', 'offline'],
]

describe('Sol state triggering through the DESKTOP overlay', () => {
  beforeEach(() => { vi.useFakeTimers(); stubEnv() })
  afterEach(() => {
    cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()
    delete (window as Window).vffOnAudioPlaybackStart
    delete (window as Window).vffOnAudioPlaybackEnd
  })

  function renderDesktop(status: string, opts?: {
    thinking?: boolean; sendingMic?: boolean; speaking?: boolean
  }) {
    return render(
      <VoiceOverlay
        schema={MINIMAL_SCHEMA}
        connectionManager={makeMockManager(status, opts)}
        status={status}
        thinking={opts?.thinking}
        initialLanguage="English"
      />
    )
  }

  const solState = (c: HTMLElement) =>
    c.querySelector('[data-testid="sol-avatar"]')?.getAttribute('data-state')

  it.each(STATUS_TO_STATE)('status %j renders Sol as %s', (status, expected) => {
    const { container } = renderDesktop(status)
    expect(solState(container)).toBe(expected)
  })

  it('thinking flag on a live session triggers the thinking animation', () => {
    const { container } = renderDesktop('connected', { thinking: true })
    expect(solState(container)).toBe('thinking')
  })

  it('a live mic send gate triggers the listening animation', async () => {
    // micSending is published from the overlay's rAF loop, so let one frame run.
    const { container } = renderDesktop('connected', { sendingMic: true })
    await advanceOneFrame()
    expect(solState(container)).toBe('listening')
  })

  it('an audio-playback START event triggers the speaking animation', () => {
    // This is the real signal path: audioManager fires the window hook, the
    // useGeminiSpeaking hook picks it up, and Sol must flip to speaking.
    const { container } = renderDesktop('connected', { speaking: true })
    expect(solState(container)).toBe('idle')

    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(solState(container)).toBe('speaking')
  })

  it('an audio-playback END event returns Sol out of speaking', () => {
    const { container } = renderDesktop('connected', { speaking: true })
    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(solState(container)).toBe('speaking')

    act(() => { window.vffOnAudioPlaybackEnd!() })
    expect(solState(container)).toBe('idle')
  })

  it('speaking outranks a simultaneous mic send gate (half-duplex turn)', async () => {
    const { container } = renderDesktop('connected', { sendingMic: true, speaking: true })
    await advanceOneFrame()
    expect(solState(container)).toBe('listening')
    act(() => { window.vffOnAudioPlaybackStart!() })
    // The assistant talking wins over our own mic still being open.
    expect(solState(container)).toBe('speaking')
  })

  it('speaking outranks thinking (agent_processing can stay armed into audio)', () => {
    const { container } = renderDesktop('connected', { thinking: true, speaking: true })
    expect(solState(container)).toBe('thinking')
    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(solState(container)).toBe('speaking')
  })

  it('paused outranks every activity signal', () => {
    const { container } = renderDesktop('paused', {
      thinking: true, sendingMic: true, speaking: true,
    })
    act(() => { window.vffOnAudioPlaybackStart?.() })
    expect(solState(container)).toBe('paused')
  })

  it('a dropped session outranks a stale speaking flag', () => {
    const { container } = renderDesktop('disconnected', { speaking: true })
    act(() => { window.vffOnAudioPlaybackStart?.() })
    expect(solState(container)).toBe('offline')
  })

  it('Sol is fed the live MIC energy value, not a constant', async () => {
    // Asserts on --e, the variable every amplitude-driven listening rule reads.
    // An earlier version of this test checked --k instead, which is derived
    // purely from the `size` prop and set unconditionally in every state -- so
    // it passed even with `energy={0}` hardcoded in the overlay, i.e. it pinned
    // nothing it claimed to. Mutation-checked: substituting energy={0} in
    // VoiceOverlay.tsx must fail this.
    const { container } = renderDesktop('connected', { sendingMic: true })
    await advanceFrames()
    const svg = container.querySelector('[data-testid="sol-avatar"]') as HTMLElement
    expect(svg.getAttribute('data-state')).toBe('listening')
    // The mock worklet frame carries energy 45, so the smoothed value must climb
    // above zero once the loop has run.
    expect(parseFloat(svg.style.getPropertyValue('--e'))).toBeGreaterThan(0)
  })

  it('Sol is fed the live AI-OUTPUT energy getter while speaking', async () => {
    // The highest-value wire on this branch and previously unpinned: post-swap,
    // speaking's ENTIRE visible animation (ray length, from --e) comes from
    // getOutputEnergy. Sol falls back to `?? 0` when the prop is missing, so a
    // dropped prop yields a silently STATIC speaking avatar with no error --
    // exactly the bug that shipped in the dev preview. Mutation-checked:
    // deleting getOutputEnergy from the overlay's <Sol> must fail this.
    const { container } = renderDesktop('connected', { speaking: true })
    act(() => { window.vffOnAudioPlaybackStart!() })
    await advanceFrames()
    const svg = container.querySelector('[data-testid="sol-avatar"]') as HTMLElement
    expect(svg.getAttribute('data-state')).toBe('speaking')
    // The mock returns 60 while speaking; a missing prop would leave this at 0.
    expect(parseFloat(svg.style.getPropertyValue('--e'))).toBeGreaterThan(0)
  })
})

describe('Sol state triggering through the MOBILE overlay', () => {
  beforeEach(() => { vi.useFakeTimers(); stubEnv() })
  afterEach(() => {
    cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()
    delete (window as Window).vffOnAudioPlaybackStart
    delete (window as Window).vffOnAudioPlaybackEnd
  })

  function renderMobile(status: string, opts?: {
    thinking?: boolean; sendingMic?: boolean; speaking?: boolean
  }) {
    return render(
      <VoiceOverlayMobile
        schema={MINIMAL_SCHEMA}
        connectionManager={makeMockManager(status, opts)}
        status={status}
        thinking={opts?.thinking}
        initialLanguage="English"
      />
    )
  }

  // The FAB's Sol is always mounted (the panel's is only there when expanded),
  // so scope to the FAB -- it is also the instance that matters most, being the
  // only status a user sees while collapsed.
  const fabSolState = (c: HTMLElement) =>
    c.querySelector('.vff-fab [data-testid="sol-avatar"]')?.getAttribute('data-state')

  it.each(STATUS_TO_STATE)('status %j renders the FAB Sol as %s', (status, expected) => {
    const { container } = renderMobile(status)
    expect(fabSolState(container)).toBe(expected)
  })

  it('thinking flag triggers the thinking animation on the FAB', () => {
    const { container } = renderMobile('connected', { thinking: true })
    expect(fabSolState(container)).toBe('thinking')
  })

  it('a live mic send gate triggers listening on the FAB', async () => {
    const { container } = renderMobile('connected', { sendingMic: true })
    await advanceOneFrame()
    expect(fabSolState(container)).toBe('listening')
  })

  it('an audio-playback START event triggers speaking on the FAB', () => {
    const { container } = renderMobile('connected', { speaking: true })
    expect(fabSolState(container)).toBe('idle')
    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(fabSolState(container)).toBe('speaking')
  })

  it('the FAB and the expanded panel always agree on the state', async () => {
    // Two Sol instances driven by one derived value; they must never disagree,
    // or the collapsed and expanded views would tell the user different things.
    const { container } = renderMobile('connected', { sendingMic: true })
    const fab = container.querySelector('.vff-fab') as HTMLElement
    fireEvent.click(fab)
    await advanceOneFrame()

    const all = [...container.querySelectorAll('[data-testid="sol-avatar"]')]
      .map(el => el.getAttribute('data-state'))
    expect(all.length).toBeGreaterThanOrEqual(2)
    expect(new Set(all).size).toBe(1)
    expect(all[0]).toBe('listening')
  })

  it('the FAB Sol is fed the live AI-OUTPUT energy getter while speaking', async () => {
    // Mobile mounts TWO Sols and both need the getter; the FAB is the one that
    // matters most, being the only status visible while collapsed.
    const { container } = renderMobile('connected', { speaking: true })
    act(() => { window.vffOnAudioPlaybackStart!() })
    await advanceFrames()
    const svg = container.querySelector('.vff-fab [data-testid="sol-avatar"]') as HTMLElement
    expect(svg.getAttribute('data-state')).toBe('speaking')
    expect(parseFloat(svg.style.getPropertyValue('--e'))).toBeGreaterThan(0)
  })

  it('the expanded panel Sol also gets a live amplitude source', async () => {
    // The third shipped mount site. Pinned separately because a dropped prop on
    // just this one would leave the panel static while the FAB animated.
    const { container } = renderMobile('connected', { speaking: true })
    const fab = container.querySelector('.vff-fab') as HTMLElement
    fireEvent.click(fab)
    act(() => { window.vffOnAudioPlaybackStart!() })
    await advanceFrames()
    const panelSol = container.querySelector(
      '.vff-panel-mobile [data-testid="sol-avatar"]'
    ) as HTMLElement
    expect(panelSol).toBeTruthy()
    expect(panelSol.getAttribute('data-state')).toBe('speaking')
    expect(parseFloat(panelSol.style.getPropertyValue('--e'))).toBeGreaterThan(0)
  })

  it('the screen-reader status text tracks the same state as the avatar', () => {
    // Sol is aria-hidden on the FAB; the live region is the non-visual
    // equivalent, so the two must not drift apart.
    const { container } = renderMobile('disconnected')
    expect(fabSolState(container)).toBe('offline')
    const live = container.querySelector('[role="status"].vff-sr-only')
    expect(live?.textContent).toBe('Not connected')
  })
})
