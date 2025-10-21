import os
import json
from typing import Dict, List

from google import genai
from backend.utils.json_recovery import extract_json_from_part

from backend.ports.labeling_ai_port import ILabelingAI


class LabelingAIGemini(ILabelingAI):
    """Adapter for using Gemini to generate human-friendly labels."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-1.5-flash-latest"):
        """If `api_key` is provided, construct `genai.Client(api_key=...)`.

        In production we expect `backend.config.get_settings()` to set up the
        environment and the genai client. Unit tests should patch
        `genai.Client` to return a mock client exposing the same methods used
        by this adapter (for example, `get_async_generative_model`).
        """
        self._model_name = model
        # If an api_key was provided, prefer constructing a genai.Client instance
        # Tests should patch `genai.Client` to return a mock client.
        self._client = None
        try:
            if api_key:
                ClientCls = getattr(genai, "Client", None)
                if ClientCls is not None:
                    try:
                        self._client = ClientCls(api_key=api_key)
                    except Exception:
                        # Don't fail construction if client instantiation fails in tests
                        self._client = None
        except Exception:
            # Best-effort: ignore client construction errors here
            self._client = None

    async def generate_display_names(
        self, field_names: List[str], pdf_context: str
    ) -> Dict[str, str]:
        """
        Uses a Gemini model to generate cleaner, more user-friendly display names
        for raw PDF form field names.
        """
        # Use the GenAI client. Prefer the client constructed at init time
        # or construct one now via `genai.Client()` if available. Tests should
        # patch `genai.Client` and return a mock client exposing
        # `get_async_generative_model`.
        client = self._client
        if client is None:
            ClientCls = getattr(genai, "Client", None)
            if ClientCls is not None:
                client = ClientCls()

        if client is None:
            raise RuntimeError("genai.Client is not configured")

        model = client.get_async_generative_model(self._model_name)

        prompt = f"""
        You are an expert UI assistant. Your task is to create clear, human-readable labels
        for a list of raw, technical field names extracted from a PDF form.

        Use the provided text from the PDF for context. The goal is to make the labels
        as intuitive as possible for a user filling out the form with their voice.

        Respond with a JSON object mapping each original field name to your suggested
        display name.

        **PDF Content Context:**
        ---
        {pdf_context[:2000]}
        ---

        **Raw Field Names:**
        {field_names}

        **JSON Output:**
        """

        response = await model.generate_content_async(prompt)

        # Try to recover JSON using the shared helper before naive parsing.
        try:
            recovered = extract_json_from_part(response.text if hasattr(response, 'text') else response)
            if recovered is not None:
                return recovered
        except Exception:
            # Fall back to previous behavior below
            pass

        try:
            cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
            display_names = json.loads(cleaned_text)
            return display_names
        except (json.JSONDecodeError, AttributeError):
            # If parsing fails, fall back to a simple transformation.
            return {name: name.replace("_", " ").title() for name in field_names}
