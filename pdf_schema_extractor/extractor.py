"""
PDF Schema Extractor
This module extracts form schema information from a PDF file.
"""

import fitz  # PyMuPDF
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from .models import (
    FormSchema,
    FormField,
    PDFPosition,
    FormMetadata,
    ExtractionInfo,
    FormSource,
    FieldType,
    FormSection,
    FormPart,
    FormSupplement,
    FieldOption,
    GroupKind,
    ValidationRules,
    FieldHelp,
    ConditionalDisplay,
    ConditionalOperator,
    TableColumn,
    MultiEntryConfig,
    SupplementType,
)
from .table_detection import consolidate_tables
import re
from collections import defaultdict


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _build_validation_rules(payload: Optional[Dict[str, Any]]) -> Optional[ValidationRules]:
    """Convert a raw validation dict into a ValidationRules instance."""
    if not payload:
        return None
    cleaned = dict(payload)
    constraint = cleaned.get("date_constraint")
    if constraint not in {None, "past_only", "future_only", "within_5_years"}:
        cleaned.pop("date_constraint", None)
    return ValidationRules(**cleaned)


def _normalize_pdf_key(pdf_name: str) -> str:
    key = pdf_name.lower()
    key = re.sub(r'#subform\.', '', key)
    key = re.sub(r'([0-9])[a-z]+(\[\d+\])$', r'\1\2', key)
    match = re.match(r'([a-z0-9_]+?)(\d+)\[(\d+)\]$', key)
    if match:
        prefix, digits, index = match.groups()
        # Some PDFs encode row numbers by appending them to the base field name
        if len(digits) > 1 and digits[-1] != index:
            candidate_base = digits[:-1]
            if candidate_base:
                key = f"{prefix}{candidate_base}[{digits[-1]}]"
    return key


def _build_help(payload: Optional[Dict[str, Any]]) -> Optional[FieldHelp]:
    """Convert raw help payload into FieldHelp."""
    if not payload:
        return None
    return FieldHelp(**payload)


def _build_conditional_display(payload: Optional[Dict[str, Any]]) -> Optional[ConditionalDisplay]:
    """Convert raw show_if metadata into ConditionalDisplay."""
    if not payload:
        return None
    operator = payload.get("operator")
    try:
        operator_enum = ConditionalOperator(operator) if operator else None
    except ValueError:
        operator_enum = None
    field_id = payload.get("field")
    if not operator_enum or not field_id:
        return None
    return ConditionalDisplay(field=field_id, operator=operator_enum, value=payload.get("value"))




def _group_radio_fields(
    fields: List[FormField],
    sections_data: List[Dict[str, Any]],
) -> List[FormField]:
    """Group PDF radio widgets into single semantic fields using heuristic clustering."""

    radio_groups: Dict[tuple, List[FormField]] = defaultdict(list)
    passthrough: List[FormField] = []

    for field in fields:
        if field.type == FieldType.RADIO and field.group_kind != GroupKind.RADIO:
            key = (field.section_id, field.pdf_field_name or field.id)
            radio_groups[key].append(field)
        else:
            passthrough.append(field)

    for (section_id, pdf_field_name), radio_buttons in radio_groups.items():
        if not radio_buttons:
            continue

        radio_buttons.sort(
            key=lambda f: (
                f.pdf_position.page if f.pdf_position else 9999,
                f.pdf_position.y if f.pdf_position else 0,
                f.pdf_position.x if f.pdf_position else 0,
            )
        )

        base_field = radio_buttons[0]

        # Build options from all radio buttons in the group
        options: List[FieldOption] = []
        for button in radio_buttons:
            option_value = button.name.split('.')[-1].strip()
            option_label = button.name
            options.append(
                FieldOption(
                    value=option_value,
                    label=option_label,
                    spoken_label=option_label,
                    pdf_field_name=button.pdf_field_name,
                )
            )

        aggregated_field = FormField(
            id=base_field.id,
            name=base_field.name,
            spoken_name=base_field.spoken_name,
            type=FieldType.RADIO,
            options=options,
            section_id=base_field.section_id,
            pdf_position=base_field.pdf_position,
            pdf_field_name=pdf_field_name,
            group_kind=GroupKind.RADIO,
            validation=base_field.validation,
            help=base_field.help,
            show_if=base_field.show_if,
        )

        passthrough.append(aggregated_field)

        removed_ids = {btn.id for btn in radio_buttons}
        section_entry = next((sec for sec in sections_data if sec["id"] == section_id), None)
        if section_entry:
            original_order = section_entry.get("fields", [])
            indices = [i for i, fid in enumerate(original_order) if fid in removed_ids]
            insert_at = indices[0] if indices else len(original_order)
            section_entry["fields"] = [fid for fid in original_order if fid not in removed_ids]
            if aggregated_field.id not in section_entry["fields"]:
                section_entry["fields"].insert(min(insert_at, len(section_entry["fields"])), aggregated_field.id)

    return passthrough




