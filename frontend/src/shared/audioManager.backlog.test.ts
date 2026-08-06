/**
 * getPlaybackBacklog diagnostic (bd polyglot-pdf-0rpu Stage 0c).
 *
 * The playback path schedules chunks at a session-lifetime `playbackTime`
 * cursor; the backlog snapshot (aheadSec / activeSources / blocked) is what the
 * attribution runs read at tool-response time to tell "stale client audio
 * played late" from "the model generated wrong audio". This pins that the
 * snapshot is a safe pure read: present on the interface, zero-valued before
 * any playback context exists, and reflecting the blocked flag.
 *
 * ASCII only. jsdom env.
 */
import { describe, it, expect } from 'vitest'
import { createAudioManager } from './audioManager'

describe('audioManager.getPlaybackBacklog', () => {
  it('returns a zeroed snapshot before any playback exists, and never throws', () => {
    const mgr = createAudioManager()
    const snap = mgr.getPlaybackBacklog()
    expect(snap).toEqual({ aheadSec: 0, activeSources: 0, blocked: false })
  })

  it('reflects the blocked flag set by flushAudioQueue', () => {
    const mgr = createAudioManager()
    // flushAudioQueue with no context must not throw, and sets the block.
    mgr.flushAudioQueue()
    expect(mgr.getPlaybackBacklog().blocked).toBe(true)
    mgr.resumePlayback()
    expect(mgr.getPlaybackBacklog().blocked).toBe(false)
  })
})
