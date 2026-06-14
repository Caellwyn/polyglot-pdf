/**
 * Metrics Tracker for VAD Tuning & Barge-In Performance
 * 
 * Tracks:
 * - Barge-in latency (mic activity -> TTS paused)
 * - Interruption ack latency (cancel sent -> Gemini confirms)
 * - Tool call cancellations (successful vs hallucinated)
 * - VAD false starts
 * 
 * NO PII - Only timing and operational metrics
 */

import { isDebugMetricsEnabled } from './config'

export interface BargeInMetric {
	timestamp: number
	micActivityDetected: number // performance.now()
	ttsPausedAt?: number
	cancelSentAt?: number
	geminiAckAt?: number
	bargeInLatency?: number // micActivityDetected → ttsPausedAt
	cancelAckLatency?: number // cancelSentAt → geminiAckAt
	result: 'pending' | 'success' | 'timeout' | 'false_start'
}

export interface ToolCallMetric {
	timestamp: number
	toolName: string
	callId: string
	receivedAt: number // performance.now()
	bargeInWindowActive: boolean // Was this within 150ms of barge-in?
	decision: 'accepted' | 'rejected_barge_in' | 'rejected_invalid'
	rejectionReason?: string
}

export interface SessionMetrics {
	sessionId: string
	sessionStart: number
	bargeIns: BargeInMetric[]
	toolCalls: ToolCallMetric[]
	falseStarts: number
	successfulBargeIns: number
	timedOutBargeIns: number
	hallucinatedToolCalls: number // Tool calls rejected due to barge-in
}

class MetricsTracker {
	private sessionMetrics: SessionMetrics | null = null
	private currentBargeIn: BargeInMetric | null = null
	private lastBargeInTime: number = 0
	private readonly BARGE_IN_GRACE_PERIOD_MS = 150
	private debugEnabled: boolean = false

	/**
	 * Start a new session
	 */
	startSession(sessionId: string): void {
		this.debugEnabled = isDebugMetricsEnabled()
		this.sessionMetrics = {
			sessionId,
			sessionStart: Date.now(),
			bargeIns: [],
			toolCalls: [],
			falseStarts: 0,
			successfulBargeIns: 0,
			timedOutBargeIns: 0,
			hallucinatedToolCalls: 0,
		}
		this.currentBargeIn = null
		this.lastBargeInTime = 0
		
		if (this.debugEnabled) {
			console.log('[VFF Metrics] [chart] Session started:', sessionId, '(Debug mode: ON)')
		}
	}

	/**
	 * Record microphone activity detected (potential barge-in)
	 */
	recordMicActivity(): void {
		if (!this.sessionMetrics) return

		const now = performance.now()
		
		this.currentBargeIn = {
			timestamp: Date.now(),
			micActivityDetected: now,
			result: 'pending',
		}

		console.log('[VFF Metrics] [mic] Mic activity detected')
	}

	/**
	 * Record TTS playback paused
	 */
	recordTTSPaused(): void {
		if (!this.sessionMetrics || !this.currentBargeIn) return

		const now = performance.now()
		this.currentBargeIn.ttsPausedAt = now
		this.currentBargeIn.bargeInLatency = now - this.currentBargeIn.micActivityDetected

		console.log(
			`[VFF Metrics] 🔇 TTS paused - Barge-in latency: ${this.currentBargeIn.bargeInLatency.toFixed(1)}ms`,
			this.currentBargeIn.bargeInLatency < 180 ? '✅' : '⚠️ SLOW'
		)
	}

	/**
	 * Record cancel_generation message sent
	 */
	recordCancelSent(): void {
		if (!this.sessionMetrics || !this.currentBargeIn) return

		const now = performance.now()
		this.currentBargeIn.cancelSentAt = now

		console.log('[VFF Metrics] [send] Cancel message sent to backend')
	}

	/**
	 * Record Gemini interruption acknowledgment received
	 */
	recordGeminiAck(): void {
		if (!this.sessionMetrics || !this.currentBargeIn) return

		const now = performance.now()
		this.currentBargeIn.geminiAckAt = now

		if (this.currentBargeIn.cancelSentAt) {
			this.currentBargeIn.cancelAckLatency = now - this.currentBargeIn.cancelSentAt
			console.log(
				`[VFF Metrics] ✅ Gemini acknowledged - Cancel latency: ${this.currentBargeIn.cancelAckLatency.toFixed(1)}ms`,
				this.currentBargeIn.cancelAckLatency < 150 ? '✅' : '⚠️ SLOW'
			)
		}

		this.currentBargeIn.result = 'success'
		this.sessionMetrics.successfulBargeIns++
		this.lastBargeInTime = now
		this.sessionMetrics.bargeIns.push(this.currentBargeIn)
		this.currentBargeIn = null
	}