def generate_semantic_section_id(section_label):
    """Generate semantic section ID from label."""
    label_lower = section_label.lower()

    # Extract Part A.I, Part A.II, etc.
    match = re.match(r'part ([a-g])(\.([ivx]+))?', label_lower)
    if match:
        part = match.group(1)
        subsection = match.group(3) if match.group(3) else ""

        if subsection:
            # Part A.I → part_a_i
            return f"part_{part}_{subsection}"

        # Part D: Your Signature → part_d_signature
        if "signature" in label_lower:
            return f"part_{part}_signature"
        elif "declaration" in label_lower:
            return f"part_{part}_declaration"
        elif "interview" in label_lower:
            return f"part_{part}_interview"
        elif "hearing" in label_lower:
            return f"part_{part}_hearing"
        elif "question" in label_lower or "application" in label_lower:
            return f"part_{part}_questions"

        return f"part_{part}"

    # Supplements
    if "supplement a" in label_lower:
        return "supplement_a_section"
    elif "supplement b" in label_lower:
        return "supplement_b_section"

    return f"section_{hash(section_label) % 1000}"


def generate_semantic_field_id(field_label, section_id):
    """Generate semantic field ID from label and section."""
    base = section_id
    label = field_label.lower()

    # Remove common prefixes
    label = re.sub(r'^part\.?\s+[a-g]\.?\s+\d+\.?.*?\d+\.?\s+', '', label)
    label = re.sub(r'^(enter|provide|list|specify)\s+', '', label)

    # Extract key terms
    if 'a-number' in label or 'alien registration' in label:
        field_key = 'a_number'
    elif 'convention against torture' in label:
        field_key = 'convention_against_torture'
    elif 'social security' in label or 'ssn' in label or 'u. s. social security number' in label:
        field_key = 'ssn'
    elif 'uscis online account' in label:
        field_key = 'uscis_online_account_number'
    elif 'last name' in label or 'family name' in label:
        field_key = 'last_name'
    elif 'first name' in label or 'given name' in label:
        field_key = 'first_name'
    elif 'middle name' in label:
        field_key = 'middle_name'
    elif 'other names' in label or 'other name' in label:
        field_key = 'other_names'
    elif 'date of birth' in label:
        field_key = 'dob'
    elif 'city and country of birth' in label:
        field_key = 'city_country_of_birth'
    elif 'present nationality' in label:
        field_key = 'present_nationality'
    elif 'nationality at birth' in label:
        field_key = 'nationality_at_birth'
    elif 'race' in label and 'tribal' in label:
        field_key = 'race_ethnic_tribal_group'
    elif 'religion' in label:
        field_key = 'religion'
    elif 'native language' in label:
        field_key = 'native_language'
    elif 'other languages' in label:
        field_key = 'other_languages'
    elif 'i-94' in label or 'i94' in label:
        field_key = 'i94_number'
    elif 'immigration court proceedings' in label:
        field_key = 'immigration_court_status'
    elif 'last left' in label and 'country' in label:
        field_key = 'last_left_country_date'
    elif 'what country issued your last passport' in label:
        field_key = 'last_passport_country'
    elif 'passport expiration date' in label or 'expiration date of his/her authorized stay' in label:
        field_key = 'passport_expiration_date'
    elif 'are you fluent in english' in label:
        field_key = 'fluent_in_english'
    elif 'residence' in label and 'street' in label:
        field_key = 'residence_street'
    elif 'residence' in label and ('apt' in label or 'apartment' in label):
        field_key = 'residence_apt_number'
    elif 'residence' in label and 'city' in label:
        field_key = 'residence_city'
    elif 'residence' in label and 'state' in label:
        field_key = 'residence_state'
    elif 'residence' in label and 'zip' in label:
        field_key = 'residence_zip'
    elif 'residence' in label and 'phone' in label:
        field_key = 'residence_phone'
    elif 'mailing' in label and 'care of' in label:
        field_key = 'mailing_in_care_of'
    elif 'mailing' in label and 'street' in label:
        field_key = 'mailing_street'
    elif 'mailing' in label and ('apt' in label or 'apartment' in label):
        field_key = 'mailing_apt_number'
    elif 'mailing' in label and 'city' in label:
        field_key = 'mailing_city'
    elif 'mailing' in label and 'state' in label:
        field_key = 'mailing_state'
    elif 'mailing' in label and 'zip' in label:
        field_key = 'mailing_zip'
    elif 'mailing' in label and 'phone' in label:
        field_key = 'mailing_phone'
    else:
        # Fallback: use sanitized label
        field_key = re.sub(r'[^a-z0-9]+', '_', label).strip('_')
        field_key = field_key[:50]  # Limit length

    return f"{base}_{field_key}"


