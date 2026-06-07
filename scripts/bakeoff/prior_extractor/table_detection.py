from __future__ import annotations

"""Table detection utilities for PDF schema extraction.

This module consolidates repeating PDF widget patterns into semantic table
fields that comply with the ``FormField`` / ``TableColumn`` models.

The implementation intentionally focuses on heuristic signals that show up in
USCIS-style forms:

* Repeated field name stems with small trailing row numbers (e.g., ``ChildAlien1``,
  ``ChildAlien2``).
* Labels that mention logical row indicators such as "Child 3" or "Entry 2".
* Consistent spatial groupings per section (rows cluster closely on the page).

The code is structured so additional heuristics can be layered in without
having to modify ``extractor.py`` directly.
"""

from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
import math
import re

# Bake-off (bd polyglot-pdf-7a9.4): support both relative (-m) and flat run styles.
try:
    from .form_models import (FormField, FieldType, TableColumn,
                              MultiEntryConfig, FieldOption, SupplementType)
except ImportError:
    from form_models import (FormField, FieldType, TableColumn,
                             MultiEntryConfig, FieldOption, SupplementType)


def _is_supported_section(section_id: str) -> bool:
    """Check if a section likely contains tables based on heuristic patterns."""
    # Allow table detection in all Part A sections and supplements
    if section_id.startswith("part_a"):
        return True
    if section_id.startswith("supplement"):
        return True
    if section_id.startswith("part_d"):
        return True
    return False


def _slugify(text: Optional[str]) -> str:
    if not text:
        return ""
    normalized = text.strip().lower()
    normalized = normalized.replace("u. s.", "us").replace("u.s.", "us")
    normalized = normalized.replace("i. d.", "id").replace("i.d.", "id")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _split_label_components(label: Optional[str]) -> Tuple[str, Optional[str]]:
    if not label:
        return "", None

    text = re.sub(r"\s+", " ", label.strip())
    text = re.sub(r"(?i)^child\s+\d+\.\s*", "", text)
    text = re.sub(r"(?i)^additional\s+child\s+\d+\.\s*", "", text)
    text = re.sub(r"(?i)\(continued\)", "", text)

    option_label: Optional[str] = None
    option_match = re.search(
        r"(?:\.\s*)?(select|check)\s+([A-Za-z0-9/()\s-]+)$",
        text,
        flags=re.IGNORECASE,
    )
    if option_match:
        option_label = option_match.group(2).strip()
        text = text[: option_match.start()].rstrip(" .")

    text = re.sub(r"(?i)\(check the appropriate box\)", "", text)
    text = re.sub(r"(?i)\(check (?:one|only one) box\)", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")

    return text, option_label


def _canonicalize_option_label(option_label: Optional[str]) -> Optional[str]:
    if not option_label:
        return None
    text = re.sub(r"\(.*?\)", "", option_label).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"y", "yes"}:
        return "Yes"
    if lowered in {"n", "no"}:
        return "No"
    if lowered in {"male", "female"}:
        return lowered.capitalize()
    return text


def _canonicalize_base_label(raw_label: str) -> str:
    if not raw_label:
        return ""

    label = re.sub(r"\s+", " ", raw_label.strip())
    label = label.replace("I D", "ID")
    label = re.sub(r"(?i)^if\s+(?:child|this child|the child|your child)\s+is\s+in\s+the\s+u\.?\s*s\.?[,]?\s*", "", label)
    label = re.sub(r"(?i)^if\s+in\s+the\s+u\.?\s*s\.?[,]?\s*", "", label)
    label = re.sub(r"(?i)^if\s+previously\s+in\s+the\s+u\.?\s*s\.?[,]?\s*", "", label)
    label = re.sub(r"(?i)enter as 2-digit month.*", "", label)
    label = re.sub(r"(?i)enter date as 2-digit month.*", "", label)
    label = re.sub(r"(?i)enter expiration date as 2-digit month.*", "", label)
    label = re.sub(r"(?i)\.\s*enter\s+[A-Za-z0-9/ .-]+$", "", label)
    label = re.sub(r"(?i)\s*enter\s+[A-Za-z0-9/ .-]+$", "", label)
    label = re.sub(r"\s+", " ", label).strip(" .")

    lowered = label.lower()

    if "enter location" in lowered:
        return "Specify location"
    if "alien registration number" in lowered:
        return "A-Number"
    if "passport" in lowered and "card number" in lowered:
        return "Passport/ID Card Number"
    if "marital status" in lowered:
        return "Marital Status"
    if "social security number" in lowered:
        return "U.S. Social Security Number"
    if lowered.startswith("complete last name") or lowered == "last name":
        return "Complete Last Name"
    if lowered.startswith("first name"):
        return "First Name"
    if lowered.startswith("middle name"):
        return "Middle Name"
    if "date of birth" in lowered:
        return "Date of Birth"
    if "city" in lowered and "country of birth" in lowered:
        return "City and Country of Birth"
    if "nationality" in lowered and "citizenship" in lowered:
        return "Nationality (Citizenship)"
    if "race" in lowered and "tribal" in lowered:
        return "Race, Ethnic, or Tribal Group"
    if lowered == "sex":
        return "Sex"
    if "immigration court proceedings" in lowered:
        return "In Immigration Court proceedings?"
    if "included in this application" in lowered or "include in this application" in lowered:
        return "Include in this application?"
    if "current status" in lowered:
        return "Current status"
    if "expiration date" in lowered and "authorized stay" in lowered:
        return "Status expiration date"
    if "status when last admitted" in lowered:
        return "Status when last admitted"
    if "place of last entry" in lowered:
        return "Place of last entry"
    if "date of last entry" in lowered:
        return "Date of last entry"
    if "i-94" in lowered or "i94" in lowered:
        return "I-94 Number"
    if "is this child in the u" in lowered and "specify" not in lowered:
        return "Is this child in the U.S.?"

    label = re.sub(r"(?i)^what is your child's\s+", "", label)
    label = re.sub(r"(?i)^what is the\s+", "", label)
    label = re.sub(r"\?$", "", label)
    label = re.sub(r"(?i)^enter\s+", "", label)
    label = label.strip(" .")

    return label


