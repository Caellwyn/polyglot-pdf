"""
PDF Filling Routes - Backend endpoint for filling PDFs with form data

Uses PyMuPDF to fill PDF forms (supports XFA and AcroForm).
Stateless: receives data -> fills PDF -> returns bytes (no storage).
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
	field_values: Dict[str, Any] = Field(..., description="Field ID -> value mapping from schema")
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

	# Log the field IDs present (never the values -- they are PII/PHI). bd hjo
	if request.field_values:
		sample_field_ids = list(request.field_values.keys())[:5]
		_log.info("pdf_fill_sample_field_ids", kit=request.kit_id, sample_field_ids=sample_field_ids)

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
				_log.debug("button_states_check", widget_name=widget.field_name, states=states)
				if states and "normal" in states:
					normal_states = states["normal"]
					if isinstance(normal_states, list):
						for state in normal_states:
							if state and state.lower() not in {"off", ""}:
								_log.debug("button_on_state_found", widget_name=widget.field_name, on_state=state)
								return state
			except Exception as e:
				_log.warning("button_states_error", widget_name=widget.field_name, error=str(e))
				pass
			_log.debug("button_on_state_default", widget_name=widget.field_name, default="Yes")
			return "Yes"

		def fill_widget(widget, page, value, field_type: Optional[str] = None) -> None:
			"""Apply a value to a widget using its page reference to avoid weak reference issues.

			CRITICAL: Must pass the page that contains this widget to avoid "weakly-referenced object no longer exists" errors.
			"""
			# Get fresh widget reference from the page (avoids weak reference issues)
			fresh_widget = None
			for w in page.widgets() or []:
				if w.field_name == widget.field_name:
					fresh_widget = w
					break

			if not fresh_widget:
				_log.warning("fresh_widget_not_found", widget_name=widget.field_name)
				return

			if fresh_widget.field_type == 2 or fresh_widget.field_type_string in {"CheckBox", "RadioButton"}:
				if value in {True, "true", "True", "1", 1}:
					target_value = get_button_on_state(fresh_widget)
					_log.debug("checkbox_value_true", widget_name=fresh_widget.field_name)  # never log value -- bd hjo
				elif value in {False, "false", "False", "0", 0}:
					target_value = "Off"
					_log.debug("checkbox_value_false", widget_name=fresh_widget.field_name)  # never log value -- bd hjo
				else:
					target_value = str(value)
					_log.debug("checkbox_value_other", widget_name=fresh_widget.field_name)  # never log value/original_value -- bd hjo

				try:
					# For XFA checkboxes: Set value and AS, but DON'T call update()
					# Let the PDF viewer generate the appearance when opening
					fresh_widget.field_value = target_value
					doc.xref_set_key(fresh_widget.xref, "AS", f"/{target_value}")

					_log.debug("checkbox_filled_success", widget_name=fresh_widget.field_name, xref=fresh_widget.xref)  # never log value -- bd hjo
				except Exception as e:
					_log.error("checkbox_fill_failed", widget_name=fresh_widget.field_name, error=str(e), traceback=True)
					raise
			else:
				# Text field
				try:
					fresh_widget.field_value = str(value)
					fresh_widget.update()
					_log.debug("text_field_filled_success", widget_name=fresh_widget.field_name, value_length=len(str(value)))
				except Exception as e:
					_log.error("text_field_fill_failed", widget_name=fresh_widget.field_name, error=str(e))
					raise

		def find_widget(field_name: str):
			"""Find a widget by field name and return both the widget and its page.

			XFA PDFs use full paths like 'form1[0].#subform[0].P1_Line1_AlienNumber[0]'
			while our schema might only have 'P1_Line1_AlienNumber[0]'.
			This function tries exact match first, then partial match (endswith).

			Returns: tuple of (widget, page) or (None, None)
			"""
			for page_index in range(doc.page_count):
				page = doc[page_index]
				widgets = page.widgets() or []
				for widget in widgets:
					# Try exact match first
					if widget.field_name == field_name:
						return (widget, page)

			# Try partial match (for XFA forms with full paths)
			for page_index in range(doc.page_count):
				page = doc[page_index]
				widgets = page.widgets() or []
				for widget in widgets:
					# Match if the widget's full path ends with our field name
					if widget.field_name and widget.field_name.endswith(field_name):
						return (widget, page)

			return (None, None)

		def apply_field_flag_changes(widget, field_obj: Optional[Dict[str, Any]]) -> None:
			"""Apply PDF field flag changes for a read-only field that unlocks on fill.

			The schema specifies which bit to flip in the field flags. The unlock
			descriptor (pdf_field_flag_change) is read from conditional_logic FIRST
			-- that is where the I-90 gold actually stores it -- then from
			conditional_behavior as a fallback (bd polyglot-pdf-7a9.16). Previously
			only conditional_behavior was read, where the gold carries just
			unlock_method, so the unlock never fired and read-only fields silently
			stayed locked.
			"""
			if not field_obj:
				return

			# Check both relationship keys for the flag-change descriptor.
			pdf_field_flag_change = None
			for key in ("conditional_logic", "conditional_behavior"):
				container = field_obj.get(key)
				if isinstance(container, dict) and container.get("pdf_field_flag_change"):
					pdf_field_flag_change = container["pdf_field_flag_change"]
					break
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
					_log.warning("radio_option_not_found", kit=request.kit_id, field_id=field_id)  # never log value -- bd hjo
					skipped_count += 1
					continue

				field_filled = False
				for option in options:
					option_pdf_field = option.get("pdf_field_name")
					if not option_pdf_field:
						continue

					widget, page = find_widget(option_pdf_field)
					if not widget or not page:
						continue

					is_selected = option.get("value") == value
					try:
						# Apply field flag changes if needed (e.g., unlock read-only fields)
						apply_field_flag_changes(widget, field_obj)

						fill_widget(widget, page, is_selected, field_type="radio")
						if is_selected:
							field_filled = True
							filled_count += 1
							_log.debug(
								"radio_selected",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=option_pdf_field,
								# never log value -- PII/PHI. bd hjo
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
				_log.debug("checkbox_processing", kit=request.kit_id, field_id=field_id, value_type=type(value).__name__)  # never log value -- bd hjo
				# Defensive shape canonicalization (bd polyglot-pdf-h76m.2): the
				# voice path historically stored a checkbox-GROUP selection as one
				# comma-separated string of option values (config.py "Multiple
				# checkboxes: comma-separated exact values"). The frontend now
				# splits that at the AI ingress, but sessions started before that
				# fix (or stale sessionStorage) can still send the string here --
				# without this split it falls to the unsupported-value branch and
				# the group silently stays empty on the printed PDF. Option values
				# never contain commas (schema contract), so the split is safe.
				# Only options-bearing fields qualify: a standalone checkbox has
				# no options to match the parts against. Boolean-INTENT strings
				# ("true"/"false", the literal forms config.py documents for a
				# standalone checkbox) are excluded: they are not option
				# selections, and routing them into the group branch would trade
				# the accurate checkbox_unsupported_value diagnostic for a
				# misleading checkbox_option_not_found one.
				if (
					isinstance(value, str)
					and value.strip().lower() not in ("true", "false")
					and (field_obj.get("options") or [])
				):
					value = [part.strip() for part in value.split(",") if part.strip()]
				if isinstance(value, bool):
					pdf_field_name = field_obj.get("pdf_field_name")
					if not pdf_field_name:
						_log.warning("checkbox_no_pdf_mapping", kit=request.kit_id, field_id=field_id)
						skipped_count += 1
						continue

					widget, page = find_widget(pdf_field_name)
					if not widget or not page:
						_log.warning("checkbox_widget_missing", kit=request.kit_id, field_id=field_id)
						skipped_count += 1
						continue

					try:
						# Apply field flag changes if needed (e.g., unlock read-only fields)
						apply_field_flag_changes(widget, field_obj)

						fill_widget(widget, page, value, field_type="checkbox")
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
					_log.info("checkbox_group_processing", kit=request.kit_id, field_id=field_id, selected_count=len(value))  # never log selected values -- bd hjo
					options = field_obj.get("options", []) or []
					for selected_value in value:
						selected_option = next((opt for opt in options if opt.get("value") == selected_value), None)
						if not selected_option:
							_log.warning(
								"checkbox_option_not_found",
								kit=request.kit_id,
								field_id=field_id,
								option_count=len(options),  # never log the selected value or the option set -- bd hjo
							)
							continue

						option_pdf_field = selected_option.get("pdf_field_name")
						_log.info("checkbox_option_matched", kit=request.kit_id, field_id=field_id, pdf_field_name=option_pdf_field)  # never log selected_value -- bd hjo
						if not option_pdf_field:
							_log.warning(
								"checkbox_option_no_pdf_mapping",
								kit=request.kit_id,
								field_id=field_id,
								# never log selected_value -- PII/PHI. bd hjo
							)
							continue

						widget, page = find_widget(option_pdf_field)
						if not widget or not page:
							_log.warning(
								"checkbox_widget_not_found",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=option_pdf_field,
							)
							continue

						_log.info("checkbox_widget_found", kit=request.kit_id, field_id=field_id, widget_name=widget.field_name, widget_type=widget.field_type_string)

						try:
							# Apply field flag changes if needed (e.g., unlock read-only fields)
							apply_field_flag_changes(widget, field_obj)

							fill_widget(widget, page, True, field_type="checkbox")
							filled_count += 1
							_log.debug(
								"checkbox_group_filled",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=option_pdf_field,
								# never log selected_value -- PII/PHI. bd hjo
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
					_log.warning("checkbox_unsupported_value", kit=request.kit_id, field_id=field_id, value_type=type(value).__name__)  # never log value -- bd hjo
					skipped_count += 1

			else:
				pdf_field_name = field_mappings.get(field_id)
				if not pdf_field_name:
					_log.warning("text_field_no_mapping", kit=request.kit_id, field_id=field_id)
					skipped_count += 1
					continue

				widget, page = find_widget(pdf_field_name)
				if not widget or not page:
					_log.warning("text_widget_not_found", kit=request.kit_id, field_id=field_id, pdf_field_name=pdf_field_name)
					skipped_count += 1
					continue

				try:
					# Apply field flag changes if needed (e.g., unlock read-only fields)
					apply_field_flag_changes(widget, field_obj)

					fill_widget(widget, page, value, field_type=field_type)
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

		# DON'T set need_appearances for XFA forms - let viewer generate them
		# try:
		# 	doc.need_appearances(True)
		# 	_log.info("need_appearances_set", kit=request.kit_id, value=True)
		# except Exception as exc:
		# 	_log.warning("need_appearances_failed", kit=request.kit_id, error=str(exc))
		_log.info("need_appearances_skipped", kit=request.kit_id, reason="XFA form - viewer will generate")

		with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
			temp_path = tmp_file.name

		try:
			# Save with minimal processing to preserve XFA checkbox appearances
			doc.save(
				temp_path,
				garbage=3,
				deflate=True,
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
