from __future__ import annotations

"""Form kit storage helpers for loading schemas/PDFs in dev and prod."""

import hashlib
import json
import os
import re
import shutil
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import anyio
import structlog

from backend.config import get_settings

_log = structlog.get_logger().bind(module="form_kit_store")

# A schema/pdf filename is kit-CONTROLLED (it comes from metadata.json or
# index.json), so it is untrusted at every layer that turns it into a path: the
# local manifest generator AND the route resolver. Centralize the rule here so
# both call the SAME guard (Codex P1, rounds 3-4 on bd polyglot-pdf-sbfk -- the
# pointwise patches kept missing a variant: a non-string value, or a layer where
# the guard had not been applied yet). A safe filename is a bare single-segment
# name: a str, no separator, no traversal, conservative charset.
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_filename(name: Any, default: str) -> str:
	"""Coerce an untrusted filename to a safe bare filename, else `default`.

	Handles ALL the ways a kit-controlled value can be unsafe in one place: a
	non-string value (123, [], None), a path separator, a `..` traversal, or a
	value outside the conservative charset. Degrades to `default` (the
	conventional name) rather than raising, so one malformed kit neither crashes
	manifest generation nor escapes its own directory.
	"""
	if not isinstance(name, str):
		return default
	if "/" in name or "\\" in name or ".." in name or not _SAFE_FILENAME_RE.fullmatch(name):
		return default
	return name


# The per-kit subdirectory holding SUPERSEDED revisions (bd polyglot-pdf-w3zw).
# Kit storage is one flat slot per kit_id, so republishing used to overwrite the
# schema an old confirmation record points at -- the audit trail could name a
# revision the store could no longer produce. Archived revisions live at
# <kit_id>/_ARCHIVE_DIR/<marker>/, which is INVISIBLE to both catalogues for
# free: `list_kit_files` ignores anything deeper than <kit>/<file> in both
# stores, and the leading underscore is outside _KIT_ID_RE, so an archive dir
# can never be mistaken for a kit.
_ARCHIVE_DIR = "_archive"

# A revision marker is kit-CONTROLLED (an edition_date typed by an author, or a
# computed `sha256:<12hex>`), and it becomes a PATH SEGMENT -- so it is
# untrusted exactly like a filename. It cannot go through `safe_filename`: real
# markers contain characters that guard rejects (a "12/2024" edition date, the
# ":" in a fingerprint). Encode instead of reject, so every marker round-trips:
# any character outside the conservative set becomes "-", which keeps the
# segment a bare, traversal-free name. Distinct markers can collide after
# encoding (12/2024 and 12-2024 both -> "12-2024"); the caller disambiguates
# with the published_at suffix, and retrieval matches on the encoded form, so a
# collision costs an extra sibling directory, never a wrong schema.
_MARKER_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")

# Path segments stay well under filesystem/GCS limits. `sibling_marker` budgets
# the fingerprint against this same cap, so the two must not drift apart.
_MARKER_MAX_LEN = 128


def encode_marker(marker: str) -> str:
	"""Encode a revision marker into a safe single path segment.

	Never raises and never returns an empty or traversal-capable segment: a
	marker that encodes to nothing (or to dots/dashes only) degrades to
	"unmarked", so an archive write always lands somewhere addressable under the
	kit.

	Dot RUNS collapse to a single "-": replacing separators alone already makes
	traversal impossible (the result is one segment, so ".." can never be a path
	component), but leaving a literal ".." inside the name is a trap for the next
	reader -- and for any future code that joins or re-splits these segments.
	Collapse it here so the invariant is visible in the value itself, not just
	in an argument about how the value gets used.
	"""
	encoded = _MARKER_UNSAFE_RE.sub("-", marker or "")
	encoded = re.sub(r"\.{2,}", "-", encoded)
	encoded = encoded[:_MARKER_MAX_LEN]
	if not encoded or set(encoded) <= {".", "-"}:
		return "unmarked"
	return encoded


def sibling_marker(marker: str, fingerprint: str) -> str:
	"""A disambiguated sibling marker that SURVIVES encoding.

	The naive `f"{marker}--{fingerprint}"` is a data-loss bug: `encode_marker`
	truncates at 128 chars, and `edition_date` is unbounded free text, so a long
	marker pushes the fingerprint off the end. At >=128 the sibling then encodes
	IDENTICALLY to the base -- the second revision overwrites the first on disk
	and retrieval hands back the wrong schema. Just under that, the suffix
	survives but mangled, so the reader's fingerprint pattern no longer matches
	it and the sibling becomes invisible (retrieval silently returns only the
	first revision). Both were reproduced live (fresh-eyes on this bead).

	So the fingerprint gets its budget FIRST and the base is trimmed to fit
	around it. Trimming the base can make two long markers collide, but that
	collision is then between DIFFERENT fingerprints, so the segments still
	differ and no revision is lost -- the failure degrades to a less readable
	name, never to overwritten bytes.
	"""
	# Cap the FINGERPRINT first so the base floor below cannot push the result
	# past the segment limit. Without this the floor breaks the very invariant
	# it exists to protect on the one input it was written for -- a pathological
	# (non-sha256) fingerprint would emit an over-long segment.
	encoded_fp = encode_marker(fingerprint)[:max(1, _MARKER_MAX_LEN - 24 - 2)]
	encoded_base = encode_marker(marker)
	# 2 for the "--" join. Leave room for the base tag below.
	base_budget = max(8, _MARKER_MAX_LEN - len(encoded_fp) - 2)
	if len(encoded_base) <= base_budget:
		return f"{encoded_base}--{encoded_fp}"

	# TRIMMING IS LOSSY, so a trimmed base must carry proof of what it came
	# from. Without it the reader can only prefix-match, and two distinct
	# markers sharing the trimmed prefix become indistinguishable -- a record
	# naming one resolves to the other's revision (measured: thousands of
	# cross-matching pairs at these lengths). Appending a short digest of the
	# FULL encoded base makes the trim verifiable: the reader recomputes it
	# from its own marker and compares, so a prefix collision no longer
	# resolves. 8 hex chars of sha256 -- this disambiguates sibling directory
	# names, it is not a security boundary.
	# Digest the RAW marker, not the encoded base: encode_marker itself
	# truncates at the cap, so two markers differing only past that point share
	# an encoded base and a digest over it would still collide.
	tag = hashlib.sha256(marker.encode("utf-8")).hexdigest()[:8]
	head_budget = max(1, base_budget - len(tag) - 1)  # 1 for the "-" join
	return f"{encoded_base[:head_budget]}-{tag}--{encoded_fp}"


