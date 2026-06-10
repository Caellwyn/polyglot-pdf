from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Protocol


class LiveAISession(Protocol):
    """Defines the contract for a live AI session object."""

    async def send_audio(self, pcm16_16k: bytes) -> None:
        ...

    async def send_tool_response(self, responses: List[Dict[str, Any]]) -> None:
        ...


class ILiveAI(ABC):
    """Port for a live, streaming AI session with audio and tool-calling capabilities."""

    @abstractmethod
    def connect(
        self, model: str, config: Dict[str, Any]
    ) -> AsyncIterator[LiveAISession]:
        """
        An async context manager that connects to the live AI service and yields a session.
        """
        ...

    # The following methods describe higher-level lifecycle and control used by
    # the form filling service. They are optional for lightweight unit tests,
    # but concrete adapters should implement them when providing a live audio
    # streaming capability.

    def set_callbacks(
        self,
        on_form_update=None,
        on_transcript=None,
        on_audio=None,
        on_tool_call=None,
        system_instruction: str | None = None,
        tool_declarations: list[dict] | None = None,
        enable_transcripts: bool = False,
    ):
        """Register coroutine callbacks used by the service.

        on_form_update: async callable taking a dict payload
        on_transcript: async callable taking a string transcript
        on_audio: async callable taking raw audio bytes
        on_tool_call: async callable taking (tool_name: str, arguments: dict)
        system_instruction: optional system prompt to send in session config
        tool_declarations: optional list of function declaration dicts (each with name/parameters)
        """
        raise NotImplementedError()

    async def stream_audio(self, audio_chunk: bytes):
        """Send a raw PCM16 16k audio chunk to the live AI pipeline."""
        raise NotImplementedError()

    async def send_text_message(self, text: str):
        """Send a text message to the live AI session (e.g., context hints, next field info)."""
        raise NotImplementedError()

    async def send_activity_start(self):
        """Send activity_start signal to Gemini (user started speaking)."""
        raise NotImplementedError()

    async def send_activity_end(self):
        """Send activity_end signal to Gemini (user stopped speaking)."""
        raise NotImplementedError()

    def begin_graceful_shutdown(self):
        """Request a cooperative receive-loop shutdown AFTER flushing pending tool
        responses, returning an awaitable Event set when the loop has fully exited.

        Synchronous + lock-free so it is safe to call from a tool callback running
        ON the receive task (e.g. switch_section), where awaiting finalize() would
        self-cancel that task and orphan the FunctionResponse it is mid-send
        (bd polyglot-pdf-0c1 / y4a). Concrete audio adapters implement this; a
        caller awaits the returned Event before starting the replacement session.
        """
        raise NotImplementedError()

    async def finalize(self):
        """Cleanly stop any background tasks and close underlying sessions."""
        raise NotImplementedError()
