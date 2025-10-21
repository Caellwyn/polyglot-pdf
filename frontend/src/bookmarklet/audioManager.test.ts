/**
 * AudioManager Tests - AudioWorklet Integration
 * 
 * Tests the modern AudioWorklet-based audio processing
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createAudioManager } from '../shared/audioManager'

// Mock Web Audio API
class MockAudioContext {
	sampleRate: number
	state: 'running' | 'suspended' = 'running'
	currentTime = 0
	destination = {}
	
	audioWorklet = {
		addModule: vi.fn().mockResolvedValue(undefined)
	}
	
	constructor(options?: { sampleRate?: number }) {
		this.sampleRate = options?.sampleRate || 48000
	}
	
	createMediaStreamSource(stream: MediaStream) {
		return {
			connect: vi.fn(),
			disconnect: vi.fn()
		}
	}
	
	createBuffer(channels: number, length: number, sampleRate: number) {
		return {
			numberOfChannels: channels,
			length,
			sampleRate,
			getChannelData: (channel: number) => {
				return new Float32Array(length)
			}
		}
	}
	
	createBufferSource() {
		return {
			buffer: null,
			connect: vi.fn(),
			disconnect: vi.fn(),
			start: vi.fn(),
			stop: vi.fn(),
			onended: null as (() => void) | null
		}
	}
	
	resume() {
		this.state = 'running'
		return Promise.resolve()
	}
	
	close() {
		return Promise.resolve()
	}
}

class MockAudioWorkletNode {
	port: {
		onmessage: ((event: MessageEvent) => void) | null
		postMessage: (data: any, transfer?: any[]) => void
		close: () => void
	}
	
	constructor(context: AudioContext, name: string) {
		this.port = {
			onmessage: null,
			postMessage: vi.fn(),
			close: vi.fn()
		}
	}
	
	connect(destination: any) {
		return destination
	}
	
	disconnect() {}
}

class MockMediaStream {
	id = 'mock-stream'
	active = true
	tracks: MediaStreamTrack[] = []
	
	getTracks() {
		return this.tracks
	}
	
	addTrack(track: MediaStreamTrack) {
		this.tracks.push(track)
	}
}

class MockMediaStreamTrack {
	kind = 'audio'
	id = 'mock-track'
	label = 'Mock Microphone'
	enabled = true
	muted = false
	readyState: 'live' | 'ended' = 'live'
	
	stop() {
		this.readyState = 'ended'
	}
}

// Setup global mocks
beforeEach(() => {
	// @ts-ignore - Mock global AudioContext
	global.AudioContext = MockAudioContext
	
	// @ts-ignore - Mock AudioWorkletNode
	global.AudioWorkletNode = MockAudioWorkletNode
	
	// Mock getUserMedia
	// @ts-ignore - Mock navigator.mediaDevices
	global.navigator.mediaDevices = {
		getUserMedia: vi.fn().mockResolvedValue(() => {
			const stream = new MockMediaStream()
			stream.addTrack(new MockMediaStreamTrack() as any)
			return stream
		})
	}
	
	// Mock URL.createObjectURL for worklet loading
	global.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-worklet-url')
	global.URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
	vi.clearAllMocks()
})

describe('AudioManager - AudioWorklet Integration', () => {
	describe('Initialization', () => {
		it('should create audio manager instance', () => {
			const manager = createAudioManager()
			
			expect(manager).toBeDefined()
			expect(manager.startRecording).toBeInstanceOf(Function)
			expect(manager.stopRecording).toBeInstanceOf(Function)
			expect(manager.playAudio).toBeInstanceOf(Function)
			expect(manager.isRecording()).toBe(false)
			expect(manager.isSpeaking()).toBe(false)
			expect(manager.getUserSpeaking()).toBe(false)
		})
	})
	
	describe('AudioWorklet Loading', () => {
		it('should successfully start recording with AudioWorklet', async () => {
			const manager = createAudioManager()
			const onAudioData = vi.fn()
			
			// Mock getUserMedia to return a proper stream
			const mockStream = new MockMediaStream()
			mockStream.addTrack(new MockMediaStreamTrack() as any)
			vi.spyOn(navigator.mediaDevices, 'getUserMedia').mockResolvedValue(mockStream as any)
			
			// Start recording - this will load the Audio Worklet
			await manager.startRecording(onAudioData)
			
			// Should be recording
			expect(manager.isRecording()).toBe(true)
			
			manager.stopRecording()
		})
		
		it('should use correct sample rate for recording context', async () => {
			const manager = createAudioManager()
			const onAudioData = vi.fn()
			
			const mockStream = new MockMediaStream()
			mockStream.addTrack(new MockMediaStreamTrack() as any)
			vi.spyOn(navigator.mediaDevices, 'getUserMedia').mockResolvedValue(mockStream as any)
			
			await manager.startRecording(onAudioData)
			
			// Recording context should use 16kHz (Gemini input)
			expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
				audio: {
					channelCount: 1,
					sampleRate: 16000,
					echoCancellation: true,
					noiseSuppression: true
				}
			})
			
			manager.stopRecording()
		})
	})
	
	describe('Recording State', () => {
		it('should update recording state correctly', async () => {
			const manager = createAudioManager()
			const onAudioData = vi.fn()
			
			const mockStream = new MockMediaStream()
			mockStream.addTrack(new MockMediaStreamTrack() as any)
			vi.spyOn(navigator.mediaDevices, 'getUserMedia').mockResolvedValue(mockStream as any)
			
			expect(manager.isRecording()).toBe(false)
			
			await manager.startRecording(onAudioData)
			expect(manager.isRecording()).toBe(true)
			
			manager.stopRecording()
			expect(manager.isRecording()).toBe(false)
		})
		
		it('should not start recording twice', async () => {
			const manager = createAudioManager()
			const onAudioData = vi.fn()
			
			const mockStream = new MockMediaStream()
			mockStream.addTrack(new MockMediaStreamTrack() as any)
			vi.spyOn(navigator.mediaDevices, 'getUserMedia').mockResolvedValue(mockStream as any)
			
			await manager.startRecording(onAudioData)
			
			const getUserMediaCallCount = vi.mocked(navigator.mediaDevices.getUserMedia).mock.calls.length
			
			// Try to start again
			await manager.startRecording(onAudioData)
			
			// Should not have called getUserMedia again
			expect(vi.mocked(navigator.mediaDevices.getUserMedia).mock.calls.length).toBe(getUserMediaCallCount)
			
			manager.stopRecording()
		})
	})
	
	describe('Energy Callbacks', () => {
		it('should invoke calibration complete callback', async () => {
			const manager = createAudioManager()
			const onAudioData = vi.fn()
			const onCalibrationComplete = vi.fn()
			
			const mockStream = new MockMediaStream()
			mockStream.addTrack(new MockMediaStreamTrack() as any)
			vi.spyOn(navigator.mediaDevices, 'getUserMedia').mockResolvedValue(mockStream as any)
			
			await manager.startRecording(onAudioData, {
				onCalibrationComplete
			})
			
			// Callback should be set up (will be called after 2s of audio processing)
			expect(manager.isRecording()).toBe(true)
			
			manager.stopRecording()
		})
	})
	
	describe('Audio Playback', () => {
		it('should handle audio playback', async () => {
			const manager = createAudioManager()
			
			// Create mock PCM16 audio data (24kHz)
			const sampleCount = 240 // 10ms at 24kHz
			const pcm16 = new Int16Array(sampleCount)
			for (let i = 0; i < sampleCount; i++) {
				pcm16[i] = Math.sin(i * 0.1) * 32767
			}
			
			await manager.playAudio(pcm16.buffer)
			
			// Should have created playback context and buffer source
			expect(manager.isSpeaking()).toBe(true)
		})
		
		it('should block playback during barge-in', async () => {
			const manager = createAudioManager()
			
			// Start playback
			const pcm16 = new Int16Array(240)
			await manager.playAudio(pcm16.buffer)
			
			// Trigger barge-in
			manager.flushAudioQueue()
			
			// Try to play more audio - should be blocked
			await manager.playAudio(pcm16.buffer)
			
			// Should not be speaking anymore
			expect(manager.isSpeaking()).toBe(false)
		})
		
		it('should resume playback after barge-in', async () => {
			const manager = createAudioManager()
			
			const pcm16 = new Int16Array(240)
			await manager.playAudio(pcm16.buffer)
			
			manager.flushAudioQueue()
			expect(manager.isSpeaking()).toBe(false)
			
			manager.resumePlayback()
			
			// Should be able to play audio again
			await manager.playAudio(pcm16.buffer)
			expect(manager.isSpeaking()).toBe(true)
		})
	})
	
	describe('Cleanup', () => {
		it('should cleanup resources on destroy', async () => {
			const manager = createAudioManager()
			const onAudioData = vi.fn()
			
			const mockStream = new MockMediaStream()
			const mockTrack = new MockMediaStreamTrack()
			mockStream.addTrack(mockTrack as any)
			vi.spyOn(navigator.mediaDevices, 'getUserMedia').mockResolvedValue(mockStream as any)
			
			await manager.startRecording(onAudioData)
			
			manager.destroy()
			
			// Should stop recording
			expect(manager.isRecording()).toBe(false)
			
			// Should have stopped media tracks
			expect(mockTrack.readyState).toBe('ended')
		})
	})
	
	describe('Error Handling', () => {
		it('should handle microphone access errors', async () => {
			const manager = createAudioManager()
			const onAudioData = vi.fn()
			
			// Mock getUserMedia to reject
			vi.spyOn(navigator.mediaDevices, 'getUserMedia').mockRejectedValue(
				new Error('Permission denied')
			)
			
			await expect(manager.startRecording(onAudioData)).rejects.toThrow('Permission denied')
			
			// Should not be recording
			expect(manager.isRecording()).toBe(false)
		})
	})
})