def _replace_with_retry(src: "Path", dst: "Path") -> None:
	"""os.replace with a brief retry loop for the WINDOWS transient EACCES.

	On Windows, two threads replacing onto the SAME destination at the same
	instant (or an AV scanner holding it) can raise PermissionError even though
	each replace is individually atomic -- POSIX rename never does this. A few
	short retries absorb the transient; a persistent denial still raises (the
	caller maps it to FormKitStoreError). Seen live: the concurrent double-save
	test failed under full-suite thread contention (bd 92qe.3).
	"""
	for attempt in range(5):
		try:
			os.replace(src, dst)
			return
		except PermissionError:
			if attempt == 4:
				raise
			time.sleep(0.05 * (attempt + 1))


class FormKitStoreError(Exception):
	"""Base exception for form kit loading failures."""


class FormKitNotFound(FormKitStoreError):
	"""Raised when a kit or requested file cannot be located."""


def _safe_str(value: Any, default: str) -> str:
	"""Return `value` if it is a non-empty string, else `default`.

	For untrusted display fields (label) that a downstream typed model requires to
	be a string -- a non-string would otherwise raise a Pydantic/`TypeError` 500.
	"""
	return value if isinstance(value, str) and value else default


def normalize_manifest(raw: Any) -> dict:
	"""Validate + normalize an untrusted manifest into a guaranteed-clean shape.

	THE trust boundary for manifest JSON (bd polyglot-pdf-sbfk). `index.json` (GCS)
	and the synthesized local manifest are both kit-controlled, so every consumer
	(`list_form_kits`, the single-kit resolver) would otherwise have to re-validate
	the shape -- and a missed spot is an uncaught 500. Normalizing ONCE here means
	downstream code can trust the result: a dict with `forms` = list[dict], each
	form's `id`/`label`/`schemaFile`/`pdfFile`/paths a safe string, with
	`schemaFile`/`pdfFile` run through `safe_filename`.

	A structurally-corrupt manifest (top-level not a dict, or `forms` not a list)
	is unreadable -> `FormKitStoreError` (the caller fails closed with 502). A
	non-dict ENTRY inside `forms` is skipped (one bad row can't drop the rest).
	"""
	if not isinstance(raw, dict):
		raise FormKitStoreError(f"Manifest is not an object: {type(raw).__name__}")
	raw_forms = raw.get("forms", [])
	if not isinstance(raw_forms, list):
		raise FormKitStoreError(f"Manifest 'forms' is not a list: {type(raw_forms).__name__}")

	forms = []
	for entry in raw_forms:
		if not isinstance(entry, dict):
			continue  # skip a corrupt non-dict row, don't fail the whole manifest
		kit_id = _safe_str(entry.get("id"), "")
		if not kit_id:
			continue  # an entry with no usable id is unaddressable -> drop it
		schema_file = safe_filename(entry.get("schemaFile") or "schema.json", "schema.json")
		pdf_file = safe_filename(entry.get("pdfFile") or "form.pdf", "form.pdf")
		forms.append({
			"id": kit_id,
			"label": _safe_str(entry.get("label"), kit_id),
			"description": entry.get("description") if isinstance(entry.get("description"), str) else None,
			"schemaFile": schema_file,
			"schemaPath": _safe_str(entry.get("schemaPath"), f"/form-kits/{kit_id}/{schema_file}"),
			"pdfFile": pdf_file,
			"pdfPath": _safe_str(entry.get("pdfPath"), f"/form-kits/{kit_id}/{pdf_file}"),
		})
	return {"forms": forms}


