"""
Shared form field models for web forms.

These models are used to represent form fields in a unified way,
independent of the source (web forms, etc.).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


class Rect(BaseModel):
	"""Bounding rectangle (used as dummy/placeholder for web forms)."""
	x0: float
	y0: float
	x1: float
	y1: float


class FormField(BaseModel):
	"""Universal form field model for web forms."""
	id: str
	# Human-readable field name
	name: Optional[str] = None
	# Client-generated stable key (optional)
	client_key: Optional[str] = None

	# Spoken / search-oriented fields produced by the LLM normalizer
	spoken_name: Optional[str] = None  # minimal canonical spoken label (e.g. "Patient First Name")
	spoken_aliases: List[str] = Field(default_factory=list)  # up to 3 short aliases for fuzzy matching

	page_index: int = 0  # Always 0 for web forms (single page)
	rect: Rect = Field(default_factory=lambda: Rect(x0=0, y0=0, x1=100, y1=20))  # Dummy rect for web
	value: Optional[str] = None
	field_type: Optional[Literal["text", "textarea", "email", "tel", "number", "date", "time", "datetime-local", "url", "password", "checkbox", "radio", "combo", "select", "list", "button", "signature", "unknown"]] = "text"
	type: Optional[str] = None  # Alias for field_type (web forms use 'type')
	flags: Optional[int] = 0
	options: List[str] = Field(default_factory=list)
	# Normalizer-provided canonical options (for radio/choice fields)
	normalized_options: Optional[List[str]] = None

	# Grouping (radio sets, checkbox clusters)
	group_id: Optional[str] = None
	group_label: Optional[str] = None
	group_kind: Optional[Literal["radio", "checkbox", "unknown"]] = None

	# Section/segment identification
	section_id: Optional[str] = None
	section_label: Optional[str] = None
	meta: Dict[str, Any] = Field(default_factory=dict)
	# Convenience debug/inspection fields (also included in meta)
	ft_info: Optional[str] = None
	flags_hex: Optional[str] = None
	classification_reason: Optional[str] = None
	confidence: Optional[float] = None