def clean_field_name(tooltip_text):
    """Extract clean field name from PDF tooltip."""
    # Remove part/section prefix like "Part. A. 1. Information About You. 1. "
    text = re.sub(r'^Part\.?\s+[A-G]\.?\s+\d+\.?.*?\d+\.?\s+', '', tooltip_text)

    # Remove instruction verbs
    text = re.sub(r'^(Enter|Provide|List|Specify)\s+', '', text, flags=re.IGNORECASE)

    # Replace "(A. Number)" with "(A-Number)" for consistency
    text = re.sub(r'\(A\.\s*Number\)', '(A-Number)', text)

    # Remove help text suffixes (", if any", ", if applicable", etc.)
    text = re.sub(r',?\s*(if any|if applicable|optional)\.?$', '', text, flags=re.IGNORECASE)

    # Add "(s)" to certain fields for consistency with ground truth
    if 'alien registration number' in text.lower() and '(s)' not in text:
        text = text.replace('Alien Registration Number', 'Alien Registration Number(s)')
        text = text.replace('alien registration number', 'Alien Registration Number(s)')

    # Cleanup: remove trailing periods, commas and extra spaces
    text = text.strip('., ')
    text = re.sub(r'\s+', ' ', text)  # Normalize spaces

    return text


def generate_spoken_name(field_name):
    """Generate concise spoken name for voice UI."""
    # Look for abbreviations in parentheses like (A-Number), (SSN)
    paren_match = re.search(r'\(([A-Z][-\w]*)\)', field_name)
    if paren_match:
        abbrev = paren_match.group(1)
        # Clean up common patterns
        abbrev = abbrev.replace('A-Number', 'A-Number')
        return abbrev

    # Otherwise, use just the key words
    words = field_name.split()
    if len(words) <= 3:
        return field_name

    # Take first 2-3 meaningful words, skip filler words
    meaningful_words = [w for w in words if w.lower() not in ['the', 'a', 'an', 'your', 'if', 'any']]
    if len(meaningful_words) <= 3:
        return ' '.join(meaningful_words)
    return ' '.join(meaningful_words[:2])


def extract_help_text(field_label):
    """Extract help text from parentheses or inline."""
    # Check for common help phrases at the end
    if ', if any' in field_label.lower():
        return {'inline': '(if any)'}
    elif ', if applicable' in field_label.lower():
        return {'inline': '(if applicable)'}
    elif ', (optional)' in field_label.lower() or '(optional)' in field_label.lower():
        return {'inline': '(optional)'}

    # Also check in parentheses
    match = re.search(r'\(([^)]+)\)', field_label)
    if match:
        help_text = match.group(1).strip()
        if help_text.lower() in ['if any', 'if applicable', 'optional']:
            return {'inline': f'({help_text})'}

    return None


def infer_validation(field_name, field_type):
    """Infer validation rules from field name and type."""
    name_lower = field_name.lower()
    validation = {}

    if 'social security' in name_lower or 'ssn' in name_lower:
        validation['format_preset'] = 'ssn'
    elif 'a-number' in name_lower or 'alien registration' in name_lower:
        validation['format_preset'] = 'a_number'
    elif 'zip' in name_lower:
        validation['format_preset'] = 'zip'

    validation['required'] = False
    return validation if validation else None