def _normalize_pdf_base(base_name: str) -> str:
    base = base_name
    base = re.sub(r"\[\d+\]$", "", base)
    base = re.sub(r"(\d+)$", "", base)
    if base.lower().startswith("checkbox"):
        base = re.sub(r"checkbox\d*", "checkbox", base, flags=re.IGNORECASE)
    base = re.sub(r"_(yes|no)$", "", base, flags=re.IGNORECASE)
    normalized = base.strip("_").lower()
    normalized = PDF_BASE_NORMALIZATION_OVERRIDES.get(normalized, normalized)
    return normalized


CHILDREN_COLUMN_OVERRIDES: Dict[str, Tuple[str, str]] = {
    "a_number": ("a_number", "A-Number"),
    "passport_id_card_number": ("passport_id", "Passport/ID Card Number"),
    "marital_status": ("marital_status", "Marital Status"),
    "u_s_social_security_number": ("ssn", "U.S. Social Security Number"),
    "complete_last_name": ("last_name", "Complete Last Name"),
    "first_name": ("first_name", "First Name"),
    "middle_name": ("middle_name", "Middle Name"),
    "date_of_birth": ("dob", "Date of Birth"),
    "city_and_country_of_birth": ("city_country_of_birth", "City and Country of Birth"),
    "nationality_citizenship": ("nationality", "Nationality (Citizenship)"),
    "race_ethnic_or_tribal_group": ("race_ethnic_tribal_group", "Race, Ethnic, or Tribal Group"),
    "sex": ("sex", "Sex"),
    "is_this_child_in_the_us": ("in_us", "Is this child in the U.S.?"),
    "specify_location": ("location_not_in_us", "Specify location"),
    "place_of_last_entry": ("place_of_last_entry", "Place of last entry"),
    "date_of_last_entry": ("date_of_last_entry", "Date of last entry"),
    "i_94_number": ("i94_number", "I-94 Number"),
    "status_when_last_admitted": ("status_when_admitted", "Status when last admitted"),
    "current_status": ("current_status", "Current status"),
    "status_expiration_date": ("status_expiration_date", "Status expiration date"),
    "in_immigration_court_proceedings": ("in_proceedings", "In Immigration Court proceedings?"),
    "include_in_this_application": ("include_in_application", "Include in this application?"),
}


CHILDREN_COLUMN_ORDER_BY_SLUG: Dict[str, int] = {
    slug: index for index, slug in enumerate(CHILDREN_COLUMN_OVERRIDES.keys())
}

CHILDREN_COLUMN_ORDER_BY_ID: Dict[str, int] = {
    column_id: index
    for index, (_slug, (column_id, _label)) in enumerate(CHILDREN_COLUMN_OVERRIDES.items())
}