class FormKitStore:
	"""Minimal async interface for loading kit assets."""

	# Whether a MISSING manifest (FormKitNotFound from load_manifest) may fall back
	# to convention-named reads. True for local (the manifest is synthesized from
	# disk, so "missing" just means an empty/absent root -- nothing to leak). False
	# for GCS: a missing index.json (partial deploy, deletion, wrong prefix) must
	# NOT reopen convention reads of unlisted/draft blobs the manifest gate hides
	# (Codex P1, round 5 -- fail closed). Subclasses override.
	allow_convention_fallback: bool = True

	# Whether the PUBLIC read routes must additionally require the kit's LIVE
	# metadata status to be "complete" before serving (Codex P1, PR #279). The
	# deploy-time manifest gate alone is not enough once the store is WRITABLE:
	# a contractor reverting a published kit to draft (to polish it) must
	# unpublish it IMMEDIATELY, else their work-in-progress saves would stream
	# to voice users through the still-listed manifest entry. True for GCS (the
	# shared, editor-writable store). False for local: local mode is ungated by
	# design (drafts are intentionally servable in dev).
	enforce_complete_on_public_reads: bool = False

	async def load_schema(self, kit_id: str, schema_file: str = "schema.json") -> dict:
		raise NotImplementedError

	async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
		raise NotImplementedError

	async def load_manifest(self, manifest_file: str = "index.json") -> dict:
		raise NotImplementedError

	# --- editor write/list surface (bd polyglot-pdf-92qe.1) ------------------
	# The hosted schema-editor needs to SEE drafts (the complete-only manifest
	# hides them by design) and to write schemas/metadata back. These methods are
	# additive -- the read contract above is unchanged and the voice app never
	# calls them.

	async def load_metadata(self, kit_id: str) -> Optional[dict]:
		"""The kit's metadata.json as a dict, or None when absent/unparseable.

		Parse failures degrade to None (not an exception) so one malformed kit
		cannot take down a catalogue listing that reads metadata per kit.
		"""
		raise NotImplementedError

	async def put_metadata(self, kit_id: str, metadata: dict) -> None:
		raise NotImplementedError

	async def put_schema(
		self, kit_id: str, schema: dict, schema_file: str = "schema.json"
	) -> None:
		raise NotImplementedError

	async def put_pdf_bytes(
		self, kit_id: str, data: bytes, pdf_file: str = "form.pdf"
	) -> None:
		"""Write a kit's form PDF (the author-tier onboarding, bd 92qe.3)."""
		raise NotImplementedError

	async def put_json_artifact(
		self, kit_id: str, data: dict, filename: str
	) -> None:
		"""Write a named JSON artifact under a kit (bd polyglot-pdf-v96b, P5.3a).

		The store-with-issues path persists the AcroForm dump (acroform.json) as a
		kit artifact so the dump-only widget-claim lint rule can run at the
		promotion gate and the P5.3c widget picker can list unclaimed widgets.
		filename is sanitized like every other kit filename.
		"""
		raise NotImplementedError

	async def load_json_artifact(self, kit_id: str, filename: str) -> dict:
		"""Read a named JSON artifact under a kit (FormKitNotFound when absent).

		The read mirror of put_json_artifact (bd polyglot-pdf-v96b). A present-but-
		unreadable artifact is a FormKitStoreError (-> 502), an absent one is
		FormKitNotFound (-> the caller treats a missing dump as "no dump available",
		degrading gracefully to the dump-less lint/repair path).
		"""
		raise NotImplementedError

	async def list_kit_files(self) -> dict[str, list[str]]:
		"""Map every kit id to the filenames at its root (one storage listing).

		This is the editor catalogue's source of truth: unlike the manifest it
		includes DRAFT kits, and the filename lists let the caller derive
		hasSchema/hasPdf without a per-file existence probe (expensive on GCS).
		"""
		raise NotImplementedError

	async def list_kit_ids(self) -> list[str]:
		"""Every kit id in the store, drafts included (sorted)."""
		return sorted((await self.list_kit_files()).keys())

	# --- revision archive (bd polyglot-pdf-w3zw) -----------------------------
	# Kit storage is ONE slot per kit_id, so a republish overwrites in place. The
	# confirmation audit trail records kit_id + a revision marker, but a marker is
	# not a storage address -- so before this, replacing a schema destroyed the
	# only copy of what an old record was confirmed against. These methods keep
	# the superseded bytes addressable by that same marker.

	async def put_archived_revision(
		self, kit_id: str, marker: str, schema: dict, metadata: Optional[dict] = None
	) -> None:
		"""Copy a superseded revision's schema (+ metadata) into the archive.

		`marker` is the revision marker resolved from the SUPERSEDED revision's
		own schema, so it matches what that revision's confirmation records
		carry. Implementations encode it into a single safe path segment.
		"""
		raise NotImplementedError

	async def load_archived_revision(self, kit_id: str, marker: str) -> dict:
		"""The archived schema stored under `marker` (FormKitNotFound if absent)."""
		raise NotImplementedError

	async def load_archived_revision_or_none(
		self, kit_id: str, marker: str
	) -> Optional[dict]:
		"""`load_archived_revision`, with absence as None instead of an exception.

		For the "is this revision already archived?" question, where absent is a
		normal answer rather than a failure. A genuine store failure still raises
		FormKitStoreError -- absent and unreadable must stay distinguishable, or
		a transient error would read as "not archived yet" and overwrite.
		"""
		try:
			return await self.load_archived_revision(kit_id, marker)
		except FormKitNotFound:
			return None

	async def list_archived_markers(self, kit_id: str) -> list[str]:
		"""Encoded markers this kit has archived revisions for (sorted).

		Empty for a kit with no archive -- never an error, since "no superseded
		revisions" is the normal state.
		"""
		raise NotImplementedError

	async def load_archived_metadata_or_none(
		self, kit_id: str, marker: str
	) -> Optional[dict]:
		"""The archived revision's metadata.json, or None when absent/unreadable.

		`put_archived_revision` snapshots the kit's metadata alongside the
		schema; its `published_at` is what lets an operator tell two revisions
		apart when one marker names both. Degrades to None (never raises) --
		this only enriches an ambiguity report, so a missing snapshot must not
		turn an honest "cannot tell" into a failure.
		"""
		raise NotImplementedError

	async def delete_kit(self, kit_id: str) -> int:
		"""Remove a kit and EVERYTHING under it, archives included. Returns the
		number of objects removed.

		The store's only destructive operation (bd polyglot-pdf-6x1j) -- every
		other method here creates or reads. The caller is responsible for the
		guard: deletion is refused unless the confirmation record has been
		consulted AND is empty (see confirmation_logger.kit_has_confirmation_
		records, which raises rather than returning False when it cannot check).

		Deleting the archives is the point, not an oversight: a kit with no
		confirmation records has nothing pointing at its superseded revisions,
		so leaving them would strand bytes no record can ever name. A kit WITH
		records must never reach this method.

		Implementations MUST confine the delete to the kit's own prefix -- an
		unvalidated kit_id is a path-traversal vector here in a way it is not
		for a read (bd polyglot-pdf-6x1j).
		"""
		raise NotImplementedError


