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

    async def ask(self, query: str, context: dict) -> tuple[str, list[dict]]:
        """Send a prose query + current-values context to the secretary agent.
        Returns (answer, sources): `answer` is the secretary's prose answer as a
        plain string; `sources` is the resolved list of {"field_id", "spoken_name"}
        dicts the answer was grounded in (bd polyglot-pdf-2af7/3vby), letting the
        caller hand an EXACT field id to switch_to_field. Fail-open: on error
        returns ("", []) so the Live model can ask the user directly.
        Non-abstract default raises NotImplementedError so implementations that
        have not yet built the secretary bead fail loudly rather than silently.
        Implementation added in the A-pillar secretary bead (polyglot-pdf-jnjj.*)."""
        raise NotImplementedError(
            "ask() is not implemented until the A-pillar secretary bead lands."
        )