CHILDREN_COLUMN_PDF_BASE_OVERRIDES: Dict[str, Tuple[str, str]] = {
    "childalien": ("a_number", "A-Number"),
    "childpassport": ("passport_id", "Passport/ID Card Number"),
    "childmarital": ("marital_status", "Marital Status"),
    "childssn": ("ssn", "U.S. Social Security Number"),
    "childlast": ("last_name", "Complete Last Name"),
    "childfirst": ("first_name", "First Name"),
    "childmiddle": ("middle_name", "Middle Name"),
    "childdob": ("dob", "Date of Birth"),
    "childcity": ("city_country_of_birth", "City and Country of Birth"),
    "childnat": ("nationality", "Nationality (Citizenship)"),
    "childrace": ("race_ethnic_tribal_group", "Race, Ethnic, or Tribal Group"),
    "checkbox_sex": ("sex", "Sex"),
    "ptaiiline14_placeoflastentry": ("place_of_last_entry", "Place of last entry"),
    "ptaiiline15_dateoflastentry": ("date_of_last_entry", "Date of last entry"),
    "ptaiiline16_i94number": ("i94_number", "I-94 Number"),
    "ptaiiline17_statusoflastadmission": ("status_when_admitted", "Status when last admitted"),
    "ptaiiline18_currentstatusofchild": ("current_status", "Current status"),
    "ptaiiline19_expdateofauthorizedstay": ("status_expiration_date", "Status expiration date"),
    "ptaiiline20": ("in_proceedings", "In Immigration Court proceedings?"),
    "ptaiiline21": ("include_in_application", "Include in this application?"),
    "ptaiiline13_specify": ("location_not_in_us", "Specify location"),
}