class LocalFormKitStore(FormKitStore):
	def __init__(self, root: Path):
		self.root = root
		_log.info("form_kits.local_store", root=str(self.root))

	def _kit_dir(self, kit_id: str) -> Path:
		return self.root / kit_id

	async def load_schema(self, kit_id: str, schema_file: str = "schema.json") -> dict:
		kit_dir = self._kit_dir(kit_id)
		path = kit_dir / schema_file
		if not path.exists():
			raise FormKitNotFound(f"Schema not found for {kit_id}: {schema_file}")

		# A present-but-unreadable schema (malformed JSON, an OSError mid-read) is a
		# STORE error, not a missing kit -- wrap it as FormKitStoreError so callers
		# map it to 502, matching GCSFormKitStore.load_schema (bd polyglot-pdf-sbfk
		# / Codex P1: local mode previously leaked these as an uncaught 500).
		try:
			return await anyio.to_thread.run_sync(
				lambda: json.loads(path.read_text(encoding="utf-8"))
			)
		except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
			raise FormKitStoreError(
				f"Invalid or unreadable schema for {kit_id}/{schema_file}: {exc}"
			) from exc

	async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
		kit_dir = self._kit_dir(kit_id)
		path = kit_dir / pdf_filename
		if not path.exists():
			raise FormKitNotFound(f"PDF not found for {kit_id}: {pdf_filename}")

		try:
			return await anyio.to_thread.run_sync(path.read_bytes)
		except OSError as exc:
			raise FormKitStoreError(
				f"Unreadable PDF for {kit_id}/{pdf_filename}: {exc}"
			) from exc

	async def load_manifest(self, manifest_file: str = "index.json") -> dict:
		"""Load manifest from local form-kits directory.

		For local mode, we generate the manifest dynamically by scanning
		the form-kits directory, similar to the frontend script.
		"""
		forms = []
		if not self.root.exists():
			_log.warning("form_kits.local_root_missing_for_manifest", root=str(self.root))
			return normalize_manifest({"forms": forms})

		for kit_dir in self.root.iterdir():
			if not kit_dir.is_dir():
				continue

			kit_id = kit_dir.name

			# A kit may declare custom schema/pdf filenames + a label via
			# metadata.json (the same keys deploy-all.sh and the editor use:
			# bd polyglot-pdf-snpi). normalize_manifest (below) does the type +
			# filename coercion; here we only need a dict to read fields from, so a
			# non-dict metadata.json is treated as absent.
			meta = {}
			meta_path = kit_dir / "metadata.json"
			if meta_path.exists():
				try:
					loaded = json.loads(meta_path.read_text(encoding="utf-8"))
					meta = loaded if isinstance(loaded, dict) else {}
				except (json.JSONDecodeError, OSError, UnicodeDecodeError):
					meta = {}

			# Sanitize the schema name HERE for the on-disk existence probe (the
			# generator reads from disk, so a traversal name must not escape the
			# kit dir even before normalize_manifest re-sanitizes the emitted value).
			schema_file = safe_filename(meta.get("schema") or "schema.json", "schema.json")
			schema_path = kit_dir / schema_file
			if not schema_path.exists():
				continue

			# Label: prefer metadata, else the schema title, else the id. Guard the
			# parsed schema: valid JSON can be a non-dict ([]), and a malformed or
			# unreadable schema must not break GENERATION (its read route surfaces
			# the 502) -- fall back to the id (Codex P1, rounds 4-5).
			label = meta.get("label")
			if not label:
				label = kit_id
				try:
					schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
					if isinstance(schema_data, dict):
						label = schema_data.get("title", kit_id)
				except (json.JSONDecodeError, OSError, UnicodeDecodeError):
					label = kit_id

			pdf_file = safe_filename(meta.get("pdf") or "form.pdf", "form.pdf")
			if not (kit_dir / pdf_file).exists():
				pdf_files = list(kit_dir.glob("*.pdf"))
				if pdf_files:
					pdf_file = pdf_files[0].name

			forms.append({
				"id": kit_id,
				"label": label,
				"description": meta.get("description"),
				"schemaFile": schema_file,
				"schemaPath": f"/form-kits/{kit_id}/{schema_file}",
				"pdfFile": pdf_file,
				"pdfPath": f"/form-kits/{kit_id}/{pdf_file}",
			})

		_log.info("form_kits.local_manifest_generated", count=len(forms))
		# Normalize for shape parity with GCS (and so a future on-disk index.json
		# path would get the same guarantees); the generated rows are already clean.
		return normalize_manifest({"forms": forms})

	# --- editor write/list surface (bd polyglot-pdf-92qe.1) ------------------

	async def load_metadata(self, kit_id: str) -> Optional[dict]:
		path = self._kit_dir(kit_id) / "metadata.json"

		def _read() -> Optional[dict]:
			if not path.exists():
				return None
			try:
				loaded = json.loads(path.read_text(encoding="utf-8"))
			except (json.JSONDecodeError, OSError, UnicodeDecodeError):
				return None
			return loaded if isinstance(loaded, dict) else None

		return await anyio.to_thread.run_sync(_read)

	async def put_metadata(self, kit_id: str, metadata: dict) -> None:
		await self._write_json(self._kit_dir(kit_id) / "metadata.json", metadata)

	async def put_schema(
		self, kit_id: str, schema: dict, schema_file: str = "schema.json"
	) -> None:
		schema_file = safe_filename(schema_file, "schema.json")
		await self._write_json(self._kit_dir(kit_id) / schema_file, schema)

	async def put_pdf_bytes(
		self, kit_id: str, data: bytes, pdf_file: str = "form.pdf"
	) -> None:
		pdf_file = safe_filename(pdf_file, "form.pdf")
		path = self._kit_dir(kit_id) / pdf_file

		def _write() -> None:
			path.parent.mkdir(parents=True, exist_ok=True)
			# Per-write nonce, same reason as _write_json (Codex P1 r2, PR #279):
			# a pid-only temp name collides under two concurrent writes.
			tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
			try:
				tmp.write_bytes(data)
				_replace_with_retry(tmp, path)
			finally:
				if tmp.exists():
					tmp.unlink(missing_ok=True)

		try:
			await anyio.to_thread.run_sync(_write)
		except OSError as exc:
			raise FormKitStoreError(f"Unable to write {pdf_file}: {exc}") from exc

	async def put_json_artifact(
		self, kit_id: str, data: dict, filename: str
	) -> None:
		filename = safe_filename(filename, "artifact.json")
		await self._write_json(self._kit_dir(kit_id) / filename, data)

	async def load_json_artifact(self, kit_id: str, filename: str) -> dict:
		filename = safe_filename(filename, "artifact.json")
		path = self._kit_dir(kit_id) / filename
		if not path.exists():
			raise FormKitNotFound(f"Artifact not found for {kit_id}: {filename}")
		try:
			return await anyio.to_thread.run_sync(
				lambda: json.loads(path.read_text(encoding="utf-8"))
			)
		except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
			raise FormKitStoreError(
				f"Invalid or unreadable artifact for {kit_id}/{filename}: {exc}"
			) from exc

	async def _write_json(self, path: Path, data: dict) -> None:
		"""Atomic JSON write: temp file in the same dir, then os.replace.

		A concurrent reader (the editor re-pulling, the voice app filling) must
		never see a half-written schema -- the same temp+rename discipline the
		dev extraction endpoint uses (extractEndpoint.ts).
		"""

		def _write() -> None:
			path.parent.mkdir(parents=True, exist_ok=True)
			# Per-WRITE unique temp name: the pid alone is constant for the
			# process, so two concurrent saves of the same file would collide on
			# one temp path (one thread clobbers the other's temp; the loser's
			# os.replace then FileNotFoundErrors) -- same lesson as the dev
			# extraction endpoint's request counter (Codex P1 r2, PR #279).
			tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
			try:
				tmp.write_text(
					json.dumps(data, indent=2, ensure_ascii=False) + "\n",
					encoding="utf-8",
				)
				_replace_with_retry(tmp, path)
			finally:
				if tmp.exists():
					tmp.unlink(missing_ok=True)

		try:
			await anyio.to_thread.run_sync(_write)
		except OSError as exc:
			raise FormKitStoreError(f"Unable to write {path.name}: {exc}") from exc

	async def list_kit_files(self) -> dict[str, list[str]]:
		def _scan() -> dict[str, list[str]]:
			if not self.root.exists():
				return {}
			out: dict[str, list[str]] = {}
			for kit_dir in self.root.iterdir():
				if not kit_dir.is_dir():
					continue
				out[kit_dir.name] = sorted(
					f.name for f in kit_dir.iterdir() if f.is_file()
				)
			return out

		try:
			return await anyio.to_thread.run_sync(_scan)
		except OSError as exc:
			raise FormKitStoreError(f"Unable to list form kits: {exc}") from exc

	# --- revision archive (bd polyglot-pdf-w3zw) -----------------------------

	def _archive_dir(self, kit_id: str, marker: str) -> Path:
		return self._kit_dir(kit_id) / _ARCHIVE_DIR / encode_marker(marker)

	async def put_archived_revision(
		self, kit_id: str, marker: str, schema: dict, metadata: Optional[dict] = None
	) -> None:
		target = self._archive_dir(kit_id, marker)
		# Reuse the atomic temp+replace writer: an archive read concurrent with
		# the write must never see half a schema, same as a live one.
		await self._write_json(target / "schema.json", schema)
		if metadata is not None:
			await self._write_json(target / "metadata.json", metadata)

	async def load_archived_revision(self, kit_id: str, marker: str) -> dict:
		path = self._archive_dir(kit_id, marker) / "schema.json"
		if not path.exists():
			raise FormKitNotFound(
				f"No archived revision for {kit_id} at marker {marker}"
			)
		try:
			return await anyio.to_thread.run_sync(
				lambda: json.loads(path.read_text(encoding="utf-8"))
			)
		except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
			raise FormKitStoreError(
				f"Invalid or unreadable archived revision for {kit_id}/{marker}: {exc}"
			) from exc

	async def load_archived_metadata_or_none(
		self, kit_id: str, marker: str
	) -> Optional[dict]:
		path = self._archive_dir(kit_id, marker) / "metadata.json"

		def _read() -> Optional[dict]:
			if not path.exists():
				return None
			try:
				loaded = json.loads(path.read_text(encoding="utf-8"))
			except (json.JSONDecodeError, OSError, UnicodeDecodeError):
				return None
			return loaded if isinstance(loaded, dict) else None

		try:
			return await anyio.to_thread.run_sync(_read)
		except OSError:
			return None

	async def list_archived_markers(self, kit_id: str) -> list[str]:
		root = self._kit_dir(kit_id) / _ARCHIVE_DIR

		def _scan() -> list[str]:
			if not root.exists():
				return []
			return sorted(
				d.name for d in root.iterdir()
				if d.is_dir() and (d / "schema.json").exists()
			)

		try:
			return await anyio.to_thread.run_sync(_scan)
		except OSError as exc:
			raise FormKitStoreError(
				f"Unable to list archived revisions for {kit_id}: {exc}"
			) from exc

	async def delete_kit(self, kit_id: str) -> int:
		kit_dir = self._kit_dir(kit_id)
		root = self.root

		def _remove() -> int:
			# CONTAINMENT FIRST. _kit_dir is a bare join, so a kit_id of "..",
			# "../other", or an absolute path resolves outside the root -- which
			# is harmless for the reads it was written for and catastrophic for
			# a recursive delete. Resolve both sides and require the target to
			# be a strict descendant of the root before removing anything.
			try:
				resolved = kit_dir.resolve()
				resolved_root = root.resolve()
			except OSError as exc:
				raise FormKitStoreError(
					f"Unable to resolve the kit path for {kit_id}: {exc}"
				) from exc
			if resolved == resolved_root or resolved_root not in resolved.parents:
				raise FormKitStoreError(
					f"Refusing to delete outside the form-kits root: {kit_id!r}"
				)
			if not resolved.is_dir():
				raise FormKitNotFound(f"Kit not found: {kit_id}")

			# Count before removing, so the return value describes what was
			# actually there rather than what the caller assumed.
			removed = sum(1 for path in resolved.rglob("*") if path.is_file())
			shutil.rmtree(resolved)
			return removed

		try:
			return await anyio.to_thread.run_sync(_remove)
		except (FormKitNotFound, FormKitStoreError):
			raise
		except OSError as exc:
			raise FormKitStoreError(f"Unable to delete {kit_id}: {exc}") from exc


