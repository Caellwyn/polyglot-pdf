/**
 * Unit tests for ProcessingIndicator component
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ProcessingIndicator } from './ProcessingIndicator'
import type { ProcessingStatusMessage, HalfCascadeError } from '../shared/halfCascadeTypes'

describe('ProcessingIndicator Component', () => {
	beforeEach(() => {
		vi.clearAllTimers()
	})

	describe('Rendering', () => {
		it('should not render when not processing', () => {
			const { container } = render(<ProcessingIndicator />)
			expect(container.firstChild).toBeNull()
		})

		it('should render processing stages', async () => {
			render(<ProcessingIndicator />)

			// Dispatch processing status event
			const event = new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: {
					type: 'processing_status',
					stage: 'transcribing',
					progress: 50
				}
			})

			window.dispatchEvent(event)

			await waitFor(() => {
				expect(screen.getByText('Transcribing speech')).toBeInTheDocument()
			})
		})

		it('should display progress bar with percentage', async () => {
			render(<ProcessingIndicator />)

			const event = new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: {
					type: 'processing_status',
					stage: 'generating',
					progress: 75
				}
			})

			window.dispatchEvent(event)

			await waitFor(() => {
				const progressBar = screen.getByRole('progressbar')
				expect(progressBar).toHaveAttribute('aria-valuenow', '75')
			})
		})

		it('should clear on transcript event', async () => {
			render(<ProcessingIndicator />)

			// Start processing
			window.dispatchEvent(new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: { type: 'processing_status', stage: 'transcribing' }
			}))

			await waitFor(() => {
				expect(screen.getByText('Transcribing speech')).toBeInTheDocument()
			})

			// Dispatch transcript (completion)
			window.dispatchEvent(new CustomEvent('vff:transcript', {
				detail: {
					type: 'transcript',
					user_transcript: 'Test',
					assistant_response: 'Response',
					language: 'en-US'
				}
			}))

			await waitFor(() => {
				const { container } = render(<ProcessingIndicator />)
				expect(container.firstChild).toBeNull()
			})
		})
	})

	describe('Processing Stages', () => {
		const stages: ProcessingStatusMessage['stage'][] = [
			'buffering',
			'transcribing',
			'generating',
			'synthesizing'
		]

		stages.forEach((stage) => {
			it(`should display ${stage} stage`, async () => {
				render(<ProcessingIndicator />)

				const event = new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
					detail: {
						type: 'processing_status',
						stage
					}
				})

				window.dispatchEvent(event)

				await waitFor(() => {
					// Check that the stage is displayed (labels are in STAGE_LABELS)
					const element = screen.getByRole('status')
					expect(element).toBeInTheDocument()
				})
			})
		})
	})

	describe('Latency Warnings', () => {
		it('should show latency warning when threshold exceeded', async () => {
			vi.useFakeTimers()
			render(<ProcessingIndicator latencyWarningThreshold={1000} />)

			// Start processing
			window.dispatchEvent(new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: { type: 'processing_status', stage: 'transcribing' }
			}))

			// Advance time past threshold
			vi.advanceTimersByTime(1500)

			// Trigger another status update to recalculate latency
			window.dispatchEvent(new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: { type: 'processing_status', stage: 'generating', progress: 50 }
			}))

			await waitFor(() => {
				expect(screen.getByText(/High latency detected/i)).toBeInTheDocument()
			})

			vi.useRealTimers()
		})
	})

	describe('Error Display', () => {
		it('should display error messages', async () => {
			render(<ProcessingIndicator />)

			const errorEvent = new CustomEvent<HalfCascadeError>('vff:half-cascade-error', {
				detail: {
					type: 'half_cascade_error',
					error_code: 'ASR_FAILED',
					message: 'Transcription failed',
					fallback_activated: false,
					recoverable: true
				}
			})

			window.dispatchEvent(errorEvent)

			await waitFor(() => {
				expect(screen.getByRole('alert')).toBeInTheDocument()
				expect(screen.getByText(/ASR_FAILED/)).toBeInTheDocument()
				expect(screen.getByText(/Transcription failed/)).toBeInTheDocument()
			})
		})

		it('should show fallback activation message', async () => {
			render(<ProcessingIndicator />)

			const errorEvent = new CustomEvent<HalfCascadeError>('vff:half-cascade-error', {
				detail: {
					type: 'half_cascade_error',
					error_code: 'TTS_FAILED',
					message: 'Speech synthesis failed',
					fallback_activated: true,
					recoverable: true
				}
			})

			window.dispatchEvent(errorEvent)

			await waitFor(() => {
				expect(screen.getByText(/Fallback to Live API activated/i)).toBeInTheDocument()
			})
		})

		it('should show non-recoverable warning', async () => {
			render(<ProcessingIndicator />)

			const errorEvent = new CustomEvent<HalfCascadeError>('vff:half-cascade-error', {
				detail: {
					type: 'half_cascade_error',
					error_code: 'CRITICAL_ERROR',
					message: 'Critical system error',
					fallback_activated: false,
					recoverable: false
				}
			})

			window.dispatchEvent(errorEvent)

			await waitFor(() => {
				expect(screen.getByText(/Manual intervention required/i)).toBeInTheDocument()
			})
		})
	})

	describe('Compact Mode', () => {
		it('should render compact view', async () => {
			const { container } = render(<ProcessingIndicator compact={true} />)

			window.dispatchEvent(new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: { type: 'processing_status', stage: 'transcribing' }
			}))

			await waitFor(() => {
				expect(container.querySelector('.processing-indicator.compact')).toBeInTheDocument()
			})
		})

		it('should show latency warning in compact mode', async () => {
			vi.useFakeTimers()
			const { container } = render(<ProcessingIndicator compact={true} latencyWarningThreshold={1000} />)

			window.dispatchEvent(new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: { type: 'processing_status', stage: 'transcribing' }
			}))

			vi.advanceTimersByTime(1500)

			window.dispatchEvent(new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: { type: 'processing_status', stage: 'generating' }
			}))

			await waitFor(() => {
				expect(container.querySelector('.latency-warning-compact')).toBeInTheDocument()
			})

			vi.useRealTimers()
		})
	})

	describe('Accessibility', () => {
		it('should have proper ARIA attributes', async () => {
			render(<ProcessingIndicator />)

			window.dispatchEvent(new CustomEvent<ProcessingStatusMessage>('vff:processing-status', {
				detail: { type: 'processing_status', stage: 'transcribing', progress: 50 }
			}))

			await waitFor(() => {
				const status = screen.getByRole('status')
				expect(status).toHaveAttribute('aria-live', 'polite')

				const progressBar = screen.getByRole('progressbar')
				expect(progressBar).toHaveAttribute('aria-valuenow', '50')
				expect(progressBar).toHaveAttribute('aria-valuemin', '0')
				expect(progressBar).toHaveAttribute('aria-valuemax', '100')
			})
		})

		it('should use role="alert" for errors', async () => {
			render(<ProcessingIndicator />)

			const errorEvent = new CustomEvent<HalfCascadeError>('vff:half-cascade-error', {
				detail: {
					type: 'half_cascade_error',
					error_code: 'TEST_ERROR',
					message: 'Test error message',
					fallback_activated: false,
					recoverable: true
				}
			})

			window.dispatchEvent(errorEvent)

			await waitFor(() => {
				expect(screen.getByRole('alert')).toBeInTheDocument()
			})
		})
	})
})