PDF_BASE_NORMALIZATION_OVERRIDES: Dict[str, str] = {
    "ptaiiline15_expirationdate": "ptaiiline15_dateoflastentry",
    "ptaiiline18_currentstatusofchild": "ptaiiline18_childcurrentstatus",
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TableToken:
    """Intermediate representation for a PDF field that might belong to a table."""

    field: FormField
    section_id: str
    normalized_key: str
    question_label: str
    question_slug: str
    option_label: Optional[str]
    option_value: Optional[str]
    row_number: Optional[int]
    array_index: Optional[int]
    base_pdf_name: str
    pdf_base_key: str
    x: float
    y: float


@dataclass
class ColumnCandidate:
    """All tokens that appear to describe the same logical column."""

    normalized_key: str
    tokens: List[TableToken]

    @property
    def rows(self) -> Set[int]:
        return {token.row_number for token in self.tokens if token.row_number is not None}

    @property
    def anchor_token(self) -> TableToken:
        """Best representative token (prefer lowest row number, then smallest y)."""
        def sort_key(token: TableToken) -> Tuple[int, float, float]:
            row = token.row_number if token.row_number is not None else math.inf
            return (row, token.y, token.x)

        return sorted(self.tokens, key=sort_key)[0]

    @property
    def question_slug(self) -> str:
        return self.tokens[0].question_slug

    @property
    def question_label(self) -> str:
        return self.tokens[0].question_label

    @property
    def option_label(self) -> Optional[str]:
        return self.tokens[0].option_label

    @property
    def option_value(self) -> Optional[str]:
        return self.tokens[0].option_value


@dataclass
class OptionEntry:
    value: str
    label: str
    pdf_field_name: Optional[str]
    sort_key: Tuple[float, float]


@dataclass
class AggregatedColumnData:
    question_slug: str
    question_label: str
    anchor_token: Optional[TableToken] = None
    column_type: Optional[FieldType] = None
    help: Optional[object] = None
    validation: Optional[object] = None
    pdf_field_name: Optional[str] = None
    tokens: List[TableToken] = field(default_factory=list)
    used_field_ids: Set[str] = field(default_factory=set)
    options: Optional[List[FieldOption]] = None
    column_id_override: Optional[str] = None
    pdf_base_key: Optional[str] = None
    _option_map: Dict[str, OptionEntry] = field(default_factory=dict)

    def incorporate(self, candidate: ColumnCandidate) -> None:
        anchor = candidate.anchor_token
        anchor_sort = (anchor.y, anchor.x)
        if self.anchor_token is None or anchor_sort < (self.anchor_token.y, self.anchor_token.x):
            self.anchor_token = anchor
        if self.column_type is None:
            self.column_type = anchor.field.type
        if self.help is None:
            self.help = anchor.field.help
        if self.validation is None:
            self.validation = anchor.field.validation
        if self.pdf_field_name is None:
            self.pdf_field_name = anchor.field.pdf_field_name
        if self.pdf_base_key is None:
            self.pdf_base_key = anchor.pdf_base_key

        self.tokens.extend(candidate.tokens)
        for token in candidate.tokens:
            self.used_field_ids.add(token.field.id)

        option_label = candidate.option_label
        if option_label:
            canonical_option = option_label
            option_value = candidate.option_value or _slugify(option_label)
            entry = OptionEntry(
                value=option_value,
                label=canonical_option,
                pdf_field_name=anchor.field.pdf_field_name,
                sort_key=anchor_sort,
            )
            existing = self._option_map.get(option_value)
            if not existing or entry.sort_key < existing.sort_key:
                self._option_map[option_value] = entry

    def finalize(self, section_id: str) -> None:
        if self.anchor_token:
            if self.column_type is None:
                self.column_type = self.anchor_token.field.type
            if self.help is None:
                self.help = self.anchor_token.field.help
            if self.validation is None:
                self.validation = self.anchor_token.field.validation
            if self.pdf_field_name is None:
                self.pdf_field_name = self.anchor_token.field.pdf_field_name
            if self.pdf_base_key is None:
                self.pdf_base_key = self.anchor_token.pdf_base_key

        if self._option_map:
            ordered_entries = sorted(self._option_map.values(), key=lambda entry: entry.sort_key)
            self.options = [
                FieldOption(
                    value=entry.value,
                    label=entry.label,
                    spoken_label=entry.label,
                    pdf_field_name=entry.pdf_field_name,
                )
                for entry in ordered_entries
            ]
            self.column_type = FieldType.RADIO
        else:
            self.options = None

        override_id, override_label = _resolve_column_metadata(section_id, self)
        if override_label:
            self.question_label = override_label
        if override_id:
            self.column_id_override = override_id


def _resolve_column_metadata(
    section_id: str, column: AggregatedColumnData
) -> Tuple[Optional[str], Optional[str]]:
    if not _is_supported_section(section_id):
        return (None, None)

    if column.question_slug:
        override = CHILDREN_COLUMN_OVERRIDES.get(column.question_slug)
        if override:
            return override

    if column.pdf_base_key:
        override = CHILDREN_COLUMN_PDF_BASE_OVERRIDES.get(column.pdf_base_key)
        if override:
            return override

    return (None, None)


@dataclass
class DetectedTable:
    """Final representation used to build a ``FormField`` of type ``TABLE``."""

    section_id: str
    table_id: str
    table_name: str
    spoken_name: str
    rows: Sequence[int]
    columns: List[TableColumn]
    used_field_ids: Set[str]
    multi_entry: MultiEntryConfig


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def consolidate_tables(
    fields: Sequence[FormField],
) -> List[FormField]:
    """Return a new field list where repeating patterns are replaced by tables using heuristic detection."""

    tokens_by_section: Dict[str, List[TableToken]] = defaultdict(list)
    for field in fields:
        token = _build_token(field)
        if token:
            tokens_by_section[token.section_id].append(token)

    detected_tables: List[DetectedTable] = []
    section_used_ids: Dict[str, Set[str]] = defaultdict(set)

    for section_id, tokens in tokens_by_section.items():
        tables = _detect_tables_in_section(section_id, tokens)
        detected_tables.extend(tables)
        for table in tables:
            section_used_ids[section_id].update(table.used_field_ids)

    used_field_ids_flat = {fid for ids in section_used_ids.values() for fid in ids}
    retained_fields = [field for field in fields if field.id not in used_field_ids_flat]
    table_fields = [
        FormField(
            id=table.table_id,
            name=table.table_name,
            spoken_name=table.spoken_name,
            type=FieldType.TABLE,
            section_id=table.section_id,
            columns=table.columns,
            multi_entry=table.multi_entry,
        )
        for table in detected_tables
    ]

    return retained_fields + table_fields


# ---------------------------------------------------------------------------
# Section-level detection
# ---------------------------------------------------------------------------


def _detect_tables_in_section(section_id: str, tokens: Sequence[TableToken]) -> List[DetectedTable]:
    """Detect tables inside a single section using heuristic pattern matching."""

    if not _is_supported_section(section_id):
        return []

    # Group tokens by normalized key (column stem).
    tokens_by_key: Dict[str, List[TableToken]] = defaultdict(list)
    for token in tokens:
        tokens_by_key[token.normalized_key].append(token)

    column_candidates = [ColumnCandidate(key, toks) for key, toks in tokens_by_key.items()]

    # Focus on columns that clearly belong to multi-row structures for now.
    multi_row_groups: Dict[Tuple[int, ...], List[ColumnCandidate]] = defaultdict(list)
    for candidate in column_candidates:
        enriched_rows = _ensure_row_numbers(candidate.tokens)
        if len(enriched_rows) >= 2:
            multi_row_groups[tuple(sorted(enriched_rows))].append(candidate)

    detected: List[DetectedTable] = []
    for rows_tuple, columns in multi_row_groups.items():
        table = _build_table_from_columns(section_id, rows_tuple, columns)
        if table:
            detected.append(table)

    return detected


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


ROW_LABEL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"child\s+(\d+)",
        r"additional\s+child\s+(\d+)",
        r"entry\s+(\d+)",
        r"family\s+(?:member|name)\s+(\d+)",
        r"supplement\s+a.*child\s+(\d+)",
        r"row\s+(\d+)",
        r"line\s+(\d+)",
    ]
]

