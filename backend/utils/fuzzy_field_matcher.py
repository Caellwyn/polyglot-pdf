"""Fuzzy field matching for hint-based field resolution.

This module implements the fuzzy search logic for TOKEN_REDUCTION_PLAN Step 1.2.
It uses RapidFuzz to match user hints (spoken field names) to actual field IDs
with scoring and ambiguity detection.

Key Features:
- Text normalization (lowercase, strip punctuation, collapse whitespace)
- RapidFuzz ratio-based scoring with small prefix boost
- Ambiguity detection via score delta threshold
- Section/page bias support (nudges scores, never forces mismatches)
- Returns top-N candidates with scores for disambiguation

Configuration:
- ACCEPT_THRESHOLD = 0.52 (minimum score to accept top match)
- AMBIGUITY_DELTA = 0.06 (if top - second < delta, treat as ambiguous)
- MAX_CANDIDATES = 3 (maximum candidates to return for ambiguous hints)
"""
from __future__ import annotations

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover
    fuzz = None  # type: ignore
    process = None  # type: ignore

from backend.models.form_models import FormField


# Thresholds from TOKEN_REDUCTION_PLAN Section 2
ACCEPT_THRESHOLD = 0.52  # Accept top match at/above this score
AMBIGUITY_DELTA = 0.06   # If top - second < delta, treat as ambiguous
MAX_CANDIDATES = 3       # Maximum candidates for ambiguous results
PREFIX_BOOST = 0.05      # Small boost for prefix matches

# Stricter bar for a match whose WINNING text is the field id (not a spoken name).
# An id-derived match is a recovery from a hallucinated id, and id fragments share
# incidental letters ("givenname" vs "aliennumber" -> 0.60) that would clear the
# spoken-name 0.52 bar and SILENTLY MIS-FILL the wrong field. The legitimate
# recoveries are near-exact suffix variants (>= 0.95); 0.88 cleanly accepts those
# while rejecting the spurious id-fragment collisions (bd polyglot-pdf-jnjj.46).
ID_MATCH_THRESHOLD = 0.88

# Leading STRUCTURAL/positional segment of a field id -- e.g. "p1_line3a_" in
# "p1_line3a_familyname", "p2_" in "p2_signature". These segments encode WHERE the
# field sits on the form (page/line), not WHAT it is, and the model reliably
# preserves the semantic tail ("familyname") while mangling this positional head
# ("p1_line1_familyname" for "p1_line3a_familyname"). Stripping it before fuzzy
# matching keys on the meaningful suffix and -- critically -- stops a hallucinated
# id from being pulled onto a DIFFERENT field that merely shares the positional
# prefix (bd polyglot-pdf-jnjj.46). Conservative: only strips leading
# page/line-style positional segments, leaving any non-positional id untouched.
_POSITIONAL_PREFIX_RE = re.compile(r'^(?:p\d+_)?(?:line\d+[a-z]?_|part\d+_)+', re.IGNORECASE)


def strip_positional_prefix(field_id: str) -> str:
    """Strip a leading page/line positional prefix from a field id.

    Returns the semantic tail (e.g. "p1_line3a_familyname" -> "familyname"). If the
    id has no recognized positional prefix, returns it unchanged. Never returns an
    empty string (a positional-only id falls back to the original).
    """
    if not field_id:
        return field_id
    stripped = _POSITIONAL_PREFIX_RE.sub('', field_id)
    return stripped or field_id


@dataclass
class FieldCandidate:
    """A candidate field match with its score."""
    field: FormField
    score: float
    match_text: str  # The text that matched (for debugging)
    via_id: bool = False  # True if the winning match_text was the field id, not a name
    

