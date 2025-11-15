"""
Context Cache Manager for Gemini Flash-Lite.

Manages schema placement in system instructions for implicit context caching,
reducing token costs by ~85% through automatic caching of static content.

Key Requirements (Phase 2B):
- Schema always first in system instruction (>1,024 tokens for caching)
- Monitor cache hit rates
- Track token cost reduction
- Validate schema consistency
"""

import hashlib
import json
from typing import Dict, Any, Optional
import structlog

_log = structlog.get_logger().bind(module="context_cache_manager")


class ContextCacheManager:
    """
    Manages context caching for Gemini Flash-Lite API.

    Gemini automatically caches system instruction content >1,024 tokens.
    By placing the form schema at the start of the system instruction,
    we get automatic caching without explicit API calls.

    Cost Savings:
    - Cached tokens cost significantly less than regular tokens
    - Target: >85% reduction in token costs
    - Cache hit rate should be >95% after first request
    """

    # Minimum tokens for Gemini to cache (API requirement)
    MIN_CACHE_TOKENS = 1024

    # Schema hash tracking for consistency validation
    _schema_hashes: Dict[str, str] = {}

    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize context cache manager.

        Args:
            session_id: Optional session ID for logging
        """
        self._session_id = session_id
        self._current_schema_hash: Optional[str] = None

        _log.info(
            "context_cache_manager_initialized",
            session_id=session_id
        )

    def build_cached_system_instruction(
        self,
        form_schema: Dict[str, Any],
        base_instruction: str
    ) -> str:
        """
        Build system instruction with schema for caching.

        Places schema at the start of system instruction to ensure:
        1. Content exceeds 1,024 tokens (caching threshold)
        2. Schema is static and cacheable
        3. Consistent ordering for cache hits

        Args:
            form_schema: Complete form schema
            base_instruction: Base instruction template

        Returns:
            str: System instruction with embedded schema
        """
        # Serialize schema in compact format
        schema_json = json.dumps(form_schema, indent=None, separators=(',', ':'))

        # Calculate and store schema hash for consistency validation
        schema_hash = self._hash_schema(schema_json)
        self._current_schema_hash = schema_hash

        # Build system instruction with schema prefix
        # Schema goes FIRST to ensure it's in the cached portion
        system_instruction = f"""FORM SCHEMA (for caching):
{schema_json}

---

{base_instruction}"""

        # Estimate token count (rough approximation: 1 token ≈ 4 characters)
        estimated_tokens = len(system_instruction) // 4

        _log.info(
            "system_instruction_built",
            schema_hash=schema_hash,
            estimated_tokens=estimated_tokens,
            will_cache=estimated_tokens >= self.MIN_CACHE_TOKENS,
            session_id=self._session_id
        )

        if estimated_tokens < self.MIN_CACHE_TOKENS:
            _log.warning(
                "schema_below_cache_threshold",
                estimated_tokens=estimated_tokens,
                min_required=self.MIN_CACHE_TOKENS,
                session_id=self._session_id
            )

        return system_instruction

    def build_dynamic_context(
        self,
        form_state: Dict[str, Any],
        conversation_history: list[Dict[str, str]],
        current_field: Optional[str] = None,
        current_part: Optional[str] = None,
        max_history_turns: int = 10
    ) -> str:
        """
        Build dynamic context (uncached portion).

        This content changes per request and is NOT cached.
        Keep it minimal (<500 tokens) for cost efficiency.

        Args:
            form_state: Current form field values
            conversation_history: Recent conversation turns
            current_field: Currently focused field ID
            current_part: Current part/section ID
            max_history_turns: Maximum history turns to include

        Returns:
            str: Formatted dynamic context
        """
        # Format form state (compact pipe-separated format)
        if form_state:
            state_entries = [
                f"{field_id}:{value}"
                for field_id, value in form_state.items()
                if value  # Only include non-empty values
            ]
            form_state_str = "|".join(state_entries)
        else:
            form_state_str = "(empty)"

        # Format conversation history (last N turns)
        history_lines = []
        recent_history = conversation_history[-max_history_turns:] if conversation_history else []

        for turn in recent_history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            # Truncate very long messages to stay under token budget
            if len(content) > 200:
                content = content[:197] + "..."
            history_lines.append(f"{role.capitalize()}: {content}")

        history_str = "\n".join(history_lines) if history_lines else "(no history)"

        # Build compact dynamic context
        context = f"""---
Current form values: {form_state_str}
Current field: {current_field or "(none)"}
Current part: {current_part or "(none)"}
Recent conversation:
{history_str}
---"""

        # Estimate token count for monitoring
        estimated_tokens = len(context) // 4

        _log.debug(
            "dynamic_context_built",
            estimated_tokens=estimated_tokens,
            form_fields=len(form_state) if form_state else 0,
            history_turns=len(recent_history),
            session_id=self._session_id
        )

        if estimated_tokens > 500:
            _log.warning(
                "dynamic_context_exceeds_target",
                estimated_tokens=estimated_tokens,
                target=500,
                session_id=self._session_id
            )

        return context

    def validate_schema_consistency(self, new_schema: Dict[str, Any]) -> bool:
        """
        Validate that schema hasn't changed (breaks caching).

        If schema changes, cache is invalidated and costs increase.
        Schema should NEVER change during a session.

        Args:
            new_schema: Schema to validate

        Returns:
            bool: True if consistent, False if changed
        """
        schema_json = json.dumps(new_schema, indent=None, separators=(',', ':'))
        new_hash = self._hash_schema(schema_json)

        if self._current_schema_hash is None:
            # First time - set baseline
            self._current_schema_hash = new_hash
            return True

        is_consistent = new_hash == self._current_schema_hash

        if not is_consistent:
            _log.error(
                "schema_consistency_violation",
                previous_hash=self._current_schema_hash,
                new_hash=new_hash,
                session_id=self._session_id
            )

        return is_consistent

    def _hash_schema(self, schema_json: str) -> str:
        """
        Calculate hash of schema for consistency tracking.

        Args:
            schema_json: Serialized schema JSON

        Returns:
            str: SHA256 hash (first 16 chars)
        """
        return hashlib.sha256(schema_json.encode()).hexdigest()[:16]

    def get_cache_metrics(self) -> Dict[str, Any]:
        """
        Get cache-related metrics for monitoring.

        Returns:
            dict: Cache metrics (schema hash, session info)
        """
        return {
            "schema_hash": self._current_schema_hash,
            "session_id": self._session_id,
            "cache_enabled": self._current_schema_hash is not None
        }


def create_cache_manager(session_id: Optional[str] = None) -> ContextCacheManager:
    """
    Factory function to create cache manager.

    Args:
        session_id: Optional session ID

    Returns:
        ContextCacheManager: Configured cache manager
    """
    return ContextCacheManager(session_id=session_id)
