"""
PDF Schema Extractor
This module extracts form schema information from a PDF file.
"""

import fitz  # PyMuPDF
from datetime import datetime
import json
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
)
import re
from collections import defaultdict


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
                            section_id = f"section_{section_order}"
                            section_label = full_line_text.replace("(continued)", "").strip()
                            
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

            # Sanitize the field name to create a cleaner ID
            clean_id = re.sub(r'\[\d+\]', '', field.field_name) # Remove array-like indices
            clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_id) # Replace special chars with underscore
            clean_id = clean_id.strip('_')

            form_field = FormField(
                id=clean_id,
                name=field.field_label or field.field_name,
                spoken_name=field.field_label or field.field_name,
                type=field_type,
                options=options,
                pdf_position=PDFPosition(
                    page=page_num + 1,
                    x=field.rect.x0,
                    y=field.rect.y0,
                    width=field.rect.width,
                    height=field.rect.height,
                ),
                pdf_field_name=field.field_name,
                section_id=final_section_id,
                section_label=field_section_label.replace("(continued)", "").strip(),
            )
            fields.append(form_field)
            
    # Add field ids to the consolidated section's field list
    for field in fields:
        for section_data in all_sections_temp:
            if section_data["id"] == field.section_id:
                if field.id not in section_data["fields"]:
                    section_data["fields"].append(field.id)
                break

    # --- Radio Button Grouping ---
    grouped_fields = []
    radio_groups = defaultdict(list)
    
    # First, separate radio buttons from other fields
    for field in fields:
        if field.type == FieldType.RADIO:
            # Group radio buttons by their original PDF field name
            radio_groups[field.pdf_field_name].append(field)
        else:
            grouped_fields.append(field)

    # Now, process each radio group
    for pdf_field_name, radio_buttons in radio_groups.items():
        if not radio_buttons:
            continue

        # Sort buttons to have a consistent order (by y, then x position)
        radio_buttons.sort(key=lambda f: (f.pdf_position.page, f.pdf_position.y, f.pdf_position.x))
        
        # The first button will be the basis for the new grouped field
        base_field = radio_buttons[0]

        # Create options from the individual radio buttons
        options = []
        for i, button in enumerate(radio_buttons):
            # The value for a radio option is often its index or a specific export value.
            # Here, we'll use the button's own unique name part as a simple value.
            # A more robust solution might need to inspect export values from the PDF.
            option_value = button.name.split('.')[-1].strip()
            options.append(FieldOption(
                value=option_value,
                label=button.name, # The full tooltip
                spoken_label=button.name
            ))

        # Create a single new FormField for the entire radio group
        grouped_radio_field = FormField(
            id=base_field.id,
            name=base_field.name, # This might need refinement to find a common name
            spoken_name=base_field.spoken_name,
            type=FieldType.RADIO,
            options=options,
            section_id=base_field.section_id,
            section_label=base_field.section_label,
            pdf_position=base_field.pdf_position, # Position of the first button
            pdf_field_name=pdf_field_name,
            group_kind=GroupKind.RADIO,
        )
        grouped_fields.append(grouped_radio_field)

        # Update the section's field list: remove individuals, add the group
        for section_data in all_sections_temp:
            if section_data["id"] == base_field.section_id:
                # Remove individual button IDs
                for button in radio_buttons:
                    if button.id in section_data["fields"]:
                        section_data["fields"].remove(button.id)
                # Add the new group ID
                if grouped_radio_field.id not in section_data["fields"]:
                    section_data["fields"].append(grouped_radio_field.id)
                break


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


    metadata = doc.metadata
    form_metadata = FormMetadata(
        title=metadata.get("title", pdf_path),
        version="1.0", # Placeholder
        page_count=doc.page_count,
        # Other metadata fields can be extracted if available
    )

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
