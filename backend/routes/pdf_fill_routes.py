"""
PDF Filling Routes - Backend endpoint for filling PDFs with form data

Uses PyMuPDF to fill PDF forms (supports XFA and AcroForm).
Stateless: receives data -> fills PDF -> returns bytes (no storage).
"""
from typing import Any, Dict, Optional
import os
import re
import tempfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import fitz  # PyMuPDF
import structlog

from backend.routes.form_kit_routes import _safe_kit_id
from backend.services.pdf_structure import (
	StructureMismatch,
	assert_matches_reference,
)
from backend.services.resume_stamp import STAMP_KEY, build_stamp, parse_stamp
from backend.services.auth import require_auth
from backend.services.kit_gates import (
	load_live_metadata,
	require_published,
	require_visible,
)
from backend.services.form_kits import (
	_SAFE_FILENAME_RE,
	FormKitNotFound,
	FormKitStoreError,
	get_form_kit_store,
)

_log = structlog.get_logger().bind(module="pdf_fill_routes")


# Upper bound on a resume upload (bd polyglot-pdf-dft1). The shipped kits are
# ~150KB (W-7) to a few MB filled; 25MB is far above any real saved form and
# far below a size that would hurt to decode. Anything larger is not a saved
# form, and handing it to a PDF parser is a cheap denial vector.
_MAX_RESUME_UPLOAD_BYTES = 25 * 1024 * 1024


def _safe_pdf_filename(pdf_filename: str) -> str:
	"""Return pdf_filename if it is a safe bare filename, else raise HTTP 400.

	Every OTHER {kit_id} route resolves pdf_filename through the manifest (an
	allowlist normalized by form_kits.normalize_manifest at write time) via
	_resolve_kit_filenames -- it never trusts a raw client value. This route is
	the one exception: PDFFillRequest.pdf_filename comes straight from the POST
	body, never through that allowlist, so store.load_pdf_bytes joined it into a
	path/blob-path with no guard at all (bd polyglot-pdf-7hicd, found tracing bd
	polyglot-pdf-xddtl's store-level guard out to its siblings). Same charset as
	form_kits._SAFE_FILENAME_RE (the single source of truth for what a safe
	filename looks like); raises rather than degrading to a default the way
	form_kits.safe_filename does, because there is no legitimate default here --
	the caller asked for a specific file and a substituted one would silently
	return the wrong PDF instead of failing loudly.
	"""
	if ".." in pdf_filename or not _SAFE_FILENAME_RE.fullmatch(pdf_filename):
		raise HTTPException(status_code=400, detail="Invalid pdf filename")
	return pdf_filename


# Characters that terminate or escape a raw PDF /Name token. An on-state
# containing any of these cannot be written via direct xref surgery without
# escaping, so the filler refuses it (bd h76m.17).
_PDF_NAME_UNSAFE = re.compile(r"[\s/#()<>\[\]{}%]")

router = APIRouter(prefix="/api", tags=["pdf"])


class PDFFillRequest(BaseModel):
	"""Request to fill a PDF with form values"""

	kit_id: str = Field(..., description="Form kit identifier (matches manifest entry)")
	pdf_filename: str = Field(..., description="PDF filename (e.g., 'i-90.pdf')")
	field_values: Dict[str, Any] = Field(..., description="Field ID -> value mapping from schema")
	form_schema: Dict[str, Any] = Field(..., description="Full schema with pdf_field_name mappings")
	# RESUME STAMP (bd polyglot-pdf-dft1). Optional: a staff download does not
	# need one, and an older client that does not send it still gets its PDF.
	#
	# The client supplies its own form_session_id, which is fine BECAUSE this
	# value is never trusted for anything: it is a resume HINT written into a
	# file the client already controls, not a credential. Compare the link
	# jti below, which is NOT taken from the body -- that one is read from the
	# verified token, because a client naming someone else's jti would corrupt
	# the aggregation the firm bills from.
	form_session_id: Optional[str] = Field(
		None, description="Client's form session id, stamped into the PDF for resume"
	)


