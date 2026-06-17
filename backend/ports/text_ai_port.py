from abc import ABC, abstractmethod


class ITextAI(ABC):
    """Port for cheap text-model calls (contradiction validator + secretary)."""

    @abstractmethod
    async def validate(self, payload: dict) -> dict:
        """Run a contradiction check over the minimal client-state payload
        (contract 2 from docs/standards/validation-delegation.md) and return
        the verdict (contract 1). Fail-open: on timeout/error returns
        {"conflicts": []} so the caller advances unchecked."""
        ...

    @abstractmethod
    async def ask(self, query: str, context: dict) -> str:
        """Send a prose query + current-values context to the secretary agent.
        Returns the secretary's answer as a plain string. Fail-open: on error
        returns "" so the Live model can ask the user directly.
        Implementation added in the A-pillar secretary bead (polyglot-pdf-jnjj.*)."""
        ...
