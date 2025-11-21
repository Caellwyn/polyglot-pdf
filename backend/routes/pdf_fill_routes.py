"""
PDF Filling Routes - Backend endpoint for filling PDFs with form data

Uses PyMuPDF to fill PDF forms (supports XFA and AcroForm).
Stateless: receives data → fills PDF → returns bytes (no storage).
"""
from typing import Any, Dict, Optional
import os
import tempfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import fitz  # PyMuPDF
import structlog

from backend.services.form_kits import (
	FormKitNotFound,
	FormKitStoreError,
	get_form_kit_store,
)

_log = structlog.get_logger().bind(module="pdf_fill_routes")

router = APIRouter(prefix="/api", tags=["pdf"])


class PDFFillRequest(BaseModel):
	"""Request to fill a PDF with form values"""

	kit_id: str = Field(..., description="Form kit identifier (matches manifest entry)")
	pdf_filename: str = Field(..., description="PDF filename (e.g., 'i-90.pdf')")
	field_values: Dict[str, Any] = Field(..., description="Field ID → value mapping from schema")
	form_schema: Dict[str, Any] = Field(..., description="Full schema with pdf_field_name mappings")


@router.post("/fill-pdf")
async def fill_pdf(request: PDFFillRequest) -> Response:
	"""Fill a PDF form with provided values using PyMuPDF."""

	store = get_form_kit_store()
	_log.info(
		"pdf_fill_request",
		kit=request.kit_id,
		pdf=request.pdf_filename,
		field_count=len(request.field_values),
	)

	# DEBUG: Log first 5 field values to verify data is coming through
	if request.field_values:
		sample_values = dict(list(request.field_values.items())[:5])
		_log.info("pdf_fill_sample_values", kit=request.kit_id, sample=sample_values)

	try:
		pdf_bytes = await store.load_pdf_bytes(request.kit_id, request.pdf_filename)
	except FormKitNotFound as exc:
		_log.error("kit_pdf_not_found", kit=request.kit_id, pdf=request.pdf_filename, error=str(exc))
		raise HTTPException(status_code=404, detail=str(exc)) from exc
	except FormKitStoreError as exc:
		_log.error("kit_pdf_load_failed", kit=request.kit_id, pdf=request.pdf_filename, error=str(exc))
		raise HTTPException(status_code=502, detail="Unable to load PDF for requested kit") from exc

	doc = None
	temp_path = None

	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		_log.info("pdf_loaded", kit=request.kit_id, pages=doc.page_count)

		field_mappings: Dict[str, str] = {}
		field_lookup: Dict[str, Dict[str, Any]] = {}
		for field in request.form_schema.get("fields", []):
			field_id = field.get("id")
			if not field_id:
				continue
			field_lookup[field_id] = field
			pdf_field_name = field.get("pdf_field_name")
			if pdf_field_name:
				field_mappings[field_id] = pdf_field_name

		_log.info("field_mappings_built", kit=request.kit_id, mapping_count=len(field_mappings))

		def get_button_on_state(widget) -> str:
			"""Derive the 'on' appearance state for a checkbox/radio widget."""
			try:
				states = widget.button_states()
				if states and "normal" in states:
					normal_states = states["normal"]
					if isinstance(normal_states, list):
						for state in normal_states:
							if state and state.lower() not in {"off", ""}:
								return state
			except Exception:
				pass
			return "Yes"

		def fill_widget(widget, value, field_type: Optional[str] = None) -> None:
			"""Apply a value to a widget, handling button vs. text fields and XFA forms.

			For XFA forms, we need to use the page-based approach to avoid "Annot is not bound" errors.
			"""
			if widget.field_type == 2 or widget.field_type_string in {"CheckBox", "RadioButton"}:
				if value in {True, "true", "True", "1", 1}:
					target_value = get_button_on_state(widget)
				elif value in {False, "false", "False", "0", 0}:
					target_value = "Off"
				else:
					target_value = str(value)

				try:
					doc.xref_set_key(widget.xref, "V", f"/{target_value}")
					doc.xref_set_key(widget.xref, "AS", f"/{target_value}")
				except Exception:
					widget.field_value = target_value
					try:
						widget.update()
					except Exception:
						pass
			else:
				# For text fields in XFA forms, we need to find the widget's page and update it there
				# This avoids the "Annot is not bound to a page" error
				widget_page = None
				widget_on_page = None

				# Find which page this widget belongs to
				for page_num in range(doc.page_count):
					page = doc[page_num]
					for w in page.widgets() or []:
						if w.xref == widget.xref:
							widget_page = page
							widget_on_page = w
							break
					if widget_on_page:
						break

				if widget_on_page:
					# Update using the widget from the page
					widget_on_page.field_value = str(value)
					try:
						widget_on_page.update()
					except Exception:
						# update() may fail for XFA, but field_value assignment should work
						pass
				else:
					# Fallback: try direct xref manipulation
					try:
						doc.xref_set_key(widget.xref, "V", f"({str(value)})")
					except Exception:
						# Last resort: just set field_value and hope for the best
						widget.field_value = str(value)

		def find_widget(field_name: str):
			"""Find a widget by field name, supporting both exact and partial matches.

			XFA PDFs use full paths like 'form1[0].#subform[0].P1_Line1_AlienNumber[0]'
			while our schema might only have 'P1_Line1_AlienNumber[0]'.
			This function tries exact match first, then partial match (endswith).
			"""
			for page_index in range(doc.page_count):
				page = doc[page_index]
				widgets = page.widgets() or []
				for widget in widgets:
					# Try exact match first
					if widget.field_name == field_name:
						return widget

			# Try partial match (for XFA forms with full paths)
			for page_index in range(doc.page_count):
				page = doc[page_index]
				widgets = page.widgets() or []
				for widget in widgets:
					# Match if the widget's full path ends with our field name
					if widget.field_name and widget.field_name.endswith(field_name):
						return widget

			return None

		def apply_field_flag_changes(widget, conditional_behavior: Optional[Dict[str, Any]]) -> None:
			"""Apply PDF field flag changes if specified in conditional_behavior.

			This handles read-only fields that need to be unlocked for filling.
			The schema specifies which bit to flip in the field flags.
			"""
			if not conditional_behavior:
				return

			# Check if there are PDF field flag changes to apply
			pdf_field_flag_change = conditional_behavior.get("pdf_field_flag_change")
			if not pdf_field_flag_change:
				return

			try:
				# Get current field flags
				current_flags = widget.field_flags
				bit = pdf_field_flag_change.get("bit", 0)
				current_value = pdf_field_flag_change.get("current_value", 1)
				required_value = pdf_field_flag_change.get("required_value", 0)

				# Only flip if current state matches expected
				if (current_flags >> bit) & 1 == current_value:
					# Flip the bit
					if required_value == 0:
						# Clear the bit (make writable)
						new_flags = current_flags & ~(1 << bit)
					else:
						# Set the bit
						new_flags = current_flags | (1 << bit)

					widget.field_flags = new_flags
					widget.update()
					_log.debug(
						"field_flag_changed",
						field_name=widget.field_name,
						bit=bit,
						old_flags=current_flags,
						new_flags=new_flags,
					)
			except Exception as exc:
				_log.warning(
					"field_flag_change_failed",
					field_name=widget.field_name,
					error=str(exc),
				)

		filled_count = 0
		skipped_count = 0
		error_count = 0

		# DEBUG: Track which fields are being processed
		_log.info("pdf_fill_start", kit=request.kit_id, total_values=len(request.field_values))

		for field_id, value in request.field_values.items():
			if value is None or value == "":
				_log.debug("field_empty_skipped", kit=request.kit_id, field_id=field_id)
				skipped_count += 1
				continue

			field_obj = field_lookup.get(field_id)
			if not field_obj:
				_log.warning("field_not_in_schema", kit=request.kit_id, field_id=field_id)
				skipped_count += 1
				continue

			field_type = field_obj.get("type", "text")
			_log.debug("processing_field", kit=request.kit_id, field_id=field_id, field_type=field_type, has_value=bool(value))

			if field_type == "radio":
				options = field_obj.get("options", []) or []
				selected_option = next((opt for opt in options if opt.get("value") == value), None)
				if not selected_option:
					_log.warning("radio_option_not_found", kit=request.kit_id, field_id=field_id, value=value)
					skipped_count += 1
					continue

				field_filled = False
				for option in options:
					option_pdf_field = option.get("pdf_field_name")
					if not option_pdf_field:
						continue

					widget = find_widget(option_pdf_field)
					if not widget:
						continue

					is_selected = option.get("value") == value
					try:
						# Apply field flag changes if needed (e.g., unlock read-only fields)
						conditional_behavior = field_obj.get("conditional_behavior")
						apply_field_flag_changes(widget, conditional_behavior)

						fill_widget(widget, is_selected, field_type="radio")
						if is_selected:
							field_filled = True
							filled_count += 1
							_log.debug(
								"radio_selected",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=option_pdf_field,
								value=value,
							)
					except Exception as exc:
						_log.error(
							"radio_fill_error",
							kit=request.kit_id,
							field_id=field_id,
							pdf_field=option_pdf_field,
							error=str(exc),
						)
						error_count += 1

				if not field_filled:
					_log.warning("radio_widget_not_found", kit=request.kit_id, field_id=field_id)
					skipped_count += 1

			elif field_type == "checkbox":
				if isinstance(value, bool):
					pdf_field_name = field_obj.get("pdf_field_name")
					if not pdf_field_name:
						_log.warning("checkbox_no_pdf_mapping", kit=request.kit_id, field_id=field_id)
						skipped_count += 1
						continue

					widget = find_widget(pdf_field_name)
					if not widget:
						_log.warning("checkbox_widget_missing", kit=request.kit_id, field_id=field_id)
						skipped_count += 1
						continue

					try:
						# Apply field flag changes if needed (e.g., unlock read-only fields)
						conditional_behavior = field_obj.get("conditional_behavior")
						apply_field_flag_changes(widget, conditional_behavior)

						fill_widget(widget, value, field_type="checkbox")
						filled_count += 1
					except Exception as exc:
						_log.error(
							"checkbox_fill_error",
							kit=request.kit_id,
							field_id=field_id,
							error=str(exc),
						)
						error_count += 1

				elif isinstance(value, list):
					options = field_obj.get("options", []) or []
					for selected_value in value:
						selected_option = next((opt for opt in options if opt.get("value") == selected_value), None)
						if not selected_option:
							_log.warning(
								"checkbox_option_not_found",
								kit=request.kit_id,
								field_id=field_id,
								value=selected_value,
							)
							continue

						option_pdf_field = selected_option.get("pdf_field_name")
						if not option_pdf_field:
							_log.warning(
								"checkbox_option_no_pdf_mapping",
								kit=request.kit_id,
								field_id=field_id,
								value=selected_value,
							)
							continue

						widget = find_widget(option_pdf_field)
						if not widget:
							_log.warning(
								"checkbox_widget_not_found",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=option_pdf_field,
							)
							continue

						try:
							# Apply field flag changes if needed (e.g., unlock read-only fields)
							conditional_behavior = field_obj.get("conditional_behavior")
							apply_field_flag_changes(widget, conditional_behavior)

							fill_widget(widget, True, field_type="checkbox")
							filled_count += 1
							_log.debug(
								"checkbox_group_filled",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=option_pdf_field,
								value=selected_value,
							)
						except Exception as exc:
							_log.error(
								"checkbox_group_fill_error",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=option_pdf_field,
								error=str(exc),
							)
							error_count += 1
				else:
					_log.warning("checkbox_unsupported_value", kit=request.kit_id, field_id=field_id, value=value)
					skipped_count += 1

			else:
				pdf_field_name = field_mappings.get(field_id)
				if not pdf_field_name:
					_log.warning("text_field_no_mapping", kit=request.kit_id, field_id=field_id)
					skipped_count += 1
					continue

				widget = find_widget(pdf_field_name)
				if not widget:
					_log.warning("text_widget_not_found", kit=request.kit_id, field_id=field_id, pdf_field_name=pdf_field_name)
					skipped_count += 1
					continue

				try:
					# Apply field flag changes if needed (e.g., unlock read-only fields)
					conditional_behavior = field_obj.get("conditional_behavior")
					apply_field_flag_changes(widget, conditional_behavior)

					fill_widget(widget, value, field_type=field_type)
					filled_count += 1
					_log.debug("text_field_filled", kit=request.kit_id, field_id=field_id, pdf_field=widget.field_name, value_length=len(str(value)))
				except Exception as exc:
					_log.error(
						"field_fill_error",
						kit=request.kit_id,
						field_id=field_id,
						error=str(exc),
					)
					error_count += 1

		_log.info(
			"fill_complete",
			kit=request.kit_id,
			filled=filled_count,
			skipped=skipped_count,
			errors=error_count,
		)

		try:
			doc.need_appearances(True)
			_log.info("need_appearances_set", kit=request.kit_id, value=True)
		except Exception as exc:
			_log.warning("need_appearances_failed", kit=request.kit_id, error=str(exc))

		with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
			temp_path = tmp_file.name

		try:
			doc.save(
				temp_path,
				garbage=4,
				clean=True,
				deflate=True,
				incremental=False,
				expand=255,
			)
			doc.close()
			doc = None

			with open(temp_path, "rb") as file_obj:
				filled_pdf_bytes = file_obj.read()
		finally:
			if temp_path and os.path.exists(temp_path):
				os.remove(temp_path)
				temp_path = None

		_log.info("pdf_generated", kit=request.kit_id, size_kb=len(filled_pdf_bytes) // 1024)

		return Response(
			content=filled_pdf_bytes,
			media_type="application/pdf",
			headers={
				"Content-Disposition": f"attachment; filename={request.pdf_filename}",
				"Content-Length": str(len(filled_pdf_bytes)),
			},
		)

	except HTTPException:
		raise
	except Exception as exc:
		_log.error("pdf_fill_failed", kit=request.kit_id, pdf=request.pdf_filename, error=str(exc))
		raise HTTPException(status_code=500, detail=f"PDF filling failed: {exc}") from exc
	finally:
		if doc is not None and not doc.is_closed:
			doc.close()
		if temp_path and os.path.exists(temp_path):
			os.remove(temp_path)