	/**
	 * Record barge-in timeout (Gemini didn't acknowledge within threshold)
	 */
	recordBargeInTimeout(): void {
		if (!this.sessionMetrics || !this.currentBargeIn) return

		console.warn('[VFF Metrics] [timer] Barge-in timeout - Gemini did not acknowledge')

		this.currentBargeIn.result = 'timeout'
		this.sessionMetrics.timedOutBargeIns++
		this.sessionMetrics.bargeIns.push(this.currentBargeIn)
		this.currentBargeIn = null
	}

	/**
	 * Record false start (user stopped talking before TTS paused)
	 */
	recordFalseStart(): void {
		if (!this.sessionMetrics || !this.currentBargeIn) return

		console.log('[VFF Metrics] [reconnect] False start detected')

		this.currentBargeIn.result = 'false_start'
		this.sessionMetrics.falseStarts++
		this.sessionMetrics.bargeIns.push(this.currentBargeIn)
		this.currentBargeIn = null
	}

	/**
	 * Check for false start condition: Gemini speaking while user mic is active
	 * Should be called whenever energy state changes
	 * @returns true if false start detected (Gemini interrupted user)
	 */
	checkFalseStart(userSpeaking: boolean, geminiSpeaking: boolean): boolean {
		// False start: Gemini starts speaking while user is mid-utterance
		if (geminiSpeaking && userSpeaking) {
			console.warn('[VFF Metrics] [warn] FALSE START: Gemini speaking while user mic active!')
			this.recordFalseStart()
			return true
		}
		return false
	}

	/**
	 * Record tool call received
	 */
	recordToolCall(toolName: string, callId: string): 'accept' | 'reject' {
		if (!this.sessionMetrics) return 'accept'

		const now = performance.now()
		const timeSinceBargeIn = now - this.lastBargeInTime
		const bargeInWindowActive = timeSinceBargeIn < this.BARGE_IN_GRACE_PERIOD_MS

		const metric: ToolCallMetric = {
			timestamp: Date.now(),
			toolName,
			callId,
			receivedAt: now,
			bargeInWindowActive,
			decision: 'accepted',
		}

		// Reject tool calls within grace period of barge-in
		if (bargeInWindowActive) {
			metric.decision = 'rejected_barge_in'
			metric.rejectionReason = `Received ${timeSinceBargeIn.toFixed(1)}ms after barge-in (< ${this.BARGE_IN_GRACE_PERIOD_MS}ms threshold)`
			this.sessionMetrics.hallucinatedToolCalls++
			this.sessionMetrics.toolCalls.push(metric)

			console.warn(
				`[VFF Metrics] 🚫 Tool call REJECTED (hallucination):`,
				`${toolName} [${callId.slice(0, 8)}]`,
				`- ${metric.rejectionReason}`
			)
			return 'reject'
		}

		this.sessionMetrics.toolCalls.push(metric)
		console.log(
			`[VFF Metrics] ✅ Tool call ACCEPTED:`,
			`${toolName} [${callId.slice(0, 8)}]`,
			`- ${timeSinceBargeIn.toFixed(0)}ms after last barge-in`
		)
		return 'accept'
	}