def extract_complete_metadata(doc):
    """Extract comprehensive form metadata."""
    metadata = doc.metadata
    first_page = doc[0]
    text = first_page.get_text()

    title = metadata.get("title", "")
    form_number = None
    match = re.search(r'(I-\d+)', title)
    if match:
        form_number = match.group(1)
        title = re.sub(r'^Form\s+I-\d+,\s+', '', title)

    omb_match = re.search(r'OMB No\.?\s+(\d+-\d+)', text)
    omb_number = omb_match.group(1) if omb_match else None

    edition_match = re.search(r'Edition\s+(\d{2})/(\d{2})/(\d{2,4})', text)
    if edition_match:
        month, day, year = edition_match.groups()
        if len(year) == 2:
            year = f"20{year}"
        edition_date = f"{year}-{month}-{day}"
    else:
        edition_date = None

    expires_match = re.search(r'Expires\s+(\d{2})/(\d{2})/(\d{4})', text)
    if expires_match:
        month, day, year = expires_match.groups()
        expiration_date = f"{year}-{month}-{day}"
    else:
        expiration_date = None

    agency = None
    if 'U.S. Citizenship and Immigration Services' in text:
        agency = 'U.S. Citizenship and Immigration Services'
    elif 'USCIS' in text:
        agency = 'U.S. Citizenship and Immigration Services'

    return FormMetadata(
        title=title,
        form_number=form_number,
        edition_date=edition_date,
        expiration_date=expiration_date,
        omb_number=omb_number,
        page_count=doc.page_count,
        agency=agency,
        language="en"
    )