@router.post("/fill-pdf")
async def fill_pdf(request: PDFFillRequest, user: dict = Depends(require_auth)) -> Response:
	"""Fill a PDF form with provided values using PyMuPDF.

	Auth-gated (bd polyglot-pdf-z2is): the request body carries user-entered
	field values (PII/PHI in transit), so this must not be an open endpoint on a
	service deployed --allow-unauthenticated. VFF_DISABLE_AUTH=true (local dev /
	voice harness) bypasses inside require_auth.

	Firm-scoped (bd polyglot-pdf-vy6id, the Opus cross-surface catch on bd
	vccy): this is the FOURTH client-tier kit read -- the caller supplies
	kit_id in the body, and without the visibility gate a POST with a private
	kit_id and empty field_values returned the private kit's blank template
	to any authed user, defeating the invisibility the three form_kit_routes
	reads enforce. Same gates, same 404 denial (existence is the secret).
	"""

	kit_id = _safe_kit_id(request.kit_id)
	pdf_filename = _safe_pdf_filename(request.pdf_filename)

	store = get_form_kit_store()
	_log.info(
		"pdf_fill_request",
		kit=kit_id,
		pdf=pdf_filename,
		field_count=len(request.field_values),
	)

	# Log the field IDs present (never the values -- they are PII/PHI). bd hjo
	if request.field_values:
		sample_field_ids = list(request.field_values.keys())[:5]
		_log.info("pdf_fill_sample_field_ids", kit=kit_id, sample_field_ids=sample_field_ids)

	try:
		meta = await load_live_metadata(store, kit_id)
		require_published(store, kit_id, meta)
		await require_visible(kit_id, meta, user)
		pdf_bytes = await store.load_pdf_bytes(kit_id, pdf_filename)
	except FormKitNotFound as exc:
		_log.error("kit_pdf_not_found", kit=kit_id, pdf=pdf_filename, error=str(exc))
		raise HTTPException(status_code=404, detail=str(exc)) from exc
	except FormKitStoreError as exc:
		_log.error("kit_pdf_load_failed", kit=kit_id, pdf=pdf_filename, error=str(exc))
		raise HTTPException(status_code=502, detail="Unable to load PDF for requested kit") from exc

	doc = None
	temp_path = None

	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		_log.info("pdf_loaded", kit=request.kit_id, pages=doc.page_count)

		# bd polyglot-pdf-h3ac: register each field under its []-alias variant TOO,
		# so a value payload keyed under the other bracket variant still resolves.
		# Gemini inconsistently adds/drops the trailing [] on checkbox-group ids
		# (bd 5k52), so a value can arrive under 'race' while the schema id is
		# 'race[]' (or vice-versa); every FRONTEND reader tries both variants, but
		# this backend lookup was exact-key only -> the field filled BLANK. The
		# frontend got6 dedup (bd polyglot-pdf-got6) exposed this by removing the
		# duplicate schema-id-keyed entry that used to mask it.
		#
		# EXACT-WINS invariant (bd polyglot-pdf-eb4z): a real exact schema id must
		# NEVER resolve to a sibling's alias. We enforce this by collecting the set
		# of real schema ids first, then registering aliases in a SECOND pass that
		# skips any alias key that is itself a real schema id. This is order-
		# independent: if 'x' and 'x[]' are two DISTINCT real fields and 'x' has no
		# pdf_field_name of its own, 'x[]'s alias write for key 'x' is skipped, so
		# field_mappings.get('x') stays absent instead of pointing at x[]'s widget.
		# (field_lookup already had this guarantee -- the real id is written
		# unconditionally in the first pass and the second-pass alias skips it.)
		schema_field_ids = {
			field.get("id")
			for field in request.form_schema.get("fields", [])
			if field.get("id")
		}

		field_mappings: Dict[str, str] = {}
		field_lookup: Dict[str, Dict[str, Any]] = {}
		# Pass 1: every real exact id wins unconditionally.
		for field in request.form_schema.get("fields", []):
			field_id = field.get("id")
			if not field_id:
				continue
			field_lookup[field_id] = field
			pdf_field_name = field.get("pdf_field_name")
			if pdf_field_name:
				field_mappings[field_id] = pdf_field_name
		# Pass 2: register []-alias variants, but only for keys that are NOT
		# themselves real schema ids (so an alias never shadows a real field) and
		# only when the key is still a gap (first alias writer wins the gap).
		for field in request.form_schema.get("fields", []):
			field_id = field.get("id")
			if not field_id:
				continue
			alias_id = field_id[:-2] if field_id.endswith("[]") else field_id + "[]"
			if alias_id in schema_field_ids:
				continue
			if alias_id not in field_lookup:
				field_lookup[alias_id] = field
			pdf_field_name = field.get("pdf_field_name")
			if pdf_field_name and alias_id not in field_mappings:
				field_mappings[alias_id] = pdf_field_name

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

		# AcroForm text-field flag bit 25 (1-based in the spec) = Comb.
		_COMB_FLAG = 1 << 24

		def fit_comb_value(widget, value: str) -> str:
			"""Clear the Comb flag when the value is longer than the widget's cells.

			A Comb text field splits its box into exactly MaxLen cells and prints ONE
			glyph per cell -- there is no cell MaxLen+1. PyMuPDF stores and reads back
			the full string regardless, so an over-long value round-trips perfectly in
			the AcroForm while the RENDERED page silently shows only the first MaxLen
			characters (bd polyglot-pdf-br7t).

			On W-7 that truncated every 4-digit year: date_of_birth is comb-8, so
			'03/14/1990' printed as '03/14/19' -- a wrong date of birth on a filed
			ITIN application, invisible to every value-level check.

			NEVER REWRITES THE VALUE. An earlier cut of this fix also stripped
			formatting punctuation so a value like '123-45-6789' would still fit its
			comb-9 SSN box, which preserved the intended one-digit-per-cell look. Three
			review rounds each found another input where that strip REORDERED meaning
			instead of reformatting it -- '1990-03-14' -> '19900314', '14.03.1990' ->
			'14031990' -- each of which then FIT comb-8 and printed a plausible-looking
			WRONG date (month=19, month=14) in a box captioned 'month / day / year'.
			Every guard added attracted a new separator, because "is this string's
			meaning purely digit ORDER?" is not decidable from the string. So the strip
			is gone: this function now only ever changes APPEARANCE, never the
			characters written, which makes the whole class unreachable by construction
			instead of by enumeration. (A value that then overflows the box WIDTH still
			clips -- bd polyglot-pdf-8i43 -- but a clipped string is visibly incomplete,
			unlike a reordered date that looks correct and gets filed.)

			The accepted cost is cosmetic and REACHABLE, not hypothetical: nothing gates
			the download path (SchemaForm.handleDownloadPDF calls fillPDF with no
			validation), and the two type="date" fields cannot be length-gated at all
			(validateField early-returns to validateDateValue, which never reads
			max_length), so a W-7 date of birth renders un-combed on every UI
			submission. That is the deliberate trade: a mis-rendered SSN or a date
			printed as plain text is visibly odd, whereas a reordered date of birth
			looks right and is filed with the IRS. Restoring the one-digit-per-cell
			look belongs in INPUT normalization, where the field's semantic type is
			known -- never in a rewrite here (bd polyglot-pdf-2ho7, closed won't-do).
			"""
			try:
				maxlen = widget.text_maxlen or 0
				if not (widget.field_flags & _COMB_FLAG) or not maxlen:
					return value
				if len(value) <= maxlen:
					return value
				widget.field_flags = widget.field_flags & ~_COMB_FLAG
				_log.info(
					"comb_relaxed_for_overflow",  # never log the value itself -- bd hjo
					widget_name=widget.field_name, maxlen=maxlen, value_length=len(value),
				)
				return value
			except Exception as e:
				# Never fail a fill over an appearance tweak -- worst case the value
				# renders truncated, which is the pre-fix behavior. Deliberately logs
				# NO widget attribute: reading widget.field_name here could itself
				# raise on the stale weakref that got us into this handler, turning a
				# cosmetic degradation into a failed fill (bd polyglot-pdf-l53i).
				_log.warning("comb_fit_failed", error=str(e))
				return value

		def fill_widget(widget, page, value, field_type: Optional[str] = None) -> None:
			"""Apply a value to a widget using its page reference to avoid weak reference issues.

			CRITICAL: Must pass the page that contains this widget to avoid "weakly-referenced object no longer exists" errors.
			"""
			# Get fresh widget reference from the page (avoids weak reference issues).
			# Match by XREF first: radio KIDS of a shared AcroForm field all carry the
			# SAME field_name (bd h76m.17), so a name-only re-fetch would grab the
			# first sibling instead of the kid the caller selected. Name match stays
			# as the fallback for callers passing a widget from another page snapshot.
			fresh_widget = None
			for w in page.widgets() or []:
				if w.xref == widget.xref:
					fresh_widget = w
					break
			if not fresh_widget:
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
					text_value = str(value)
					# Must precede the assignment: a comb widget prints only MaxLen
					# glyphs, so an over-long value would render truncated even though
					# it stores fine (bd polyglot-pdf-br7t). Returns the value
					# UNCHANGED -- it edits the widget's flags, never the characters.
					text_value = fit_comb_value(fresh_widget, text_value)
					fresh_widget.field_value = text_value
					fresh_widget.update()
					_log.debug("text_field_filled_success", widget_name=fresh_widget.field_name, value_length=len(text_value))
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

		def widget_has_on_state(widget, on_state: str) -> bool:
			"""STRICT membership check: on_state appears in the widget's /AP
			normal states. Unlike get_button_on_state (whose 'Yes' DEFAULT is
			right for single-target fills), a failed/empty appearance table here
			means NOT-a-match -- defaulting would let a broken sibling kid
			masquerade as the target when the real on-state is literally 'Yes'
			(fresh-eyes, bd h76m.17: silent wrong-box selection)."""
			try:
				states = widget.button_states() or {}
				normal = states.get("normal") or []
				return isinstance(normal, list) and on_state in normal
			except Exception:
				return False

		def find_widget_by_state(field_name: str, on_state: str):
			"""Find the radio KID matching an 'on' appearance state (bd h76m.17).

			A true-AcroForm radio group is ONE field name shared by several kid
			widgets, each distinguished only by its on-state (the v2 mapping:
			field-level pdf_field_name + per-option pdf_on_value). Writing the
			state onto the MATCHING kid sets /V and that kid's /AS correctly.
			Falls back to the first name-match so an unexpected appearance table
			still records the field value.

			Returns: tuple of (widget, page) or (None, None)
			"""
			fallback = (None, None)
			for page_index in range(doc.page_count):
				page = doc[page_index]
				for widget in page.widgets() or []:
					name = widget.field_name or ""
					if name == field_name or name.endswith(field_name):
						if fallback == (None, None):
							fallback = (widget, page)
						if widget_has_on_state(widget, on_state):
							return (widget, page)
			return fallback

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
						# v2 shared-field radio kid (bd h76m.17): the option carries
						# only pdf_on_value; the field-level pdf_field_name is the
						# shared AcroForm field. Only the SELECTED option writes --
						# a radio field holds ONE value, so deselected kids need no
						# Off pass (unlike the per-widget style below).
						shared_pdf_field = field_obj.get("pdf_field_name")
						on_state = option.get("pdf_on_value")
						if not shared_pdf_field or not on_state:
							continue
						if option.get("value") != value:
							continue
						# The on-state goes into a RAW /Name token below: refuse
						# PDF-Name-unsafe characters rather than writing a corrupt
						# xref entry (defensive until the authoring-side lint pins
						# the charset; fresh-eyes, bd h76m.17).
						if _PDF_NAME_UNSAFE.search(on_state):
							_log.warning(
								"radio_on_state_unsafe_chars",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=shared_pdf_field,
							)
							continue
						widget, page = find_widget_by_state(shared_pdf_field, on_state)
						if not widget or not page:
							_log.warning(
								"radio_shared_widget_not_found",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=shared_pdf_field,
							)
							continue
						try:
							apply_field_flag_changes(widget, field_obj)
							# Direct xref write instead of fill_widget: the state goes
							# on the KID annotation (V + AS), which is deterministic
							# and avoids PyMuPDF's flaky Widget weakrefs; the viewer
							# regenerates appearances exactly as for the XFA-style
							# checkbox path above.
							doc.xref_set_key(widget.xref, "V", f"/{on_state}")
							doc.xref_set_key(widget.xref, "AS", f"/{on_state}")
							field_filled = True
							filled_count += 1
							_log.debug(
								"radio_selected_shared",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=shared_pdf_field,
								# never log value/on_state pairing to selection -- bd hjo
							)
						except Exception as exc:
							_log.error(
								"radio_fill_error",
								kit=request.kit_id,
								field_id=field_id,
								pdf_field=shared_pdf_field,
								error=str(exc),
							)
							error_count += 1
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

			elif field_type in ("checkbox", "checkbox_group"):
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
				# The v2 checkbox_group TYPE (bd h76m.17) shares this branch: it is
				# the same options-bearing multi-select, explicit in the type
				# instead of inferred from options[]; without this routing a group
				# fell to the scalar path and printed BLANK (v2 forbids the
				# field-level pdf_field_name the scalar path needs).
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
					# Length only -- never the value itself (bd hjo). Equal to the inner
					# text_field_filled_success length by construction: the filler does
					# not rewrite text values.
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

		# RESUME STAMP (bd polyglot-pdf-dft1), written just before save so it
		# lands in the bytes the client keeps. This is what makes the saved PDF
		# a SAVE FILE: the answers are already in the form fields, and this
		# adds the identity needed to resume -- with no server storage, so the
		# stateless-architecture rule holds.
		#
		# The link jti comes from the VERIFIED token, never the body: a client
		# naming someone else's jti would corrupt the per-link aggregation the
		# firm bills from. form_session_id does come from the body, which is
		# safe because it is a hint the client already controls, not a
		# credential (see services/resume_stamp.py).
		#
		# Best-effort: a stamping failure must never cost the client the PDF
		# they just filled. Losing the stamp costs a resume; raising here
		# costs the document.
		try:
			_stamp = build_stamp(
				form_session_id=request.form_session_id,
				kit_id=request.kit_id,
				link_jtis=[user["jti"]] if isinstance(user, dict) and user.get("jti") else None,
				schema_version=(request.form_schema or {}).get("form_metadata", {}).get("version"),
			)
			if _stamp:
				_meta = doc.metadata or {}
				_meta[STAMP_KEY] = _stamp
				doc.set_metadata(_meta)
				_log.info("resume_stamp_written", kit=request.kit_id)
		except Exception as exc:  # noqa: BLE001 -- never lose the PDF over a stamp
			_log.warning("resume_stamp_failed", kit=request.kit_id, error=str(exc))

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
				"Content-Disposition": f"attachment; filename={pdf_filename}",
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


