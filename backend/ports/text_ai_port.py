from abc import ABC, abstractmethod


class ITextAI(ABC):
    """Port for cheap text-model calls (contradiction validator + secretary)."""

    @abstractmethod
    async def validate(self, payload: dict, session_ctx: dict | None = None) -> dict:
        """Run a contradiction check over the minimal client-state payload
        (contract 2 from docs/standards/validation-delegation.md) and return
        the verdict (contract 1). Fail-open: on timeout/error returns
        {"conflicts": []} so the caller advances unchecked.

        session_ctx (bd polyglot-pdf-t86oz): optional caller session state
        ({firm_id, employee_id, link_jti, kit_id, channel, form_session_id})
        forwarded to the usage_kind="text_validator" event this call emits."""
        ...

    async def ask(
        self, query: str, context: dict, session_ctx: dict | None = None
    ) -> tuple[str, list[dict], bool]:
        """Send a prose query + current-values context to the secretary agent.
        Returns (answer, sources, resolved): `answer` is the secretary's prose
        answer; `sources` is the resolved list of {"field_id", "spoken_name"} dicts
        the answer was grounded in / the fields identified for navigation (bd
        polyglot-pdf-2af7/3vby), letting the caller hand an EXACT field id to
        switch_to_field; `resolved` is False when the secretary deliberately could
        NOT identify a requested navigation target (the semantic-pushback signal,
        bd polyglot-pdf-y76q), True otherwise (incl. on fail-open). Fail-open: on
        error returns ("", [], True) so the Live model can ask the user directly.
        Non-abstract default raises NotImplementedError so implementations that
        have not yet built the secretary bead fail loudly rather than silently.
        Implementation added in the A-pillar secretary bead (polyglot-pdf-jnjj.*)."""
        raise NotImplementedError(
            "ask() is not implemented until the A-pillar secretary bead lands."
        )

    async def translate_labels(
        self,
        labels: list,
        language_name: str,
        language_code: str,
        session_ctx: dict | None = None,
    ) -> dict | None:
        """Batch-translate option labels into the session language (bd
        polyglot-pdf-ow1e, runtime option-label translation). Returns
        {input_label: translated_label} on success (entries may be dropped by
        validation), or None on any error -- None is the fail-open SIGNAL that
        tells the caller not to cache, distinct from a valid empty dict.
        Non-abstract default raises so implementations without the feature
        fail loudly (the option_translation cache layer converts that to a
        fail-open empty result).

        session_ctx (bd polyglot-pdf-t86oz): optional caller session state,
        forwarded to the usage_kind="text_translation" event."""
        raise NotImplementedError(
            "translate_labels() is not implemented by this text-AI adapter."
        )

    async def translate_items(
        self,
        items: list,
        language_name: str,
        language_code: str,
        *,
        form_name: str | None = None,
        glossary_context: dict | None = None,
        session_ctx: dict | None = None,
    ) -> dict | None:
        """Context-carrying batch translation (bd polyglot-pdf-ch7j, the
        translation-gate epic): structured items {id, kind, text | options +
        parent_question}, option sets translated as units, optional
        glossary/register injection. Returns {"items": {id: {"translation":
        str} | {"options": {source: str}}}, "ambiguous": [id, ...]} on
        success, or None on any error (the same do-not-cache fail-open
        SIGNAL as translate_labels). Non-abstract default raises so
        implementations without the feature fail loudly.

        session_ctx (bd polyglot-pdf-t86oz): optional caller session state,
        forwarded to the usage_kind="text_translation" event."""
        raise NotImplementedError(
            "translate_items() is not implemented by this text-AI adapter."
        )

    async def back_translate(
        self, items: dict, language_name: str, language_code: str
    ) -> dict | None:
        """Independent literal back-translation for the verify loop (bd
        polyglot-pdf-9ikj): {id: foreign_string} in, {id: english} out, or
        None on any error (the do-not-trust fail-open signal). Runs on the
        LITE tier for independence from the pro forward/judge path.
        Non-abstract default raises so implementations without the feature
        fail loudly."""
        raise NotImplementedError(
            "back_translate() is not implemented by this text-AI adapter."
        )

    async def judge_translations(
        self,
        items: list,
        language_name: str,
        language_code: str,
        *,
        glossary_context: dict | None = None,
    ) -> dict | None:
        """Bilingual drift judge for the verify loop (bd polyglot-pdf-9ikj):
        items [{id, en, translation, back_translation}] in, verdicts
        {id: {"drift": bool, "reason": str}} out, or None on any error.
        The back-translation is SUPPORTING evidence only; the judge scores
        the foreign string against the English original directly. Callers
        chunk (the service pins chunk size 50 per the V1 A/B).
        Non-abstract default raises (fail loud)."""
        raise NotImplementedError(
            "judge_translations() is not implemented by this text-AI adapter."
        )

    async def rectify_translations(
        self,
        items: list,
        language_name: str,
        language_code: str,
        *,
        glossary_context: dict | None = None,
    ) -> dict | None:
        """Bounded correction pass for the verify loop (bd polyglot-pdf-9ikj):
        items [{id, en, translation, back_translation, problem}] in,
        corrections {id: corrected_string} out, or None on any error.
        Corrections re-enter the FULL loop (re-lint + fresh back-translate +
        provenance-stripped re-judge) -- the caller owns that cycle.
        Non-abstract default raises (fail loud)."""
        raise NotImplementedError(
            "rectify_translations() is not implemented by this text-AI "
            "adapter."
        )