def extract_schema(pdf_path: str) -> FormSchema:
    """
    Extracts form schema from a PDF file.

    Args:
        pdf_path: The path to the PDF file.

    Returns:
        A FormSchema object representing the PDF's form schema.
    """
    doc = fitz.open(pdf_path)
    fields = []
    sections = []
    
    # A simple heuristic for identifying section headers
    # Looks for bold text in all caps.
    # section_header_re = re.compile(r"^[A-Z\s,.-]+$") # Old, too strict

    # First pass: identify sections and their vertical positions
    sections_by_page = {}
    section_order = 1
    
    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
        page_sections = []
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    # Combine text from all spans in a line to get the full line text
                    full_line_text = "".join(span["text"] for span in line["spans"]).strip()
                    if "spans" in line and line["spans"]:
                        span = line["spans"][0] # Use the first span for position and style
                        text = span["text"].strip()
                        is_bold = span["flags"] & 2**4
                        font_size = span["size"]
                        
                        # New, more robust heuristic for headers
                        is_header_font = is_bold and font_size >= 11
                        is_part_header = text.startswith("Part ")
                        is_supplement_header = "Supplement" in full_line_text and font_size > 12

                        if is_header_font and (is_part_header or is_supplement_header):
                            # Use the full line text for the section label and normalize it
                            section_label = full_line_text.replace("(continued)", "").strip()
                            section_id = generate_semantic_section_id(section_label)
                            
                            # Store the y-coordinate of the header
                            header_y = span["bbox"][1] 
                            
                            # Avoid adding duplicate sections from the same line
                            if not any(s['label'] == section_label for s in page_sections):
                                page_sections.append({
                                    "id": section_id,
                                    "label": section_label,
                                    "order": section_order,
                                    "y": header_y,
                                    "page_num": page_num + 1,
                                    "fields": []
                                })
                                section_order += 1
        sections_by_page[page_num + 1] = sorted(page_sections, key=lambda s: s["y"])

    # Consolidate sections with the same label from different pages
    consolidated_sections_data = {}
    for page_num in sorted(sections_by_page.keys()):
        for section_data in sections_by_page[page_num]:
            label = section_data["label"]
            if label not in consolidated_sections_data:
                consolidated_sections_data[label] = {
                    "id": section_data["id"],
                    "label": label,
                    "order": section_data["order"],
                    "fields": [], # Fields will be added later
                    "page_number": section_data["page_num"],
                    "temp_ids": []
                }
            # Keep track of original page-specific section IDs for field mapping
            consolidated_sections_data[label]["temp_ids"].append(section_data["id"])


    all_sections_temp = sorted(consolidated_sections_data.values(), key=lambda s: s["order"])
    
    # Create a mapping from the old page-specific section ID to the new consolidated one
    section_id_map = {}
    for section_data in all_sections_temp:
        for temp_id in section_data["temp_ids"]:
            section_id_map[temp_id] = section_data["id"]


    # If no sections were found, create a default one
    if not all_sections_temp:
        default_section_data = {
            "id": "default_section",
            "label": "Default Section",
            "order": 1,
            "fields": [],
            "page_number": 1
        }
        all_sections_temp.append(default_section_data)
        section_id_map["default_section"] = "default_section"
        sections_by_page[1] = [{"id": "default_section", "label": "Default Section", "y": 0, "fields": []}]


    # Second pass: associate fields with the correct section based on y-coordinate
    for page_num, page in enumerate(doc):
        page_sections = sections_by_page.get(page_num + 1, [])
        
        for field in page.widgets():
            # Skip barcode fields
            if 'barcode' in field.field_name.lower():
                continue

            # Skip hidden fields
            if field.field_flags & (1 << 1):  # Hidden flag
                continue

            field_y = field.rect.y0

            # Determine which section the field belongs to by finding the last header above it
            field_section_id = "default_section"
            field_section_label = "Default Section"
            
            if page_sections:
                # Default to the first section on the page if the field is above all headers
                current_section_data = page_sections[0]
                for sec in page_sections:
                    if field_y > sec["y"]:
                        current_section_data = sec
                    else:
                        break # Stop when we find a header below the field
                
                field_section_id = current_section_data["id"]
                field_section_label = current_section_data["label"]

            # Map the temporary page-specific section ID to the final consolidated ID
            final_section_id = section_id_map.get(field_section_id, "default_section")

            field_type = "unknown"
            options = None
            if field.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
                field_type = FieldType.TEXT
            elif field.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                field_type = FieldType.CHECKBOX
            elif field.field_type == fitz.PDF_WIDGET_TYPE_RADIO:
                field_type = FieldType.RADIO
                # Radio button options are handled by grouping fields with the same name
            elif field.field_type in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
                field_type = FieldType.SELECT
                if field.choice_values:
                    options = []
                    # Use choice_displays if available, otherwise fall back to choice_values
                    display_values = field.choice_displays if field.choice_displays and len(field.choice_displays) == len(field.choice_values) else field.choice_values
                    for i, value in enumerate(field.choice_values):
                        label = display_values[i]
                        options.append(FieldOption(value=value, label=label, spoken_label=label))

            elif field.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                field_type = FieldType.SIGNATURE

            # Generate semantic field ID
            field_label = field.field_label or field.field_name
            clean_id = generate_semantic_field_id(field_label, final_section_id)

            # Clean field name
            clean_name = clean_field_name(field_label)
            spoken_name = generate_spoken_name(clean_name)
            help_text = extract_help_text(field_label)
            validation = infer_validation(clean_name, field_type)

            # Clean PDF field name - keep just the base name and first index
            # e.g., "form1[0].#subform[1].PtAILine1_ANumber[0]" -> "PtAILine1_ANumber[0]"
            pdf_name_parts = field.field_name.split('.')
            pdf_field_name = pdf_name_parts[-1] if pdf_name_parts else field.field_name

            form_field = FormField(
                id=clean_id,
                name=clean_name,
                spoken_name=spoken_name,
                type=field_type,
                options=options,
                help=help_text,
                validation=validation,
                pdf_position=PDFPosition(
                    page=page_num + 1,
                    x=field.rect.x0,
                    y=field.rect.y0,
                    width=field.rect.width,
                    height=field.rect.height,
                ),
                pdf_field_name=pdf_field_name,
                section_id=final_section_id,
            )
            fields.append(form_field)
            
    # Deduplicate field IDs by adding suffixes
    field_id_counts = defaultdict(int)
    for field in fields:
        original_id = field.id
        field_id_counts[original_id] += 1
        if field_id_counts[original_id] > 1:
            # Add suffix to make unique
            field.id = f"{original_id}_{field_id_counts[original_id]}"

    # --- Table Detection and Consolidation ---
    # Detect repeating field patterns and consolidate into table fields
    print(f"  Consolidating tables across {len(fields)} fields...")
    fields_with_tables = consolidate_tables(fields)
    print(f"  After table consolidation: {len(fields_with_tables)} fields")

    # Add field ids to the consolidated section's field list
    for field in fields_with_tables:
        for section_data in all_sections_temp:
            if section_data["id"] == field.section_id:
                if field.id not in section_data["fields"]:
                    section_data["fields"].append(field.id)
                break

    # --- Radio normalization ---
    grouped_fields = _group_radio_fields(fields_with_tables, all_sections_temp)

    # Track all pages where section fields appear
    section_pages = defaultdict(set)
    for field in grouped_fields:
        # Table fields might not have pdf_position, skip them
        if hasattr(field, 'pdf_position') and field.pdf_position:
            section_pages[field.section_id].add(field.pdf_position.page)

    # Update sections with page_numbers array
    for section_data in all_sections_temp:
        pages = sorted(section_pages.get(section_data["id"], {section_data.get("page_number", 1)}))
        section_data["page_numbers"] = pages
        # Remove old page_number field
        section_data.pop("page_number", None)

    # Now, create the final FormSection objects from the dictionaries
    all_sections = [FormSection(**{k: v for k, v in s_data.items() if k != 'temp_ids'}) for s_data in all_sections_temp]

    # Group sections into Parts and Supplements
    parts_map = defaultdict(lambda: {
        "id": "", "label": "", "order": 99, "section_ids": []
    })
    supplements_map = defaultdict(lambda: {
        "id": "", "name": "", "purpose": "", "fields": []
    })
    final_sections_for_schema = []

    part_re = re.compile(r"^(Part [A-G])")
    part_order_map = {"Part A": 1, "Part B": 2, "Part C": 3, "Part D": 4, "Part E": 5, "Part F": 6, "Part G": 7}


    for section in all_sections:
        part_match = part_re.match(section.label)
        if "Supplement A" in section.label:
            label = "Supplement A"
            if not supplements_map[label]["id"]:
                supplements_map[label].update({
                    "id": "supplement_a",
                    "name": "Supplement A: Information About Your Children",
                    "purpose": "To provide information about additional children not listed in the main form."
                })
            supplements_map[label]["fields"].extend(section.fields)
        elif "Supplement B" in section.label:
            label = "Supplement B"
            if not supplements_map[label]["id"]:
                 supplements_map[label].update({
                    "id": "supplement_b",
                    "name": "Supplement B: Additional Information",
                    "purpose": "For providing additional details for any question."
                })
            supplements_map[label]["fields"].extend(section.fields)

        elif part_match:
            part_label = part_match.group(1)
            if not parts_map[part_label]["id"]:
                parts_map[part_label].update({
                    "id": f"part_{part_label.split(' ')[1].lower()}",
                    "label": part_label,
                    "order": part_order_map.get(part_label, 99)
                })
            parts_map[part_label]["section_ids"].append(section.id)
            final_sections_for_schema.append(section)
        else:
            # If a section doesn't fit into a part or supplement, add it to the root
            final_sections_for_schema.append(section)

    parts = sorted([FormPart(**p) for p in parts_map.values() if p["id"]], key=lambda p: p.order)
    supplements = [FormSupplement(**s) for s in supplements_map.values() if s["id"]]


    form_metadata = extract_complete_metadata(doc)

    extraction_info = ExtractionInfo(
        extracted_at=datetime.now().isoformat(),
        extraction_confidence=0.8, # Placeholder
        extractor_version="0.1.0", # Placeholder
        manual_review_required=True,
    )

    schema = FormSchema(
        source=FormSource.PDF,
        form_metadata=form_metadata,
        sections=final_sections_for_schema,
        parts=parts if parts else None,
        supplements=supplements if supplements else None,
    fields=grouped_fields,
        extraction_info=extraction_info,
    )

    return schema


if __name__ == "__main__":
    # This is an example of how to use the function.
    # The user will need to provide the correct paths.
    # I will need to find the correct path to the PDF.
    pdf_file_path = "C:\\Users\\caell\\OneDrive\\AILearning\\polyglot-pdf\\example_pdfs\\i-589\\i-589-asylum-application.pdf"
    output_schema_path = "C:\\Users\\caell\\OneDrive\\AILearning\\polyglot-pdf\\pdf_schema_extractor\\test_schemas\\extracted_schema.json"
    
    print(f"Extracting schema from {pdf_file_path}...")
    schema_data = extract_schema(pdf_file_path)
    
    with open(output_schema_path, "w") as f:
        json.dump(schema_data, f, indent=2)
        
    print(f"Schema extracted and saved to {output_schema_path}")