class ResumeUploadRequest(BaseModel):
	"""A client re-opening the PDF they saved earlier (bd polyglot-pdf-dft1)."""

	kit_id: str = Field(..., description="Kit the client is resuming")
	pdf_filename: str = Field(..., description="The kit's PDF filename")
	pdf_base64: str = Field(..., description="The client's saved PDF, base64")


@router.post("/resume-form")
async def resume_form(
	request: ResumeUploadRequest, user: dict = Depends(require_auth)
) -> Dict[str, Any]:
	"""Verify a client's saved PDF and hand back the answers inside it.

	THE UPLOAD IS ATTACKER-CONTROLLED. A client picked this file off their own
	disk, so "it parsed" is not "it is the form we sent them". Before anything
	is read out of it, it must be STRUCTURALLY IDENTICAL to the kit's own form
	-- see services/pdf_structure.py for what that covers and why a literal
	byte match cannot work.

	THE COMPARISON TARGET CARRIES NO CLIENT INPUT. kit_id runs the same gate
	chain as /fill-pdf (require_published + require_visible), and for a client
	link require_visible resolves to the ONE kit that link was minted for --
	so a client cannot aim this at another firm's form, and the reference
	bytes come from our own store.

	Returns the field values found; the client merges them into their form.
	Field values are NEVER logged (PII/PHI).
	"""
	import base64

	kit_id = _safe_kit_id(request.kit_id)
	pdf_filename = _safe_pdf_filename(request.pdf_filename)
	store = get_form_kit_store()

	try:
		uploaded = base64.b64decode(request.pdf_base64, validate=True)
	except Exception as exc:  # noqa: BLE001
		_log.info("resume_upload_undecodable", kit=kit_id)
		raise HTTPException(status_code=400, detail="Unreadable file") from exc

	# Bound the upload. These forms are ~150KB-2MB; anything far larger is not
	# a saved form, and decoding it into a PDF parser is a cheap denial vector.
	if len(uploaded) > _MAX_RESUME_UPLOAD_BYTES:
		_log.warning("resume_upload_too_large", kit=kit_id, size=len(uploaded))
		raise HTTPException(status_code=413, detail="File too large")

	try:
		meta = await load_live_metadata(store, kit_id)
		require_published(store, kit_id, meta)
		await require_visible(kit_id, meta, user)
		reference = await store.load_pdf_bytes(kit_id, pdf_filename)
	except FormKitNotFound as exc:
		raise HTTPException(status_code=404, detail="Not found") from exc
	except FormKitStoreError as exc:
		# The REFERENCE form is what an upload is checked against, so an
		# unreadable one must fail closed with a handled error -- never an
		# unhandled 500, and never by admitting the upload unchecked.
		_log.error("resume_reference_load_failed", kit=kit_id, error=str(exc))
		raise HTTPException(
			status_code=502, detail="Unable to load the form for this kit"
		) from exc

	try:
		assert_matches_reference(uploaded, reference)
	except StructureMismatch as exc:
		# ONE refusal for every structural failure -- wrong form, tampered
		# form, unreadable form. Distinguishing them would tell an attacker
		# which part of their file to fix.
		_log.warning("resume_upload_refused", kit=kit_id, reason=str(exc))
		raise HTTPException(
			status_code=400,
			detail="That file does not match the form you were sent.",
		) from exc

	# The client's answers come back keyed by SCHEMA FIELD ID, never by PDF
	# widget name. The two namespaces are disjoint -- measured on the shipped
	# W-7, ZERO of 53 schema ids equal their pdf_field_name -- so returning
	# widget names would hand the client 23 keys their form has never heard of
	# and restore none of their work.
	try:
		schema = await store.load_schema(kit_id)
	except FormKitNotFound as exc:
		# Same mapping /api/fill-pdf uses (bd polyglot-pdf-sbfk): a MISSING kit
		# is a 404, and an UNREADABLE one is a 502 -- never an unhandled 500
		# that leaks a stack trace to a client trying to recover their work.
		# The two are caught separately because they are different facts, and
		# an earlier version caught only the first while claiming both.
		raise HTTPException(status_code=404, detail="Not found") from exc
	except FormKitStoreError as exc:
		_log.error("resume_schema_load_failed", kit=kit_id, error=str(exc))
		raise HTTPException(
			status_code=502, detail="Unable to load the form for this kit"
		) from exc

	# widget name -> what that widget means.
	#
	# THREE SHAPES, and missing any one loses answers:
	#   direct   -- field.pdf_field_name; the widget holds the value
	#   option   -- options[].pdf_field_name; the widget is ONE choice of a
	#               radio or checkbox_group, and being "on" selects it
	#
	# The option shape covers 21 widgets on the W-7, 75 on the i-90 and 24 on
	# the f1040. Reading only the direct shape lost every box a client ticked.
	#
	# The OPTION entry carries its PARENT field id explicitly. An earlier
	# version looked the parent up by searching for a field containing that
	# option VALUE, which is wrong because values are not unique: 13 values are
	# shared across fields on the i-90 and 3 on the f1040, so answers landed on
	# the wrong field entirely.
	#
	# multi is True for checkbox_group, whose answer is a LIST client-side.
	by_widget: Dict[str, dict] = {}
	for field in (schema or {}).get("fields", []):
		field_id = field.get("id")
		if not isinstance(field_id, str) or not field_id:
			continue
		widget_name = field.get("pdf_field_name")
		if isinstance(widget_name, str) and widget_name:
			by_widget[widget_name] = {"kind": "direct", "field_id": field_id}
		multi = field.get("type") == "checkbox_group"
		for option in field.get("options") or []:
			if not isinstance(option, dict):
				continue
			opt_widget = option.get("pdf_field_name")
			opt_value = option.get("value")
			if isinstance(opt_widget, str) and opt_widget and isinstance(opt_value, str):
				by_widget[opt_widget] = {
					"kind": "option",
					"field_id": field_id,
					"option_value": opt_value,
					"multi": multi,
				}

	doc = None
	try:
		doc = fitz.open(stream=uploaded, filetype="pdf")
		values: Dict[str, Any] = {}
		# checkbox_group answers accumulate: the client stores a LIST.
		multi_values: Dict[str, list] = {}
		# Single-choice fields showing MORE THAN ONE ticked option.
		conflicted: set = set()
		for page in doc:
			for widget in page.widgets():
				name = widget.field_name
				value = widget.field_value

				# RESOLVE THE MAPPING FIRST. The /AS read below was gated on an
				# EXACT key match, but the i-90's widgets match only by suffix
				# -- so the read was skipped for every one of them and 7 real
				# radio answers stayed lost even after the fallback was added.
				# Resolve, then read.
				mapped = by_widget.get(name)
				if not mapped:
					# SUFFIX FALLBACK, mirroring find_widget in the FILL path:
					# XFA PDFs name widgets with a full path
					# ("form1[0].#subform[0].P1_Line1_AlienNumber[0]") while a
					# schema may map the bare leaf. On the i-90 that is ALL 114
					# direct mappings -- 0 exact, 114 suffix-only -- so an
					# exact-key lookup lost every text answer on the only
					# status:complete kit, while the fill path wrote them
					# correctly. Exact wins first, the same precedence
					# find_widget uses.
					mapped = next(
						(m for widget_name, m in by_widget.items()
						 if name.endswith(widget_name)),
						None,
					)
				if not mapped:
					continue

				# A CHECKED BOX HIDES IN /AS, NOT IN field_value. On these XFA
				# forms the fill path writes the on-state to the appearance key
				# and deliberately does not call update(), so /V stays "Off"
				# while /AS holds the on-state -- and PyMuPDF reports
				# field_value as "Off" for a box the client genuinely ticked.
				# Measured through the REAL /api/fill-pdf route.
				if widget.field_type == 2:
					try:
						raw = doc.xref_get_key(widget.xref, "AS")
					except Exception:  # noqa: BLE001 -- a missing key is not an answer
						raw = None
					if raw and raw[0] == "name" and isinstance(raw[1], str):
						# Strip the leading "/" AND surrounding whitespace: the
						# i-90 has on-states like "/ STE " and "/ APT ", so a
						# bare lstrip("/") left " STE " and the emptiness check
						# below discarded it.
						value = raw[1].lstrip("/").strip()

				if not name or not isinstance(value, str) or not value.strip():
					continue

				if mapped["kind"] == "direct":
					if value == "Off":
						continue      # an unchecked box is not an answer
					values[mapped["field_id"]] = value
					continue

				# An OPTION widget. It is selected when it shows ANY state
				# other than Off -- derived from the widget, exactly as the
				# FILL path does (get_button_on_state), rather than from a
				# pdf_on_value key that only the W-7 carries: it is absent
				# from all 75 i-90 and all 24 f1040 option widgets, so
				# requiring it lost every one of their answers.
				if value == "Off":
					continue
				if mapped.get("multi"):
					# checkbox_group answers are a LIST client-side; collapsing
					# to a scalar means a second tick silently replaces the
					# first and the box renders unticked.
					bucket = multi_values.setdefault(mapped["field_id"], [])
					if mapped["option_value"] not in bucket:
						bucket.append(mapped["option_value"])
				else:
					# A single-choice field. A file with SEVERAL options of the
					# same radio ticked is not a valid form state -- our own
					# fill path writes exactly one -- so rather than letting
					# whichever widget came last silently win, drop the field
					# and let the client answer it again. They lose one answer
					# they could not have produced legitimately, instead of
					# resuming with a choice they never made.
					#
					# Not a security boundary: every value here is a real
					# option of the CORRECT field, and a client can only do
					# this to their own draft. It is about not inventing an
					# answer on a legal form.
					previous = values.get(mapped["field_id"])
					if previous is not None and previous != mapped["option_value"]:
						conflicted.add(mapped["field_id"])
					values[mapped["field_id"]] = mapped["option_value"]

		for field_id in conflicted:
			values.pop(field_id, None)
		if conflicted:
			_log.warning("resume_conflicting_options", kit=kit_id,
						 field_count=len(conflicted))
		values.update(multi_values)
		stamp = parse_stamp((doc.metadata or {}).get(STAMP_KEY))
	finally:
		if doc is not None:
			doc.close()

	# Field COUNT only. The values are the client's answers.
	_log.info("resume_upload_accepted", kit=kit_id, field_count=len(values))

	return {
		"kit_id": kit_id,
		"field_values": values,
		"form_session_id": (stamp or {}).get("fsid"),
		"link_jtis": (stamp or {}).get("jtis", []),
	}