class GCSFormKitStore(FormKitStore):
	"""Form kit store using authenticated Google Cloud Storage client."""

	# A missing index.json in GCS must NOT fall back to convention reads -- that
	# would reopen unlisted/draft blobs the complete-only manifest gate hides
	# (Codex P1, round 5). Local mode synthesizes its manifest, so it keeps the
	# base default (True).
	allow_convention_fallback: bool = False

	# The shared GCS store is editor-writable (bd 92qe.1), so public reads must
	# honor the LIVE metadata status -- a kit reverted to draft unpublishes
	# immediately instead of serving work-in-progress saves (Codex P1, PR #279).
	enforce_complete_on_public_reads: bool = True

	def __init__(self, bucket_name: str, prefix: Optional[str] = None):
		from google.cloud import storage
		from google.cloud.exceptions import NotFound

		self.bucket_name = bucket_name
		self.prefix = (prefix or "").strip("/")
		self._client = storage.Client()
		self._bucket = self._client.bucket(bucket_name)
		self._not_found_exc = NotFound
		_log.info(
			"form_kits.gcs_store",
			bucket=self.bucket_name,
			prefix=self.prefix or "/",
		)

	def _build_blob_path(self, *parts: str) -> str:
		"""Build GCS blob path from parts."""
		segments = [self.prefix] if self.prefix else []
		segments.extend(p for p in parts if p)
		return "/".join(segments)

	async def _fetch_bytes(self, blob_path: str) -> bytes:
		"""Fetch bytes from GCS blob using authenticated client."""
		def _download():
			blob = self._bucket.blob(blob_path)
			try:
				return blob.download_as_bytes()
			except self._not_found_exc:
				return None

		data = await anyio.to_thread.run_sync(_download)
		if data is None:
			raise FormKitNotFound(f"GCS blob not found: gs://{self.bucket_name}/{blob_path}")
		return data

	async def load_schema(self, kit_id: str, schema_file: str = "schema.json") -> dict:
		blob_path = self._build_blob_path(kit_id, schema_file)
		data = await self._fetch_bytes(blob_path)
		try:
			return json.loads(data.decode("utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError) as exc:
			raise FormKitStoreError(
				f"Invalid schema for {kit_id}/{schema_file}: {exc}"
			) from exc

	async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
		blob_path = self._build_blob_path(kit_id, pdf_filename)
		return await self._fetch_bytes(blob_path)

	async def load_manifest(self, manifest_file: str = "index.json") -> dict:
		"""Load manifest from GCS bucket using authenticated client."""
		blob_path = self._build_blob_path(manifest_file)
		_log.info("form_kits.gcs_manifest_fetch", blob_path=blob_path, bucket=self.bucket_name)

		data = await self._fetch_bytes(blob_path)
		try:
			raw = json.loads(data.decode("utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError) as exc:
			# UnicodeDecodeError too (non-UTF-8 index.json): without it the resolver
			# leaks an uncaught 500 instead of the fail-closed 502 (Codex P1, r4).
			raise FormKitStoreError(f"Invalid manifest at gs://{self.bucket_name}/{blob_path}: {exc}") from exc
		# normalize_manifest validates the SHAPE (a non-object or non-list 'forms'
		# raises FormKitStoreError) so the resolver/list route never see a malformed
		# manifest (Codex P1, round 5).
		return normalize_manifest(raw)

	# --- editor write/list surface (bd polyglot-pdf-92qe.1) ------------------

	async def load_metadata(self, kit_id: str) -> Optional[dict]:
		blob_path = self._build_blob_path(kit_id, "metadata.json")

		def _download() -> Optional[bytes]:
			blob = self._bucket.blob(blob_path)
			try:
				return blob.download_as_bytes()
			except self._not_found_exc:
				return None

		# Wrap NON-NotFound storage failures (transient service errors,
		# permission problems) as FormKitStoreError like every other GCS method:
		# callers catch only FormKitStoreError, so a raw google exception here
		# would surface as an uncaught 500 (Codex P1, PR #279).
		try:
			data = await anyio.to_thread.run_sync(_download)
		except Exception as exc:
			raise FormKitStoreError(
				f"Unable to read gs://{self.bucket_name}/{blob_path}: {exc}"
			) from exc
		if data is None:
			return None
		try:
			loaded = json.loads(data.decode("utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError):
			return None
		return loaded if isinstance(loaded, dict) else None

	async def put_metadata(self, kit_id: str, metadata: dict) -> None:
		await self._upload_json(self._build_blob_path(kit_id, "metadata.json"), metadata)

	async def put_schema(
		self, kit_id: str, schema: dict, schema_file: str = "schema.json"
	) -> None:
		schema_file = safe_filename(schema_file, "schema.json")
		await self._upload_json(self._build_blob_path(kit_id, schema_file), schema)

	async def put_pdf_bytes(
		self, kit_id: str, data: bytes, pdf_file: str = "form.pdf"
	) -> None:
		pdf_file = safe_filename(pdf_file, "form.pdf")
		blob_path = self._build_blob_path(kit_id, pdf_file)

		def _upload() -> None:
			blob = self._bucket.blob(blob_path)
			blob.cache_control = "no-cache"
			blob.upload_from_string(data, content_type="application/pdf")

		try:
			await anyio.to_thread.run_sync(_upload)
		except Exception as exc:
			raise FormKitStoreError(
				f"Unable to write gs://{self.bucket_name}/{blob_path}: {exc}"
			) from exc

	async def put_json_artifact(
		self, kit_id: str, data: dict, filename: str
	) -> None:
		filename = safe_filename(filename, "artifact.json")
		await self._upload_json(self._build_blob_path(kit_id, filename), data)

	async def load_json_artifact(self, kit_id: str, filename: str) -> dict:
		filename = safe_filename(filename, "artifact.json")
		blob_path = self._build_blob_path(kit_id, filename)
		# _fetch_bytes raises FormKitNotFound when the blob is absent (the "no dump
		# stored" signal the caller degrades on) but lets a NON-NotFound google
		# error (ServiceUnavailable/Forbidden/...) propagate RAW. The
		# load_json_artifact contract is graceful degradation -- _load_kit_dump
		# catches only FormKitNotFound/FormKitStoreError, so an unwrapped transient
		# error would 500 the promotion gate (Opus fallback review, PR #323). Wrap
		# it as FormKitStoreError here, matching load_metadata's discipline.
		try:
			data = await self._fetch_bytes(blob_path)
		except FormKitNotFound:
			raise
		except Exception as exc:
			raise FormKitStoreError(
				f"Unable to read gs://{self.bucket_name}/{blob_path}: {exc}"
			) from exc
		try:
			return json.loads(data.decode("utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError) as exc:
			raise FormKitStoreError(
				f"Invalid artifact for {kit_id}/{filename}: {exc}"
			) from exc

	async def _upload_json(self, blob_path: str, data: dict) -> None:
		"""Upload a JSON blob with no-cache so a re-pull after a save is never
		stale (the editor's save->reload round trip)."""

		def _upload() -> None:
			blob = self._bucket.blob(blob_path)
			blob.cache_control = "no-cache"
			blob.upload_from_string(
				json.dumps(data, indent=2, ensure_ascii=False) + "\n",
				content_type="application/json",
			)

		try:
			await anyio.to_thread.run_sync(_upload)
		except Exception as exc:  # google API errors are env-specific; fail closed
			raise FormKitStoreError(
				f"Unable to write gs://{self.bucket_name}/{blob_path}: {exc}"
			) from exc

	async def list_kit_files(self) -> dict[str, list[str]]:
		"""One flat listing under the prefix, grouped into kit_id -> filenames.

		Unlike the manifest this includes DRAFT kits -- exactly what the
		token-gated editor catalogue needs. Blobs nested deeper than
		<prefix>/<kit>/<file> are ignored (kits are flat by convention).
		"""
		base = f"{self.prefix}/" if self.prefix else ""

		def _scan() -> dict[str, list[str]]:
			out: dict[str, list[str]] = {}
			for blob in self._client.list_blobs(self.bucket_name, prefix=base):
				rel = blob.name[len(base):]
				parts = rel.split("/")
				if len(parts) != 2 or not parts[0] or not parts[1]:
					continue  # the manifest itself, folder markers, deep nesting
				out.setdefault(parts[0], []).append(parts[1])
			return {k: sorted(v) for k, v in out.items()}

		try:
			return await anyio.to_thread.run_sync(_scan)
		except Exception as exc:
			raise FormKitStoreError(
				f"Unable to list gs://{self.bucket_name}/{base}: {exc}"
			) from exc

	# --- revision archive (bd polyglot-pdf-w3zw) -----------------------------

	async def put_archived_revision(
		self, kit_id: str, marker: str, schema: dict, metadata: Optional[dict] = None
	) -> None:
		segment = encode_marker(marker)
		await self._upload_json(
			self._build_blob_path(kit_id, _ARCHIVE_DIR, segment, "schema.json"), schema
		)
		if metadata is not None:
			await self._upload_json(
				self._build_blob_path(kit_id, _ARCHIVE_DIR, segment, "metadata.json"),
				metadata,
			)

	async def load_archived_revision(self, kit_id: str, marker: str) -> dict:
		segment = encode_marker(marker)
		blob_path = self._build_blob_path(kit_id, _ARCHIVE_DIR, segment, "schema.json")
		# Same discipline as load_json_artifact: an ABSENT archive is
		# FormKitNotFound (the caller reports "no such revision"), but a transient
		# google error must not escape raw as an uncaught 500.
		try:
			data = await self._fetch_bytes(blob_path)
		except FormKitNotFound:
			raise FormKitNotFound(
				f"No archived revision for {kit_id} at marker {marker}"
			) from None
		except Exception as exc:
			raise FormKitStoreError(
				f"Unable to read gs://{self.bucket_name}/{blob_path}: {exc}"
			) from exc
		try:
			return json.loads(data.decode("utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError) as exc:
			raise FormKitStoreError(
				f"Invalid archived revision for {kit_id}/{marker}: {exc}"
			) from exc

	async def load_archived_metadata_or_none(
		self, kit_id: str, marker: str
	) -> Optional[dict]:
		segment = encode_marker(marker)
		blob_path = self._build_blob_path(
			kit_id, _ARCHIVE_DIR, segment, "metadata.json"
		)

		def _download() -> Optional[bytes]:
			blob = self._bucket.blob(blob_path)
			try:
				return blob.download_as_bytes()
			except self._not_found_exc:
				return None

		try:
			data = await anyio.to_thread.run_sync(_download)
		except Exception:
			return None  # best-effort: enriches a message, never fails the read
		if data is None:
			return None
		try:
			loaded = json.loads(data.decode("utf-8"))
		except (json.JSONDecodeError, UnicodeDecodeError):
			return None
		return loaded if isinstance(loaded, dict) else None

	async def list_archived_markers(self, kit_id: str) -> list[str]:
		base = self._build_blob_path(kit_id, _ARCHIVE_DIR) + "/"

		def _scan() -> list[str]:
			out = set()
			for blob in self._client.list_blobs(self.bucket_name, prefix=base):
				rel = blob.name[len(base):]
				parts = rel.split("/")
				# <marker>/schema.json exactly -- ignore folder markers and any
				# deeper nesting, mirroring list_kit_files' flat-shape rule.
				if len(parts) == 2 and parts[0] and parts[1] == "schema.json":
					out.add(parts[0])
			return sorted(out)

		try:
			return await anyio.to_thread.run_sync(_scan)
		except Exception as exc:
			raise FormKitStoreError(
				f"Unable to list gs://{self.bucket_name}/{base}: {exc}"
			) from exc

	async def delete_kit(self, kit_id: str) -> int:
		if not kit_id or "/" in kit_id or kit_id in (".", ".."):
			raise FormKitStoreError(
				f"Refusing to delete an unsafe kit id: {kit_id!r}"
			)
		# TRAILING SLASH IS LOAD-BEARING. list_blobs matches on a raw string
		# prefix, so deleting "w7" without it would also sweep away "w7-2024"
		# and "w7-old" -- sibling kits whose ids merely start the same way. The
		# slash confines the match to this kit's own directory.
		base = self._build_blob_path(kit_id) + "/"

		def _purge() -> int:
			blobs = list(self._client.list_blobs(self.bucket_name, prefix=base))
			if not blobs:
				raise FormKitNotFound(f"Kit not found: {kit_id}")
			removed = 0
			for blob in blobs:
				# Belt and braces: assert each blob really is under the prefix
				# before deleting it, rather than trusting the listing.
				if not blob.name.startswith(base):
					continue
				blob.delete()
				removed += 1
			return removed

		try:
			return await anyio.to_thread.run_sync(_purge)
		except FormKitNotFound:
			raise
		except Exception as exc:
			raise FormKitStoreError(
				f"Unable to delete gs://{self.bucket_name}/{base}: {exc}"
			) from exc


@lru_cache(maxsize=1)
def get_form_kit_store() -> FormKitStore:
	settings = get_settings()
	mode = (settings.FORM_KITS_MODE or "local").lower()

	if mode == "gcs":
		bucket = settings.FORM_KITS_GCS_BUCKET
		if not bucket:
			raise RuntimeError(
				"FORM_KITS_GCS_BUCKET must be set when FORM_KITS_MODE=gcs"
			)

		return GCSFormKitStore(
			bucket_name=bucket.strip(),
			prefix=settings.FORM_KITS_REMOTE_PREFIX,
		)

	# Default to local filesystem
	root = Path(settings.FORM_KITS_LOCAL_ROOT).expanduser()
	if not root.exists():
		_log.warning("form_kits.local_root_missing", root=str(root))

	return LocalFormKitStore(root)
