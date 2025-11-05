"""
PDF Filling Routes - Backend endpoint for filling PDFs with form data

Uses PyMuPDF to fill PDF forms (supports XFA and AcroForm).
Stateless: receives data → fills PDF → returns bytes (no storage).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Dict, Any
import fitz  # PyMuPDF
from pathlib import Path
import structlog
import tempfile
import os

_log = structlog.get_logger().bind(module="pdf_fill_routes")

router = APIRouter(prefix="/api", tags=["pdf"])


class PDFFillRequest(BaseModel):
    """Request to fill a PDF with form values"""
    pdf_filename: str = Field(..., description="PDF filename (e.g., 'i-90.pdf')")
    field_values: Dict[str, Any] = Field(..., description="Field ID → value mapping from schema")
    form_schema: Dict[str, Any] = Field(..., description="Full schema with pdf_field_name mappings")


@router.post("/fill-pdf")
async def fill_pdf(request: PDFFillRequest) -> Response:
    """
    Fill a PDF form with provided values using PyMuPDF.

    Flow:
    1. Load PDF from disk (pdf_schema_extractor/test_schemas/test_pdfs/...)
    2. Map schema field IDs → PDF field names (using schema.fields[].pdf_field_name)
    3. Fill PDF fields with provided values
    4. Return filled PDF as bytes

    Args:
        request: PDF filename, field values, and schema

    Returns:
        PDF bytes with Content-Disposition header for download

    Raises:
        HTTPException: If PDF not found or filling fails
    """
    _log.info("pdf_fill_request",
             pdf=request.pdf_filename,
             field_count=len(request.field_values))

    # Construct PDF path
    # Expected: pdf_schema_extractor/test_schemas/test_pdfs/{form}/{filename}
    form_name = request.pdf_filename.replace('.pdf', '')  # e.g., "i-90"
    pdf_path = Path(f"pdf_schema_extractor/test_schemas/test_pdfs/{form_name}/{request.pdf_filename}")

    if not pdf_path.exists():
        _log.error("pdf_not_found", path=str(pdf_path))
        raise HTTPException(status_code=404, detail=f"PDF not found: {request.pdf_filename}")

    try:
        # Open PDF with PyMuPDF
        doc = fitz.open(str(pdf_path))
        _log.info("pdf_loaded", pages=len(doc))

        # Build field mappings and lookup
        field_mappings = {}  # field_id → pdf_field_name (for text fields)
        field_lookup = {}    # field_id → full field object (for radio/checkbox)

        for field in request.form_schema.get('fields', []):
            field_id = field.get('id')
            if not field_id:
                continue

            field_lookup[field_id] = field
            pdf_field_name = field.get('pdf_field_name')
            if pdf_field_name:
                field_mappings[field_id] = pdf_field_name

        _log.info("field_mappings_built", mapping_count=len(field_mappings))

        # Helper function to get button "on" state
        def get_button_on_state(widget) -> str:
            """Extract the 'on' state from a button widget's button_states()"""
            try:
                states = widget.button_states()
                if states and 'normal' in states:
                    normal_states = states['normal']
                    if isinstance(normal_states, list):
                        # Find the first non-Off, non-empty state
                        for state in normal_states:
                            if state and state.lower() not in ['off', '']:
                                return state
            except:
                pass
            # Fallback to common values
            return 'Yes'

        # Helper function to fill a widget
        def fill_widget(widget, value, field_type: str = None):
            """Fill a widget with appropriate value based on field type"""
            # Check if this is a button field (checkbox/radio)
            # Type 2 = PDF_WIDGET_TYPE_CHECKBOX (includes both checkboxes and radios in XFA forms)
            if widget.field_type == 2 or widget.field_type_string in ['CheckBox', 'RadioButton']:
                # For buttons, we need to set to the "on" state
                old_value = widget.field_value
                target_value = None

                if value in [True, 'true', 'True', '1', 1]:
                    # Get the actual on-state value from the widget
                    on_state = get_button_on_state(widget)
                    target_value = on_state
                elif value in [False, 'false', 'False', '0', 0]:
                    target_value = 'Off'
                else:
                    # Value might already be the on-state
                    target_value = str(value)

                # For XFA forms, we need to set both /V and /AS keys directly in PDF structure
                # widget.field_value doesn't persist correctly for XFA
                # IMPORTANT: Do NOT call widget.update() after this, as it will overwrite our changes
                try:
                    # Set /V (value) key
                    doc.xref_set_key(widget.xref, "V", f"/{target_value}")
                    # Set /AS (appearance state) key - tells which appearance stream to use
                    doc.xref_set_key(widget.xref, "AS", f"/{target_value}")
                    _log.info("button_set_xref", field=widget.field_name,
                             old=old_value, new=target_value, xref=widget.xref)
                except Exception as e:
                    _log.error("button_set_xref_failed", field=widget.field_name,
                              error=str(e))
                    # Fallback to widget API
                    widget.field_value = target_value
                    widget.update()
            else:
                # Regular text/date/select field
                if isinstance(value, bool):
                    widget.field_value = str(value)
                elif isinstance(value, (int, float)):
                    widget.field_value = str(value)
                else:
                    widget.field_value = str(value)

                # Only call update for non-button fields
                widget.update()

        # Fill fields
        filled_count = 0
        skipped_count = 0
        error_count = 0

        for field_id, value in request.field_values.items():
            # Skip empty values
            if value is None or value == "":
                skipped_count += 1
                continue

            # Get field metadata from schema
            field_obj = field_lookup.get(field_id)
            if not field_obj:
                _log.warning("field_not_in_schema", field_id=field_id)
                skipped_count += 1
                continue

            field_type = field_obj.get('type', 'text')

            # Handle different field types
            if field_type == 'radio':
                # Radio button: value is like "P1_checkbox4[0]"
                # Need to find which option matches and get its pdf_field_name
                selected_option = None
                for option in field_obj.get('options', []):
                    if option.get('value') == value:
                        selected_option = option
                        break

                if not selected_option:
                    _log.warning("radio_option_not_found", field_id=field_id, value=value)
                    skipped_count += 1
                    continue

                pdf_field_name = selected_option.get('pdf_field_name')
                if not pdf_field_name:
                    _log.warning("radio_no_pdf_mapping", field_id=field_id, option=value)
                    skipped_count += 1
                    continue

                # For radio buttons, first set all options in the group to Off
                # then set the selected one to On
                for option in field_obj.get('options', []):
                    option_pdf_field = option.get('pdf_field_name')
                    if not option_pdf_field:
                        continue

                    # Find this option's widget and set to Off (unless it's the selected one)
                    is_selected = (option.get('value') == value)

                    for page_num in range(len(doc)):
                        page = doc[page_num]
                        for widget in page.widgets():
                            if widget.field_name == option_pdf_field:
                                try:
                                    if is_selected:
                                        fill_widget(widget, True, field_type='radio')
                                        filled_count += 1
                                        _log.debug("radio_selected", field_id=field_id,
                                                  pdf_field=option_pdf_field, value=value)
                                    else:
                                        fill_widget(widget, False, field_type='radio')
                                        _log.debug("radio_deselected", field_id=field_id,
                                                  pdf_field=option_pdf_field)
                                except Exception as e:
                                    _log.error("radio_fill_error", field_id=field_id,
                                              pdf_field=option_pdf_field, error=str(e))
                                    error_count += 1
                                break
                        else:
                            continue
                        break

                # Mark as processed
                if filled_count > 0:
                    field_filled = True
                else:
                    _log.warning("radio_widget_not_found", field_id=field_id,
                                pdf_field=pdf_field_name)
                    skipped_count += 1

            elif field_type == 'checkbox':
                # Checkbox: value can be boolean (single) or array (group)
                if isinstance(value, bool):
                    # Single checkbox - use main pdf_field_name
                    pdf_field_name = field_obj.get('pdf_field_name')
                    if not pdf_field_name:
                        _log.warning("checkbox_no_pdf_mapping", field_id=field_id)
                        skipped_count += 1
                        continue

                    field_filled = False
                    for page_num in range(len(doc)):
                        page = doc[page_num]
                        for widget in page.widgets():
                            if widget.field_name == pdf_field_name:
                                try:
                                    fill_widget(widget, value, field_type='checkbox')
                                    field_filled = True
                                    filled_count += 1
                                    break
                                except Exception as e:
                                    _log.error("checkbox_fill_error", field_id=field_id,
                                              pdf_field=pdf_field_name, error=str(e))
                                    error_count += 1
                                    break
                        if field_filled:
                            break

                    if not field_filled:
                        _log.warning("checkbox_widget_not_found", field_id=field_id,
                                    pdf_field=pdf_field_name)
                        skipped_count += 1

                elif isinstance(value, list):
                    # Checkbox group - multiple selections
                    # Each selected value needs to map to a checkbox widget
                    for selected_value in value:
                        # Find the option that matches
                        selected_option = None
                        for option in field_obj.get('options', []):
                            if option.get('value') == selected_value:
                                selected_option = option
                                break

                        if not selected_option:
                            _log.warning("checkbox_option_not_found",
                                        field_id=field_id, value=selected_value)
                            continue

                        pdf_field_name = selected_option.get('pdf_field_name')
                        if not pdf_field_name:
                            # Some checkbox groups might not have individual pdf_field_names
                            # Try using consolidated_widgets or field name pattern
                            _log.warning("checkbox_option_no_pdf_mapping",
                                        field_id=field_id, option=selected_value)
                            continue

                        # Find and check this checkbox
                        field_filled = False
                        for page_num in range(len(doc)):
                            page = doc[page_num]
                            for widget in page.widgets():
                                if widget.field_name == pdf_field_name:
                                    try:
                                        fill_widget(widget, True, field_type='checkbox')
                                        field_filled = True
                                        filled_count += 1
                                        _log.debug("checkbox_group_filled",
                                                  field_id=field_id,
                                                  pdf_field=pdf_field_name,
                                                  value=selected_value)
                                        break
                                    except Exception as e:
                                        _log.error("checkbox_group_fill_error",
                                                  field_id=field_id,
                                                  pdf_field=pdf_field_name,
                                                  error=str(e))
                                        error_count += 1
                                        break
                            if field_filled:
                                break

            else:
                # Text, textarea, date, select, tel - use existing logic
                pdf_field_name = field_mappings.get(field_id)
                if not pdf_field_name:
                    _log.warning("no_pdf_mapping", field_id=field_id)
                    skipped_count += 1
                    continue

                field_filled = False
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    for widget in page.widgets():
                        if widget.field_name == pdf_field_name:
                            try:
                                fill_widget(widget, value, field_type=field_type)
                                field_filled = True
                                filled_count += 1
                                break
                            except Exception as e:
                                _log.error("field_fill_error",
                                         field_id=field_id,
                                         pdf_field=pdf_field_name,
                                         error=str(e))
                                error_count += 1
                                break
                    if field_filled:
                        break

                if not field_filled:
                    _log.warning("field_not_found", field_id=field_id,
                                pdf_field=pdf_field_name)
                    skipped_count += 1

        _log.info("fill_complete",
                 filled=filled_count,
                 skipped=skipped_count,
                 errors=error_count)

        # Set NeedAppearances flag to tell PDF viewers to regenerate form field appearances
        # This is critical for radio buttons and checkboxes to display correctly
        try:
            doc.need_appearances(True)
            _log.info("need_appearances_set", value=True)
        except Exception as e:
            _log.warning("need_appearances_failed", error=str(e))

        # For XFA forms, we need to save to a temp file first, then read it back
        # This ensures all XFA field values are properly written
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            temp_path = tmp_file.name

        try:
            # Save with incremental=False to force full rewrite
            # This should commit all field changes including XFA
            doc.save(
                temp_path,
                garbage=4,          # Maximum garbage collection
                clean=True,         # Clean up unused objects
                deflate=True,       # Compress streams
                incremental=False,  # Full rewrite (important for XFA)
                expand=255          # Expand all object streams
            )
            doc.close()

            # Read the saved PDF back into bytes
            with open(temp_path, 'rb') as f:
                pdf_bytes = f.read()
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

        _log.info("pdf_generated", size_kb=len(pdf_bytes) // 1024)

        # Return PDF with download headers
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={request.pdf_filename}",
                "Content-Length": str(len(pdf_bytes))
            }
        )

    except Exception as e:
        _log.error("pdf_fill_failed", error=str(e), pdf=request.pdf_filename)
        raise HTTPException(status_code=500, detail=f"PDF filling failed: {str(e)}")