@dataclass
class MatchResult:
    """Result of fuzzy matching a single hint."""
    status: str  # "resolved", "ambiguous", "unresolved"
    top_candidate: Optional[FieldCandidate] = None
    candidates: List[FieldCandidate] = None  # For ambiguous results
    
    def __post_init__(self):
        if self.candidates is None:
            self.candidates = []


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy matching.
    
    Applies the normalization strategy from TOKEN_REDUCTION_PLAN Phase 2:
    - Strip numeric prefixes (e.g., "3_phone_number" -> "phone_number")
    - Lowercase
    - Strip punctuation (keep only alphanumeric and spaces)
    - Collapse multiple spaces to single space
    - Trim whitespace
    
    Args:
        text: Raw text to normalize
        
    Returns:
        Normalized text string
        
    Examples:
        >>> normalize_text("Date of Birth (MM/DD/YYYY)")
        'date of birth mm dd yyyy'
        >>> normalize_text("  First   Name:  ")
        'first name'
        >>> normalize_text("3_phone_number")
        'phone number'
        >>> normalize_text("1_full_name")
        'full name'
    """
    if not text:
        return ""
    
    # Strip numeric prefix pattern: "N_" or "N. " at start
    # Handles cases like "1_full_name", "3_phone_number", "2. email"
    text = re.sub(r'^\d+[_.\s]+', '', text)
    
    # Lowercase
    normalized = text.lower()
    
    # Remove punctuation, keep alphanumeric and spaces
    normalized = re.sub(r'[^a-z0-9\s]+', ' ', normalized)
    
    # Collapse whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def calculate_score(hint: str, candidate_text: str, bias_boost: float = 0.0) -> float:
    """Calculate fuzzy match score between hint and candidate.
    
    Uses RapidFuzz token_sort_ratio for robustness to word order, plus a small
    prefix boost to prefer exact matches at the start of the text.
    
    Args:
        hint: Normalized hint text from user
        candidate_text: Normalized field text (spoken_name or alias)
        bias_boost: Optional boost from section/page bias (0.0 - 0.10)
        
    Returns:
        Score between 0.0 and 1.0 (higher is better)
        
    Implementation Notes:
        - Uses token_sort_ratio (robust to word order: "birth date" == "date birth")
        - Adds PREFIX_BOOST (0.05) if hint is prefix of candidate
        - Adds bias_boost (from section/page filters) to nudge scores
        - Never exceeds 1.0 even with boosts
    """
    if not fuzz:  # RapidFuzz not available
        # Fallback to simple exact match
        return 1.0 if hint == candidate_text else 0.0
    
    # Base score using token_sort_ratio (0-100 scale)
    base_score = fuzz.token_sort_ratio(hint, candidate_text) / 100.0
    
    # Prefix boost: if hint is prefix of candidate, add small boost
    if candidate_text.startswith(hint):
        base_score += PREFIX_BOOST
    
    # Apply bias boost (from section/page filters)
    final_score = min(1.0, base_score + bias_boost)
    
    return final_score


def build_searchable_index(
    fields: List[FormField],
) -> Dict[str, Tuple[FormField, str, bool]]:
    """Build searchable index mapping normalized text -> (field, original_text, is_id).

    Creates entries for:
    - spoken_name (primary label)
    - spoken_aliases (up to 3 search variants)
    - name (field name, fallback)
    - id with positional prefix stripped (last-resort, flagged is_id=True)

    Args:
        fields: List of form fields to index

    Returns:
        Dict mapping normalized text -> (field, original unnormalized text, is_id).
        is_id marks an entry derived from the field id rather than a spoken name, so
        the caller can hold it to the stricter ID_MATCH_THRESHOLD.

    Notes:
        - Deduplication: if same normalized text maps to multiple fields, first wins
        - Original text preserved for debugging/logging
        - group_label and section_label NOT indexed (too vague for direct matching)
        - id is indexed LAST so spoken_name/aliases/name win when both would match;
          it exists to catch a model that hallucinates a plausible id VARIANT
          (e.g. 'p1_line3_family_name' for 'p1_line3a_familyname') in
          update_form_fields rather than the spoken name (bd polyglot-pdf-jnjj.46)
    """
    index: Dict[str, Tuple[FormField, str, bool]] = {}

    for field in fields:
        # (original_text, is_id) in priority order; first to claim a normalized key wins.
        searchable_texts: List[Tuple[str, bool]] = []

        # Priority 1: spoken_name (AI-friendly canonical label)
        spoken_name = getattr(field, "spoken_name", None)
        if spoken_name:
            searchable_texts.append((spoken_name, False))

        # Priority 2: spoken_aliases (fuzzy search variants)
        spoken_aliases = getattr(field, "spoken_aliases", None) or []
        searchable_texts.extend((a, False) for a in spoken_aliases[:3])  # Max 3 aliases

        # Priority 3: field name (fallback)
        if field.name:
            searchable_texts.append((field.name, False))

        # Priority 4: field id with its positional prefix stripped (last-resort).
        # The model is GIVEN the exact id in next_field_guidance but under the
        # reduced DTI system instruction it sometimes invents a variant of that id
        # in update_form_fields. The variants preserve the SEMANTIC tail
        # ("familyname") and mangle the POSITIONAL head ("p1_line1_" for
        # "p1_line3a_"), so we index the stripped tail -- matching the raw id here
        # instead would let "p1_line1_familyname" be pulled onto whatever field
        # shares the "p1_line1" prefix and APPLY the value to the wrong field. The
        # is_id flag holds these to ID_MATCH_THRESHOLD so an incidental id-fragment
        # collision can't silently mis-fill (bd polyglot-pdf-jnjj.46).
        if field.id:
            searchable_texts.append((strip_positional_prefix(field.id), True))

        # Index all searchable texts
        for text, is_id in searchable_texts:
            if not text:
                continue
            normalized = normalize_text(text)
            if normalized and normalized not in index:
                index[normalized] = (field, text, is_id)

    return index


def fuzzy_match_hint(
    hint: str,
    fields: List[FormField],
    section_bias: Optional[str] = None,
    page_bias: Optional[int] = None,
) -> MatchResult:
    """Match a single hint to fields using fuzzy search.
    
    Implements the fuzzy matching algorithm from TOKEN_REDUCTION_PLAN Phase 2:
    1. Normalize hint text
    2. Build searchable index from fields
    3. Score all candidates (with optional section/page bias)
    4. Apply thresholds to determine status (resolved/ambiguous/unresolved)
    
    Args:
        hint: User-provided hint (e.g., "birthdate", "patient name")
        fields: List of all available fields
        section_bias: Optional section to boost scores for (e.g., "Identity")
        page_bias: Optional page number to boost scores for (e.g., 2)
        
    Returns:
        MatchResult with status and candidates
        
    Status Logic:
        - "resolved": Top score >= ACCEPT_THRESHOLD and (top - second >= AMBIGUITY_DELTA)
        - "ambiguous": Top score >= ACCEPT_THRESHOLD but (top - second < AMBIGUITY_DELTA)
        - "unresolved": Top score < ACCEPT_THRESHOLD (low confidence)
        
    Examples:
        >>> result = fuzzy_match_hint("birthdate", fields)
        >>> result.status
        'resolved'
        >>> result.top_candidate.field.id
        'B91Q20'
        >>> result.top_candidate.score
        0.87
    """
    if not hint or not fields:
        return MatchResult(status="unresolved")
    
    normalized_hint = normalize_text(hint)
    if not normalized_hint:
        return MatchResult(status="unresolved")

    # A hint that is itself a (possibly hallucinated) field id carries a positional
    # prefix the stripped-id index entries don't; precompute the stripped form so
    # those entries can be scored against it (the scoring loop uses this for is_id
    # entries only) -- that is what lets a mangled id like "p1_line1_familyname"
    # match the stripped-id entry "familyname" (bd polyglot-pdf-jnjj.46).
    # normalize_text collapses the id's underscores to spaces, so strip the raw hint.
    normalized_hint_stripped = normalize_text(strip_positional_prefix(hint))

    # Build index
    index = build_searchable_index(fields)
    if not index:
        return MatchResult(status="unresolved")

    # Score all candidates
    scored_candidates: List[FieldCandidate] = []

    for normalized_text, (field, original_text, is_id) in index.items():
        # Calculate bias boost
        bias_boost = 0.0

        # Section bias: boost if field's section_label matches
        if section_bias:
            field_section = getattr(field, "section_label", None)
            if field_section and field_section.lower().strip() == section_bias.lower().strip():
                bias_boost += 0.05

        # Page bias: boost if field's page_index matches
        if page_bias is not None:
            if field.page_index == page_bias:
                bias_boost += 0.03

        score = calculate_score(normalized_hint, normalized_text, bias_boost)
        # An id-derived entry only meaningfully matches the STRIPPED hint (the raw
        # hint still carries its positional prefix); score it that way.
        if is_id and normalized_hint_stripped:
            score = calculate_score(normalized_hint_stripped, normalized_text, bias_boost)

        scored_candidates.append(FieldCandidate(
            field=field,
            score=score,
            match_text=original_text,
            via_id=is_id,
        ))

    # Collapse to the best score PER FIELD before ranking. A field is indexed under
    # several texts (spoken_name, aliases, name, stripped id), so without this the
    # same field can occupy both top slots and a clear single-field win reads as
    # "ambiguous" (its own second-best entry sits within AMBIGUITY_DELTA of its
    # best). De-duping by field id makes the ambiguity check compare DISTINCT fields
    # (bd polyglot-pdf-jnjj.46).
    best_by_field: Dict[str, FieldCandidate] = {}
    for cand in scored_candidates:
        existing = best_by_field.get(cand.field.id)
        if existing is None or cand.score > existing.score:
            best_by_field[cand.field.id] = cand
    scored_candidates = list(best_by_field.values())

    # Sort by score descending
    scored_candidates.sort(key=lambda c: c.score, reverse=True)

    if not scored_candidates:
        return MatchResult(status="unresolved")
    
    top = scored_candidates[0]

    # Check if top score meets acceptance threshold. An id-derived win must clear the
    # stricter ID_MATCH_THRESHOLD -- legitimate id-variant recoveries are near-exact
    # suffix matches (>= 0.95), whereas spurious id-fragment collisions sit ~0.60 and
    # would mis-fill if held only to the 0.52 spoken-name bar (bd polyglot-pdf-jnjj.46).
    threshold = ID_MATCH_THRESHOLD if top.via_id else ACCEPT_THRESHOLD
    if top.score < threshold:
        return MatchResult(status="unresolved")
    
    # Check for ambiguity
    if len(scored_candidates) > 1:
        second = scored_candidates[1]
        delta = top.score - second.score
        
        if delta < AMBIGUITY_DELTA:
            # Ambiguous: return top N candidates
            return MatchResult(
                status="ambiguous",
                candidates=scored_candidates[:MAX_CANDIDATES]
            )
    
    # Resolved: clear winner
    return MatchResult(
        status="resolved",
        top_candidate=top
    )