	/**
	 * Get current session statistics
	 */
	getStats(): {
		totalBargeIns: number
		successfulBargeIns: number
		timedOutBargeIns: number
		falseStarts: number
		avgBargeInLatency: number
		p95BargeInLatency: number
		avgCancelAckLatency: number
		p95CancelAckLatency: number
		totalToolCalls: number
		hallucinatedToolCalls: number
		toolCallHallucinationRate: number
		falseStartRate: number
	} | null {
		if (!this.sessionMetrics) return null

		const bargeIns = this.sessionMetrics.bargeIns
		const bargeInLatencies = bargeIns
			.filter(b => b.bargeInLatency !== undefined)
			.map(b => b.bargeInLatency!)
		const cancelAckLatencies = bargeIns
			.filter(b => b.cancelAckLatency !== undefined)
			.map(b => b.cancelAckLatency!)

		const avg = (arr: number[]) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
		const p95 = (arr: number[]) => {
			if (!arr.length) return 0
			const sorted = [...arr].sort((a, b) => a - b)
			const idx = Math.floor(sorted.length * 0.95)
			return sorted[idx]
		}

		const totalBargeIns = bargeIns.length
		const totalToolCalls = this.sessionMetrics.toolCalls.length

		return {
			totalBargeIns,
			successfulBargeIns: this.sessionMetrics.successfulBargeIns,
			timedOutBargeIns: this.sessionMetrics.timedOutBargeIns,
			falseStarts: this.sessionMetrics.falseStarts,
			avgBargeInLatency: avg(bargeInLatencies),
			p95BargeInLatency: p95(bargeInLatencies),
			avgCancelAckLatency: avg(cancelAckLatencies),
			p95CancelAckLatency: p95(cancelAckLatencies),
			totalToolCalls,
			hallucinatedToolCalls: this.sessionMetrics.hallucinatedToolCalls,
			toolCallHallucinationRate: totalToolCalls ? (this.sessionMetrics.hallucinatedToolCalls / totalToolCalls) * 100 : 0,
			falseStartRate: totalBargeIns ? (this.sessionMetrics.falseStarts / totalBargeIns) * 100 : 0,
		}
	}

	/**
	 * Print session summary
	 */
	printSummary(): void {
		const stats = this.getStats()
		if (!stats) {
			console.log('[VFF Metrics] No session data')
			return
		}

		console.log('\n' + '='.repeat(60))
		console.log('[chart] VAD TUNING METRICS SUMMARY')
		console.log('='.repeat(60))
		console.log('\n[mic] BARGE-IN PERFORMANCE:')
		console.log(`   Total Barge-Ins: ${stats.totalBargeIns}`)
		console.log(`   Successful: ${stats.successfulBargeIns} (${(stats.successfulBargeIns / stats.totalBargeIns * 100).toFixed(1)}%)`)
		console.log(`   Timeouts: ${stats.timedOutBargeIns}`)
		console.log(`   False Starts: ${stats.falseStarts} (${stats.falseStartRate.toFixed(1)}%)`)
		console.log(`   Avg Latency: ${stats.avgBargeInLatency.toFixed(1)}ms ${stats.avgBargeInLatency < 180 ? '[OK]' : '[warn]'}`)
		console.log(`   P95 Latency: ${stats.p95BargeInLatency.toFixed(1)}ms ${stats.p95BargeInLatency < 180 ? '[OK] TARGET MET' : '[X] EXCEEDS TARGET'}`)

		console.log('\n[reconnect] CANCEL ACKNOWLEDGMENT:')
		console.log(`   Avg Latency: ${stats.avgCancelAckLatency.toFixed(1)}ms ${stats.avgCancelAckLatency < 150 ? '[OK]' : '[warn]'}`)
		console.log(`   P95 Latency: ${stats.p95CancelAckLatency.toFixed(1)}ms ${stats.p95CancelAckLatency < 150 ? '[OK] TARGET MET' : '[X] EXCEEDS TARGET'}`)

		console.log('\n[tools] TOOL CALL SAFETY:')
		console.log(`   Total Tool Calls: ${stats.totalToolCalls}`)
		console.log(`   Hallucinated (rejected): ${stats.hallucinatedToolCalls}`)
		console.log(`   Hallucination Rate: ${stats.toolCallHallucinationRate.toFixed(1)}% ${stats.toolCallHallucinationRate < 1 ? '[OK] EXCELLENT' : stats.toolCallHallucinationRate < 5 ? '[warn] ACCEPTABLE' : '[X] TOO HIGH'}`)

		console.log('\n' + '='.repeat(60) + '\n')
	}

	/**
	 * End session and print summary
	 */
	endSession(): void {
		if (!this.sessionMetrics) return

		console.log('[VFF Metrics] [chart] Session ended:', this.sessionMetrics.sessionId)
		this.printSummary()
		this.sessionMetrics = null
		this.currentBargeIn = null
		this.lastBargeInTime = 0
	}

	/**
	 * Export raw metrics data (for offline analysis)
	 */
	exportData(): SessionMetrics | null {
		return this.sessionMetrics ? { ...this.sessionMetrics } : null
	}
}

// Singleton instance
export const metrics = new MetricsTracker()

// Expose metrics API globally for testing UI
if (typeof window !== 'undefined') {
	(window as any).__VFF_METRICS__ = metrics
}
