/**
 * Conversation Transcript Component - Unit Tests
 *
 * Tests for RTL support, accessibility, and functionality
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { ConversationTranscript } from "./ConversationTranscript"
import {
	saveConversationHistory,
	clearConversationHistory
} from "../shared/halfCascadeTypes"

// Mock clipboard API
Object.assign(navigator, {
	clipboard: {
		writeText: vi.fn(() => Promise.resolve())
	}
})

// Mock window.confirm
global.confirm = vi.fn(() => true)

describe("ConversationTranscript", () => {
	beforeEach(() => {
		// Clear sessionStorage before each test
		sessionStorage.clear()
		vi.clearAllMocks()
	})

	afterEach(() => {
		clearConversationHistory()
	})

	describe("Rendering", () => {
		it("renders toggle button with correct label", () => {
			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button", { name: /show conversation transcript/i })
			expect(toggle).toBeInTheDocument()
			expect(screen.getByText("Transcript")).toBeInTheDocument()
		})

		it("renders with custom className", () => {
			const { container } = render(<ConversationTranscript className="custom-class" />)
			expect(container.firstChild).toHaveClass("conversation-transcript", "custom-class")
		})

		it("displays message count when messages exist", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" },
				{ role: "assistant", content: "Hi there!" }
			])

			render(<ConversationTranscript />)

			expect(screen.getByText("(2)")).toBeInTheDocument()
		})

		it("does not display count when no messages", () => {
			render(<ConversationTranscript />)

			expect(screen.queryByText(/\(\d+\)/)).not.toBeInTheDocument()
		})
	})

	describe("Toggle Functionality", () => {
		it("starts collapsed by default", () => {
			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button", { name: /show/i })
			expect(toggle).toHaveAttribute("aria-expanded", "false")
			expect(screen.queryByRole("region", { name: /conversation transcript/i })).not.toBeInTheDocument()
		})

		it("expands when toggle clicked", async () => {
			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button", { name: /show/i })
			fireEvent.click(toggle)

			await waitFor(() => {
				expect(toggle).toHaveAttribute("aria-expanded", "true")
				expect(screen.getByRole("region", { name: /conversation transcript/i })).toBeInTheDocument()
			})
		})

		it("collapses when clicked again", async () => {
			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button", { name: /show/i })

			// Open
			fireEvent.click(toggle)
			await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "true"))

			// Close
			fireEvent.click(toggle)
			await waitFor(() => {
				expect(toggle).toHaveAttribute("aria-expanded", "false")
			})
		})

		it("supports controlled mode", async () => {
			const onToggle = vi.fn()
			const { rerender } = render(
				<ConversationTranscript isOpen={false} onToggle={onToggle} />
			)

			const toggle = screen.getByRole("button")
			fireEvent.click(toggle)

			expect(onToggle).toHaveBeenCalledWith(true)

			// Simulate parent updating prop
			rerender(<ConversationTranscript isOpen={true} onToggle={onToggle} />)

			expect(screen.getByRole("region", { name: /conversation transcript/i })).toBeInTheDocument()
		})

		it("supports keyboard navigation (Enter key)", async () => {
			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button", { name: /show/i })
			fireEvent.keyDown(toggle, { key: "Enter" })

			await waitFor(() => {
				expect(toggle).toHaveAttribute("aria-expanded", "true")
			})
		})

		it("supports keyboard navigation (Space key)", async () => {
			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button", { name: /show/i })
			fireEvent.keyDown(toggle, { key: " " })

			await waitFor(() => {
				expect(toggle).toHaveAttribute("aria-expanded", "true")
			})
		})
	})

	describe("Message Display", () => {
		it("displays empty state when no messages", () => {
			render(<ConversationTranscript isOpen={true} />)

			expect(screen.getByText("No conversation history yet.")).toBeInTheDocument()
			expect(screen.getByText(/start speaking/i)).toBeInTheDocument()
		})

		it("displays user messages correctly", () => {
			saveConversationHistory([
				{ role: "user", content: "What is your name?" }
			])

			render(<ConversationTranscript isOpen={true} />)

			expect(screen.getByText("You")).toBeInTheDocument()
			expect(screen.getByText("What is your name?")).toBeInTheDocument()
		})

		it("displays assistant messages correctly", () => {
			saveConversationHistory([
				{ role: "assistant", content: "I am a voice assistant." }
			])

			render(<ConversationTranscript isOpen={true} />)

			expect(screen.getByText("Assistant")).toBeInTheDocument()
			expect(screen.getByText("I am a voice assistant.")).toBeInTheDocument()
		})

		it("displays multiple messages in order", () => {
			saveConversationHistory([
				{ role: "user", content: "Message 1" },
				{ role: "assistant", content: "Message 2" },
				{ role: "user", content: "Message 3" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const messages = screen.getAllByRole("article")
			expect(messages).toHaveLength(3)
			expect(messages[0]).toHaveTextContent("Message 1")
			expect(messages[1]).toHaveTextContent("Message 2")
			expect(messages[2]).toHaveTextContent("Message 3")
		})

		it("displays language labels when provided", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} currentLanguage="es-ES" />)

			expect(screen.getByText("Spanish (Spain)")).toBeInTheDocument()
		})

		it("displays timestamps for messages", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} />)

			// Timestamp format: HH:MM
			const timeElement = screen.getByText(/\d{2}:\d{2}/)
			expect(timeElement).toBeInTheDocument()
		})
	})

	describe("RTL Language Support", () => {
		const rtlLanguages = [
			{ code: "ar-SA", name: "Arabic" },
			{ code: "he-IL", name: "Hebrew" },
			{ code: "fa-IR", name: "Persian" },
			{ code: "ur-PK", name: "Urdu" }
		]

		rtlLanguages.forEach(({ code, name }) => {
			it(`applies RTL direction for ${name} (${code})`, () => {
				saveConversationHistory([
					{ role: "user", content: "مرحبا" }  // "Hello" in Arabic
				])

				const { container } = render(
					<ConversationTranscript isOpen={true} currentLanguage={code} />
				)

				const message = container.querySelector(`[data-lang="${code}"]`)
				expect(message).toHaveAttribute("dir", "rtl")
			})
		})

		it("applies LTR direction for English", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			const { container } = render(
				<ConversationTranscript isOpen={true} currentLanguage="en-US" />
			)

			const message = container.querySelector('[data-lang="en-US"]')
			expect(message).toHaveAttribute("dir", "ltr")
		})

		it("handles mixed RTL/LTR conversations", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" },  // English
				{ role: "assistant", content: "مرحبا" }  // Arabic
			])

			const { container } = render(
				<ConversationTranscript isOpen={true} currentLanguage="en-US" />
			)

			const messages = container.querySelectorAll(".message")
			expect(messages).toHaveLength(2)
			// Both should be LTR since currentLanguage is en-US
			// (In real app, each message would have its own language tag)
		})
	})

	describe("Copy Functionality", () => {
		it("copies transcript to clipboard when copy button clicked", async () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" },
				{ role: "assistant", content: "Hi there!" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const copyButton = screen.getByRole("button", { name: /copy transcript/i })
			fireEvent.click(copyButton)

			await waitFor(() => {
				expect(navigator.clipboard.writeText).toHaveBeenCalled()
			})
		})

		it("shows success message after copy", async () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const copyButton = screen.getByRole("button", { name: /copy transcript/i })
			fireEvent.click(copyButton)

			await waitFor(() => {
				expect(screen.getByText("Copied!")).toBeInTheDocument()
			})

			// Success message should disappear after 2 seconds
			await waitFor(() => {
				expect(screen.queryByText("Copied!")).not.toBeInTheDocument()
			}, { timeout: 3000 })
		})

		it("disables copy button when no messages", () => {
			render(<ConversationTranscript isOpen={true} />)

			const copyButton = screen.getByRole("button", { name: /copy transcript/i })
			expect(copyButton).toBeDisabled()
		})

		it("handles copy errors gracefully", async () => {
			// Mock clipboard to reject
			vi.mocked(navigator.clipboard.writeText).mockRejectedValueOnce(new Error("Copy failed"))

			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const copyButton = screen.getByRole("button", { name: /copy transcript/i })
			fireEvent.click(copyButton)

			// Should not show "Copied!" on error
			await waitFor(() => {
				expect(screen.queryByText("Copied!")).not.toBeInTheDocument()
			})
		})
	})

	describe("Clear Functionality", () => {
		it("clears all messages when clear button clicked", async () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" },
				{ role: "assistant", content: "Hi!" }
			])

			render(<ConversationTranscript isOpen={true} />)

			expect(screen.getAllByRole("article")).toHaveLength(2)

			const clearButton = screen.getByRole("button", { name: /clear all/i })
			fireEvent.click(clearButton)

			await waitFor(() => {
				expect(screen.getByText("No conversation history yet.")).toBeInTheDocument()
				expect(screen.queryAllByRole("article")).toHaveLength(0)
			})
		})

		it("shows confirmation dialog before clearing", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const clearButton = screen.getByRole("button", { name: /clear all/i })
			fireEvent.click(clearButton)

			expect(global.confirm).toHaveBeenCalledWith(
				expect.stringContaining("Clear all conversation history")
			)
		})

		it("does not clear if user cancels confirmation", async () => {
			vi.mocked(global.confirm).mockReturnValueOnce(false)

			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const clearButton = screen.getByRole("button", { name: /clear all/i })
			fireEvent.click(clearButton)

			// Messages should still be there
			expect(screen.getAllByRole("article")).toHaveLength(1)
		})

		it("disables clear button when no messages", () => {
			render(<ConversationTranscript isOpen={true} />)

			const clearButton = screen.getByRole("button", { name: /clear all/i })
			expect(clearButton).toBeDisabled()
		})
	})

	describe("Accessibility", () => {
		it("has proper ARIA attributes on toggle button", () => {
			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button", { name: /show conversation transcript/i })
			expect(toggle).toHaveAttribute("aria-expanded")
			expect(toggle).toHaveAttribute("aria-controls", "transcript-panel")
		})

		it("has proper ARIA role on messages container", () => {
			render(<ConversationTranscript isOpen={true} />)

			const container = screen.getByRole("log")
			expect(container).toHaveAttribute("aria-live", "polite")
			expect(container).toHaveAttribute("aria-atomic", "false")
		})

		it("has proper ARIA labels on toolbar buttons", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} />)

			expect(screen.getByRole("button", { name: /copy transcript to clipboard/i })).toBeInTheDocument()
			expect(screen.getByRole("button", { name: /clear all conversation history/i })).toBeInTheDocument()
		})

		it("each message has article role", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" },
				{ role: "assistant", content: "Hi!" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const messages = screen.getAllByRole("article")
			expect(messages).toHaveLength(2)
			expect(messages[0]).toHaveAttribute("aria-label", expect.stringContaining("You message"))
			expect(messages[1]).toHaveAttribute("aria-label", expect.stringContaining("Assistant message"))
		})

		it("language and time have ARIA labels", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} currentLanguage="en-US" />)

			const languageLabel = screen.getByLabelText(/language: english/i)
			expect(languageLabel).toBeInTheDocument()

			const timeLabel = screen.getByLabelText(/time: \d{2}:\d{2}/i)
			expect(timeLabel).toBeInTheDocument()
		})
	})

	describe("Auto-scroll", () => {
		it("scrolls to bottom when panel opens with messages", async () => {
			saveConversationHistory([
				{ role: "user", content: "Message 1" },
				{ role: "user", content: "Message 2" },
				{ role: "user", content: "Message 3" }
			])

			render(<ConversationTranscript />)

			const toggle = screen.getByRole("button")
			fireEvent.click(toggle)

			await waitFor(() => {
				const container = screen.getByRole("log")
				// Check that scroll position is at or near bottom
				// Note: In JSDOM, scrollIntoView is a no-op, so we just verify it doesn't crash
				expect(container).toBeInTheDocument()
			})
		})
	})

	describe("Message Formatting", () => {
		it("formats timestamps correctly (HH:MM)", () => {
			saveConversationHistory([
				{ role: "user", content: "Hello" }
			])

			render(<ConversationTranscript isOpen={true} />)

			const timeText = screen.getByText(/\d{2}:\d{2}/).textContent
			expect(timeText).toMatch(/^\d{2}:\d{2}$/)
		})

		it("preserves line breaks in message content", () => {
			saveConversationHistory([
				{ role: "user", content: "Line 1\nLine 2\nLine 3" }
			])

			const { container } = render(<ConversationTranscript isOpen={true} />)

			const content = container.querySelector(".message-content")
			expect(content).toHaveTextContent("Line 1\nLine 2\nLine 3")
			expect(content).toHaveStyle({ whiteSpace: "pre-wrap" })
		})
	})
})