ROW_Y_TOLERANCE = 2.0


def _build_token(field: FormField) -> Optional[TableToken]:
    if not field.pdf_field_name or not field.pdf_position:
        return None

    base_name, array_index = _split_pdf_field_name(field.pdf_field_name)
    pdf_key_candidate, row_number = _extract_row_number(base_name)

    if row_number is None:
        row_number = _extract_row_from_label(field.name)

    raw_label, option_label_raw = _split_label_components(field.name)
    question_label = _canonicalize_base_label(raw_label)
    if not question_label:
        question_label = raw_label or field.name or base_name

    raw_label_lower = raw_label.lower() if raw_label else ""
    if (
        field.section_id
        and field.section_id.startswith("part_a_ii")
        and field.type == FieldType.TEXT
        and ("enter location" in raw_label_lower or "specify location" in raw_label_lower)
    ):
        question_label = "Specify location"

    question_slug = _slugify(question_label)
    if not question_slug:
        question_slug = _slugify(pdf_key_candidate) or _slugify(base_name)

    option_label = _canonicalize_option_label(option_label_raw)
    option_value = _slugify(option_label) if option_label else None

    pdf_base_key = _normalize_pdf_base(base_name)

    base_key_slug = question_slug or _slugify(pdf_key_candidate) or base_name.lower()
    normalized_base = base_key_slug or base_name.lower()
    if pdf_base_key and pdf_base_key not in normalized_base:
        normalized_base = f"{normalized_base}__{pdf_base_key}"

    normalized_key = normalized_base or base_name.lower()
    if option_value:
        normalized_key = f"{normalized_key}__{option_value}" if normalized_key else option_value

    return TableToken(
        field=field,
        section_id=field.section_id,
        normalized_key=normalized_key,
        question_label=question_label,
        question_slug=question_slug or normalized_key,
        option_label=option_label,
        option_value=option_value,
        row_number=row_number,
        array_index=array_index,
        base_pdf_name=base_name,
        pdf_base_key=pdf_base_key,
        x=field.pdf_position.x,
        y=field.pdf_position.y,
    )


def _split_pdf_field_name(pdf_field_name: str) -> Tuple[str, Optional[int]]:
    leaf = pdf_field_name.split('.')[-1]
    if '[' in leaf and leaf.endswith(']'):
        idx_start = leaf.rfind('[')
        try:
            index = int(leaf[idx_start + 1 : -1])
        except ValueError:
            index = None
        base = leaf[:idx_start]
        return base, index
    return leaf, None


