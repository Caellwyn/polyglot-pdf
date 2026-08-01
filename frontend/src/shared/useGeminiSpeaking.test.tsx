// @vitest-environment jsdom
//
// Tests for the speaking signal behind Sol's speaking state (bd polyglot-pdf-2p4y).
//
// The two things worth pinning here are the ones that bite later:
//   1. CHAINING. The hook claims window.vffOnAudioPlaybackStart/End, which the
//      audio manager fires and (today) nobody else consumes. If a watchdog is
//      added later it must not be silently dropped, and the overlay remounts on
//      a desktop<->mobile breakpoint cross, so the previous handler has to be
//      called AND restored on unmount.
//   2. THE BARGE-IN HOLE. flushAudioQueue() stops playback WITHOUT firing the
//      end event (deliberately -- firing it there would spam the watchdog), so a
//      purely event-driven flag would stick "speaking" on forever after the user
//      interrupts. The reconcile poll closes that.
import { render, cleanup, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useGeminiSpeaking } from './useGeminiSpeaking'
import type { AudioManager } from './audioManager'

function makeAudioManager(speaking = false) {
  let s = speaking
  return {
    isSpeaking: vi.fn(() => s),
    __set: (v: boolean) => { s = v },
  } as unknown as AudioManager & { __set: (v: boolean) => void }
}

function Probe({ am }: { am: AudioManager | null }) {
  const speaking = useGeminiSpeaking(am)
  return <span data-testid="v">{String(speaking)}</span>
}

const val = (c: HTMLElement) => c.querySelector('[data-testid="v"]')!.textContent

describe('useGeminiSpeaking', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    delete (window as Window).vffOnAudioPlaybackStart
    delete (window as Window).vffOnAudioPlaybackEnd
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    delete (window as Window).vffOnAudioPlaybackStart
    delete (window as Window).vffOnAudioPlaybackEnd
  })

  it('starts false and follows the playback start/end events', () => {
    const am = makeAudioManager()
    const { container } = render(<Probe am={am} />)
    expect(val(container)).toBe('false')

    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(val(container)).toBe('true')

    act(() => { window.vffOnAudioPlaybackEnd!() })
    expect(val(container)).toBe('false')
  })

  it('chains a pre-existing handler instead of clobbering it', () => {
    const priorStart = vi.fn()
    const priorEnd = vi.fn()
    window.vffOnAudioPlaybackStart = priorStart
    window.vffOnAudioPlaybackEnd = priorEnd

    const { container } = render(<Probe am={makeAudioManager()} />)

    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(priorStart).toHaveBeenCalledTimes(1)
    expect(val(container)).toBe('true')

    act(() => { window.vffOnAudioPlaybackEnd!() })
    expect(priorEnd).toHaveBeenCalledTimes(1)
    expect(val(container)).toBe('false')
  })

  it('restores the previous handlers on unmount (overlay remounts on a breakpoint cross)', () => {
    const priorStart = vi.fn()
    const priorEnd = vi.fn()
    window.vffOnAudioPlaybackStart = priorStart
    window.vffOnAudioPlaybackEnd = priorEnd

    const { unmount } = render(<Probe am={makeAudioManager()} />)
    expect(window.vffOnAudioPlaybackStart).not.toBe(priorStart)

    unmount()
    expect(window.vffOnAudioPlaybackStart).toBe(priorStart)
    expect(window.vffOnAudioPlaybackEnd).toBe(priorEnd)
  })

  it('clears speaking after a barge-in flush, which fires NO end event', () => {
    const am = makeAudioManager()
    const { container } = render(<Probe am={am} />)

    // Playback starts, and the manager agrees it is speaking.
    am.__set(true)
    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(val(container)).toBe('true')

    // Barge-in: the queue is flushed. No end event is fired -- by design.
    am.__set(false)
    expect(val(container)).toBe('true')  // still stuck, until the poll reconciles

    act(() => { vi.advanceTimersByTime(250) })
    expect(val(container)).toBe('false')
  })

  it('does not poll while idle (no audio manager churn when nothing is playing)', () => {
    const am = makeAudioManager()
    render(<Probe am={am} />)
    act(() => { vi.advanceTimersByTime(2000) })
    // Never speaking -> the reconcile effect never armed.
    expect(am.isSpeaking).not.toHaveBeenCalled()
  })

  it('with a null audio manager, a start event clamps straight back to silence', () => {
    // Pins the branch the stuck-flag fix introduced. With no manager there is
    // nothing to reconcile against and no end event is coming, so believing the
    // start event would strand `speaking` true forever. The clamp runs in the
    // same commit as the event, so this never even flickers true.
    const { container } = render(<Probe am={null} />)
    expect(val(container)).toBe('false')

    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(val(container)).toBe('false')

    act(() => { vi.advanceTimersByTime(500) })
    expect(val(container)).toBe('false')
  })

  it('a LIVE manager still engages on the start event (the clamp is null-only)', () => {
    // Guards the obvious over-correction: if the clamp ever fired for a live
    // manager, speaking would never engage at all and Sol's speaking state would
    // be dead. `isSpeaking()` returning false must NOT suppress the event -- the
    // reconcile poll is what lowers the flag later, 200ms in.
    const am = makeAudioManager(false)
    const { container } = render(<Probe am={am} />)

    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(val(container)).toBe('true')

    act(() => { vi.advanceTimersByTime(250) })
    expect(val(container)).toBe('false')
  })

  it('clears a stuck speaking flag when the audio manager goes away', () => {
    // disconnect() nulls the manager. If we kept believing audio was playing,
    // no end event would ever arrive and there would be nothing to reconcile
    // against -- leaving Sol permanently "speaking" with flat, zero-amplitude
    // ray-breathing across the reconnect. Clearing is the only honest option.
    const am = makeAudioManager(true)
    const { container, rerender } = render(<Probe am={am} />)
    act(() => { window.vffOnAudioPlaybackStart!() })
    expect(val(container)).toBe('true')

    act(() => { rerender(<Probe am={null} />) })
    expect(val(container)).toBe('false')
  })
})
