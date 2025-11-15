/**
 * Conversation Transcript Component
 *
 * Displays conversation history with RTL language support.
 * Supports: Arabic (ar-SA), Hebrew (he-IL), Persian (fa-IR), Urdu (ur-PK)
 *
 * Features:
 * - Collapsible panel
 * - Auto-scroll to latest message
 * - Copy transcript functionality
 * - Clear conversation
 * - Language indicators per message
 * - Mobile responsive
 * - WCAG 2.1 accessible
 */

import { useEffect, useRef, useState } from "react"
import {
	loadConversationHistory,
	clearConversationHistory,
	getLanguageDisplayName,
	type LanguageCode
} from "../shared/halfCascadeTypes"
import "./ConversationTranscript.css"

export interface ConversationMessage {
	role: "user" | "assistant"
	content: string
	language?: string
	timestamp: number
}

interface ConversationTranscriptProps {
	isOpen?: boolean
	onToggle?: (isOpen: boolean) => void
	currentLanguage?: string
	className?: string
}

/**
 * Check if a language code requires RTL rendering
 */
function isRTLLanguage(languageCode: string | undefined): boolean {
	if (!languageCode) return false
	const rtlLanguages = ["ar-SA", "he-IL", "fa-IR", "ur-PK"]
	return rtlLanguages.includes(languageCode)
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp: number): string {
	const date = new Date(timestamp)
	const hours = date.getHours().toString().padStart(2, "0")
	const minutes = date.getMinutes().toString().padStart(2, "0")
	return `${hours}:${minutes}`
}

/**
 * Copy transcript to clipboard
 */
async function copyTranscriptToClipboard(messages: ConversationMessage[]): Promise<boolean> {
	try {
		const text = messages
			.map((msg) => {
				const speaker = msg.role === "user" ? "You" : "Assistant"
				const time = formatTimestamp(msg.timestamp)
				return `[${time}] ${speaker}: ${msg.content}`
			})
			.join("\n\n")

		await navigator.clipboard.writeText(text)
		return true
	} catch (error) {
		console.error("[ConversationTranscript] Failed to copy:", error)
		return false
	}
}

export function ConversationTranscript({
	isOpen: controlledIsOpen,
	onToggle,
	currentLanguage,
	className = ""
}: ConversationTranscriptProps) {
	// State
	const [internalIsOpen, setInternalIsOpen] = useState(false)
	const [messages, setMessages] = useState<ConversationMessage[]>([])
	const [copySuccess, setCopySuccess] = useState(false)
	const messagesEndRef = useRef<HTMLDivElement>(null)
	const scrollContainerRef = useRef<HTMLDivElement>(null)

	// Use controlled or uncontrolled state
	const isOpen = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen

	/**
	 * Load conversation history from sessionStorage
	 */
	function loadMessages() {
		const history = loadConversationHistory()
		const messagesWithTimestamps: ConversationMessage[] = history.map((entry, index) => ({
			role: entry.role as "user" | "assistant",
			content: entry.content,
			language: currentLanguage,  // Use current language as default
			timestamp: Date.now() - (history.length - index) * 1000  // Approximate timestamps
		}))
		setMessages(messagesWithTimestamps)
	}

	/**
	 * Clear all conversation history
	 */
	function handleClear() {
		if (confirm("Clear all conversation history? This cannot be undone.")) {
			clearConversationHistory()
			setMessages([])
		}
	}

	/**
	 * Copy transcript to clipboard
	 */
	async function handleCopy() {
		const success = await copyTranscriptToClipboard(messages)
		if (success) {
			setCopySuccess(true)
			setTimeout(() => setCopySuccess(false), 2000)
		}
	}

	/**
	 * Toggle panel open/closed
	 */
	function handleToggle() {
		const newState = !isOpen
		if (controlledIsOpen === undefined) {
			setInternalIsOpen(newState)
		}
		onToggle?.(newState)
	}

	/**
	 * Auto-scroll to bottom on new messages
	 */
	useEffect(() => {
		if (isOpen && messagesEndRef.current) {
			messagesEndRef.current.scrollIntoView({ behavior: "smooth" })
		}
	}, [messages, isOpen])

	/**
	 * Load messages on mount and when conversation updates
	 */
	useEffect(() => {
		loadMessages()

		// Set up interval to poll for new messages (every 2 seconds)
		const interval = setInterval(loadMessages, 2000)
		return () => clearInterval(interval)
	}, [currentLanguage])

	/**
	 * Keyboard accessibility
	 */
	function handleKeyDown(event: React.KeyboardEvent) {
		if (event.key === "Enter" || event.key === " ") {
			event.preventDefault()
			handleToggle()
		}
	}

	return (
		<div className={`conversation-transcript ${className}`}>
			{/* Toggle Button */}
			<button
				type="button"
				className="transcript-toggle"
				onClick={handleToggle}
				onKeyDown={handleKeyDown}
				aria-expanded={isOpen}
				aria-controls="transcript-panel"
				aria-label={isOpen ? "Hide conversation transcript" : "Show conversation transcript"}
			>
				<span className="toggle-icon">{isOpen ? "▼" : "▶"}</span>
				<span className="toggle-label">Transcript</span>
				{messages.length > 0 && (
					<span className="message-count" aria-label={`${messages.length} messages`}>
						({messages.length})
					</span>
				)}
			</button>

			{/* Transcript Panel */}
			{isOpen && (
				<div
					id="transcript-panel"
					className="transcript-panel"
					role="region"
					aria-label="Conversation transcript"
				>
					{/* Toolbar */}
					<div className="transcript-toolbar">
						<button
							type="button"
							className="toolbar-button copy-button"
							onClick={handleCopy}
							disabled={messages.length === 0}
							aria-label="Copy transcript to clipboard"
							title="Copy transcript"
						>
							📋 {copySuccess ? "Copied!" : "Copy"}
						</button>
						<button
							type="button"
							className="toolbar-button clear-button"
							onClick={handleClear}
							disabled={messages.length === 0}
							aria-label="Clear all conversation history"
							title="Clear transcript"
						>
							🗑️ Clear
						</button>
					</div>

					{/* Messages Container */}
					<div
						ref={scrollContainerRef}
						className="messages-container"
						role="log"
						aria-live="polite"
						aria-atomic="false"
					>
						{messages.length === 0 ? (
							<div className="empty-state" role="status">
								<p>No conversation history yet.</p>
								<p className="hint">Start speaking to see your conversation here.</p>
							</div>
						) : (
							messages.map((message, index) => {
								const isRTL = isRTLLanguage(message.language)
								const languageLabel = message.language
									? getLanguageDisplayName(message.language)
									: undefined

								return (
									<div
										key={index}
										className={`message message-${message.role}`}
										data-lang={message.language}
										dir={isRTL ? "rtl" : "ltr"}
										role="article"
										aria-label={`${message.role === "user" ? "You" : "Assistant"} message`}
									>
										<div className="message-header">
											<span className="message-speaker">
												{message.role === "user" ? "You" : "Assistant"}
											</span>
											{languageLabel && (
												<span className="message-language" aria-label={`Language: ${languageLabel}`}>
													{languageLabel}
												</span>
											)}
											<span className="message-time" aria-label={`Time: ${formatTimestamp(message.timestamp)}`}>
												{formatTimestamp(message.timestamp)}
											</span>
										</div>
										<div className="message-content">
											{message.content}
										</div>
									</div>
								)
							})
						)}
						<div ref={messagesEndRef} aria-hidden="true" />
					</div>
				</div>
			)}
		</div>
	)
}

export default ConversationTranscript
