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

        # Build field mapping: schema field_id → pdf_field_name
        field_mappings = {}
        for field in request.form_schema.get('fields', []):
            field_id = field.get('id')
            pdf_field_name = field.get('pdf_field_name')
            if field_id and pdf_field_name:
                field_mappings[field_id] = pdf_field_name

        _log.info("field_mappings_built", mapping_count=len(field_mappings))

        # Fill fields
        filled_count = 0
        skipped_count = 0
        error_count = 0

        for field_id, value in request.field_values.items():
            # Skip empty values
            if value is None or value == "":
                skipped_count += 1
                continue

            # Get PDF field name from schema
            pdf_field_name = field_mappings.get(field_id)
            if not pdf_field_name:
                _log.warning("no_pdf_mapping", field_id=field_id)
                skipped_count += 1
                continue

            # Find and fill the field
            field_filled = False
            for page_num in range(len(doc)):
                page = doc[page_num]
                widgets = page.widgets()

                for widget in widgets:
                    if widget.field_name == pdf_field_name:
                        try:
                            # Convert value to appropriate type
                            if isinstance(value, bool):
                                widget.field_value = value
                            elif isinstance(value, (int, float)):
                                widget.field_value = str(value)
                            else:
                                widget.field_value = str(value)

                            widget.update()
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

            if not field_filled and pdf_field_name:
                _log.debug("field_not_found",
                          field_id=field_id,
                          pdf_field=pdf_field_name)
                skipped_count += 1

        _log.info("fill_complete",
                 filled=filled_count,
                 skipped=skipped_count,
                 errors=error_count)

        # Save to bytes
        pdf_bytes = doc.tobytes()
        doc.close()

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