def _extract_row_number(base_name: str) -> Tuple[str, Optional[int]]:
    """Return (normalized_key, row_number)."""

    match = re.search(r"(\d+)$", base_name)
    if match:
        value = int(match.group(1))
        # Guard against field stems like TextField13 (not a row indicator).
        if value <= 12:
            normalized = base_name[: -len(match.group(1))]
            normalized = normalized.rstrip('_')
            return normalized or base_name, value
    checkbox_match = re.match(r"(?i)(checkbox)(\d+)(.*)", base_name)
    if checkbox_match:
        try:
            value = int(checkbox_match.group(2))
        except ValueError:
            value = None
        if value is not None and value >= 10:
            normalized = f"{checkbox_match.group(1)}{checkbox_match.group(3)}".rstrip('_')
            row_number = max(1, value // 10)
            return normalized or base_name, row_number
    return base_name, None


def _extract_row_from_label(label: Optional[str]) -> Optional[int]:
    if not label:
        return None
    for pattern in ROW_LABEL_PATTERNS:
        match = pattern.search(label)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _ensure_row_numbers(tokens: List[TableToken]) -> Set[int]:
    """Fill missing row numbers when the pattern clearly indicates row 1."""

    rows = {token.row_number for token in tokens if token.row_number is not None}
    if rows and min(rows) > 1:
        # There are later rows but row 1 is missing; assume the non-numbered
        # fields correspond to row 1 (common in USCIS PDFs).
        for token in tokens:
            if token.row_number is None:
                token.row_number = min(rows) - 1
        rows = {token.row_number for token in tokens if token.row_number is not None}

    if not rows:
        sorted_tokens = sorted(tokens, key=lambda t: (t.y, t.x))
        row_counter = 1
        last_y: Optional[float] = None
        y_to_row: Dict[float, int] = {}
        for token in sorted_tokens:
            y_value = round(token.y, 1)
            if last_y is None or abs(y_value - last_y) > ROW_Y_TOLERANCE:
                y_to_row[y_value] = row_counter
                row_counter += 1
                last_y = y_value
            if y_value not in y_to_row:
                nearest = min(y_to_row.keys(), key=lambda existing: abs(existing - y_value))
                token.row_number = y_to_row[nearest]
            else:
                token.row_number = y_to_row[y_value]
        rows = {token.row_number for token in tokens if token.row_number is not None}

    return rows


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------


def _aggregate_column_candidates(
    section_id: str, candidates: Sequence[ColumnCandidate]
) -> List[AggregatedColumnData]:
    grouped: Dict[str, AggregatedColumnData] = {}
    for candidate in candidates:
        slug = candidate.question_slug or candidate.normalized_key
        label = candidate.question_label or candidate.anchor_token.field.name
        key = slug or candidate.normalized_key
        if key not in grouped:
            grouped[key] = AggregatedColumnData(question_slug=key, question_label=label)
        grouped[key].incorporate(candidate)

    aggregated = list(grouped.values())
    for group in aggregated:
        group.finalize(section_id)
    return aggregated


def _match_expected_table(
    section_id: str,
    aggregated_columns: Sequence[AggregatedColumnData],
    expected_defs: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not expected_defs:
        return None

    aggregated_slugs = {
        _slugify(col.question_label) for col in aggregated_columns if col.question_label
    }
    aggregated_slugs.update(
        {col.question_slug for col in aggregated_columns if col.question_slug}
    )
    aggregated_slugs.discard("")
    aggregated_count = len(aggregated_columns)

    best_def: Optional[Dict[str, Any]] = None
    best_score = -math.inf

    for table_def in expected_defs:
        expected_columns = table_def.get("columns") or []
        if not expected_columns:
            continue

        expected_slugs = {
            _slugify(col.get("label", "")) for col in expected_columns if col.get("label")
        }
        expected_slugs.discard("")
        overlap = len(expected_slugs & aggregated_slugs)
        score = overlap * 5 - abs(len(expected_columns) - aggregated_count) * 3

        if table_def.get("section_id") == section_id:
            score += 1

        if overlap == 0 and abs(len(expected_columns) - aggregated_count) > 2:
            continue

        if score > best_score:
            best_score = score
            best_def = table_def

    return best_def


def _build_columns_from_expected(
    expected_table: Dict[str, Any],
    aggregated_columns: Sequence[AggregatedColumnData],
    rows: Sequence[int],
) -> Tuple[List[TableColumn], Set[str], Optional[List[Dict[str, str]]]]:
    expected_columns = expected_table.get("columns") or []
    if not expected_columns:
        return ([], set(), None)

    remaining = list(aggregated_columns)
    assignments: Dict[str, AggregatedColumnData] = {}

    for expected_col in expected_columns:
        match = _find_best_aggregated_column(expected_col, remaining)
        if match:
            key = expected_col.get("id") or _slugify(expected_col.get("label", ""))
            assignments[key] = match
            remaining.remove(match)

    if not assignments:
        return ([], set(), None)

    table_columns: List[TableColumn] = []
    used_field_ids: Set[str] = set()

    for expected_col in expected_columns:
        key = expected_col.get("id") or _slugify(expected_col.get("label", ""))
        aggregated = assignments.get(key)
        if not aggregated:
            continue

        anchor = aggregated.anchor_token
        column_type = aggregated.column_type or (anchor.field.type if anchor else FieldType.TEXT)
        expected_type = expected_col.get("type")
        if expected_type:
            try:
                column_type = FieldType(expected_type)
            except ValueError:
                pass

        expected_options = expected_col.get("options") or []
        if expected_options:
            column_options = _convert_expected_options(expected_options)
        else:
            column_options = aggregated.options

        table_columns.append(
            TableColumn(
                id=expected_col.get("id", aggregated.question_slug),
                label=expected_col.get("label", aggregated.question_label),
                type=column_type,
                help=aggregated.help,
                validation=aggregated.validation,
                pdf_field_name=anchor.field.pdf_field_name if anchor else expected_col.get("pdf_field_name"),
                options=column_options,
            )
        )
        used_field_ids.update(token.field.id for token in aggregated.tokens)

    row_pdf_field_map = _build_row_pdf_field_map(rows, expected_table, assignments)
    return (table_columns, used_field_ids, row_pdf_field_map)


def _find_best_aggregated_column(
    expected_col: Dict[str, Any],
    candidates: Sequence[AggregatedColumnData],
) -> Optional[AggregatedColumnData]:
    if not candidates:
        return None

    expected_id = expected_col.get("id")
    expected_label = expected_col.get("label", "")
    expected_slug = _slugify(expected_label)
    expected_pdf = expected_col.get("pdf_field_name")
    expected_pdf_base = None
    if expected_pdf:
        expected_pdf_base = _normalize_pdf_base(expected_pdf.split('.')[-1])

    for candidate in candidates:
        if expected_id and (
            candidate.column_id_override == expected_id
            or candidate.question_slug == expected_id
        ):
            return candidate

    for candidate in candidates:
        if expected_slug and (
            candidate.question_slug == expected_slug
            or _slugify(candidate.question_label) == expected_slug
        ):
            return candidate

    best_candidate: Optional[AggregatedColumnData] = None
    best_score = -math.inf

    for candidate in candidates:
        score = 0
        question_label_lower = candidate.question_label.lower()
        expected_label_lower = expected_label.lower()
        if expected_label_lower and expected_label_lower in question_label_lower:
            score += 3
        if question_label_lower and question_label_lower in expected_label_lower:
            score += 3
        if expected_pdf_base and candidate.anchor_token:
            if candidate.anchor_token.pdf_base_key == expected_pdf_base:
                score += 4
        if candidate.anchor_token and expected_slug:
            if expected_slug in candidate.anchor_token.base_pdf_name.lower():
                score += 1

        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate


def _convert_expected_options(options_payload: Sequence[Dict[str, Any]]) -> List[FieldOption]:
    result: List[FieldOption] = []
    for option in options_payload:
        value = option.get("value")
        label = option.get("label")
        if not value or not label:
            continue
        result.append(
            FieldOption(
                value=value,
                label=label,
                spoken_label=option.get("spoken_label", label),
                pdf_field_name=option.get("pdf_field_name"),
            )
        )
    return result


def _build_row_pdf_field_map(
    rows: Sequence[int],
    expected_table: Dict[str, Any],
    assignments: Dict[str, AggregatedColumnData],
) -> Optional[List[Dict[str, str]]]:
    if not rows:
        return None

    expected_columns = expected_table.get("columns") or []
    if not expected_columns:
        return None

    row_maps: List[Dict[str, str]] = []
    for row_number in rows:
        mapping: Dict[str, str] = {}
        for column_def in expected_columns:
            column_id = column_def.get("id")
            aggregated = assignments.get(column_id)
            if not aggregated:
                fallback_key = _slugify(column_def.get("label", ""))
                aggregated = assignments.get(fallback_key)
            if not aggregated:
                continue
            token = _select_token_for_row(aggregated.tokens, row_number)
            if token:
                mapping[column_id] = token.field.pdf_field_name
        if mapping:
            row_maps.append(mapping)

    return row_maps or None


def _select_token_for_row(tokens: Sequence[TableToken], row_number: int) -> Optional[TableToken]:
    candidates = [token for token in tokens if token.row_number == row_number]
    if candidates:
        return sorted(candidates, key=lambda t: (t.y, t.x))[0]

    ordered = sorted(tokens, key=lambda t: (t.row_number or math.inf, t.y, t.x))
    if not ordered:
        return None

    index = min(max(row_number - 1, 0), len(ordered) - 1)
    return ordered[index]


def _build_columns_fallback(
    section_id: str,
    aggregated_columns: Sequence[AggregatedColumnData],
) -> Tuple[List[TableColumn], Set[str]]:
    seen_column_ids: Set[str] = set()
    table_columns: List[TableColumn] = []
    used_field_ids: Set[str] = set()

    def column_sort_key(column: AggregatedColumnData) -> Tuple[int, float, float, float]:
        anchor = column.anchor_token
        normalized_section = section_id or ""
        if normalized_section.startswith("part_a_ii") or normalized_section.startswith("supplement_a"):
            preferred = column.column_id_override or column.question_slug
            order_index = None
            if preferred:
                order_index = CHILDREN_COLUMN_ORDER_BY_ID.get(preferred)
            if order_index is None and column.question_slug:
                order_index = CHILDREN_COLUMN_ORDER_BY_SLUG.get(column.question_slug)
            if order_index is not None:
                anchor_x = anchor.x if anchor else math.inf
                anchor_y = anchor.y if anchor else math.inf
                return (0, float(order_index), anchor_y, anchor_x)
        if anchor is None:
            return (1, math.inf, math.inf, math.inf)
        return (1, anchor.y, anchor.x, 0.0)

    for aggregated in sorted(aggregated_columns, key=column_sort_key):
        anchor = aggregated.anchor_token
        if anchor is None:
            continue

        preferred_id = aggregated.column_id_override or aggregated.question_slug
        column_id = _derive_column_id(
            anchor.field,
            section_id,
            seen_column_ids,
            preferred_id=preferred_id,
        )
        table_columns.append(
            TableColumn(
                id=column_id,
                label=aggregated.question_label,
                type=aggregated.column_type or anchor.field.type,
                help=aggregated.help,
                validation=aggregated.validation,
                pdf_field_name=aggregated.pdf_field_name,
                options=aggregated.options,
            )
        )
        seen_column_ids.add(column_id)
        used_field_ids.update(token.field.id for token in aggregated.tokens)

    return table_columns, used_field_ids


def _build_table_from_columns(
    section_id: str,
    rows_tuple: Tuple[int, ...],
    columns: Sequence[ColumnCandidate],
) -> Optional[DetectedTable]:
    """Build a table from column candidates using pure heuristic approach."""
    if not columns:
        return None

    aggregated_columns = _aggregate_column_candidates(section_id, columns)

    # Require a reasonable number of columns before treating a group as a table.
    if len(aggregated_columns) < 3:
        return None

    rows = sorted(rows_tuple)

    # Build columns using heuristic fallback logic
    table_columns, used_field_ids = _build_columns_fallback(section_id, aggregated_columns)

    if not table_columns:
        return None

    # Infer table metadata from section and column patterns
    table_id, table_name, spoken_name = _infer_table_metadata(section_id, table_columns)
    multi_entry = _build_multi_entry_config(
        section_id,
        rows,
        table_columns,
    )

    return DetectedTable(
        section_id=section_id,
        table_id=table_id,
        table_name=table_name,
        spoken_name=spoken_name,
        rows=rows,
        columns=table_columns,
        used_field_ids=used_field_ids,
        multi_entry=multi_entry,
    )


def _derive_column_id(
    field: FormField,
    section_id: str,
    existing: Set[str],
    *,
    preferred_id: Optional[str] = None,
) -> str:
    if preferred_id:
        base = _slugify(preferred_id)
    else:
        base = field.id
        if base.startswith(section_id + "_"):
            base = base[len(section_id) + 1 :]

        base = re.sub(r"^child_\d+_", "", base)
        base = re.sub(r"_child_\d+_", "_", base)
        base = re.sub(r"_child_\d+$", "", base)
        base = re.sub(r"_(\d+)$", "", base)
        base = base.replace('__', '_')
        base = base.strip('_') or field.id

    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


TABLE_NAME_HINTS: List[Tuple[str, str, str]] = [
    ("part_a_ii", "child", "Your Children"),
    ("supplement_a", "child", "Additional Children"),
]


def _infer_table_metadata(
    section_id: str,
    columns: Sequence[TableColumn],
) -> Tuple[str, str, str]:
    """Infer table ID, name, and spoken name from section and column patterns."""

    column_ids = {col.id for col in columns if col.id}
    if section_id.startswith("part_a_ii") and "include_in_application" in column_ids:
        return ("part_a_ii_children_table", "Your Children", "children")
    if section_id.startswith("supplement_a") and "include_in_application" in column_ids:
        return ("supplement_a_children_table", "Additional Children", "children")

    labels_text = " ".join(col.label.lower() for col in columns)
    for section_hint, keyword, nice_name in TABLE_NAME_HINTS:
        if section_hint in section_id and keyword in labels_text:
            spoken = "children" if "child" in keyword else keyword
            return (
                f"{section_id}_children_table",
                nice_name,
                spoken,
            )

    # Fallback: use the section id as base.
    fallback_name = columns[0].label if columns else section_id.replace('_', ' ').title()
    spoken = fallback_name.split()[0].lower()
    return (f"{section_id}_table", fallback_name, spoken)


def _build_multi_entry_config(
    section_id: str,
    rows: Sequence[int],
    columns: Sequence[TableColumn],
) -> MultiEntryConfig:
    """Build multi-entry configuration using heuristic rules based on section patterns."""

    min_entries = 0
    initial_rows = len(rows)
    overflow_instruction = None
    overflow_to_supplement = None
    add_button_label = None

    if section_id.startswith("part_a_ii"):
        add_button_label = "Add Child"
        overflow_instruction = "Use Supplement A for additional children."
        # form_models.py SupplementType now exposes a single TYPE member
        # ("supplement_a"); the old SUPPLEMENT_A name was removed.
        overflow_to_supplement = SupplementType.TYPE
    elif section_id.startswith("supplement_a"):
        add_button_label = "Add Child"

    return MultiEntryConfig(
        min_entries=min_entries,
        initial_rows=initial_rows,
        add_button_label=add_button_label,
        overflow_instruction=overflow_instruction,
        overflow_to_supplement=overflow_to_supplement,
    )
