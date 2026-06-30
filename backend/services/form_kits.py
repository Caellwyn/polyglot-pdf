from __future__ import annotations

"""Form kit storage helpers for loading schemas/PDFs in dev and prod."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import anyio
import structlog

from backend.config import get_settings

_log = structlog.get_logger().bind(module="form_kit_store")


class FormKitStoreError(Exception):
	"""Base exception for form kit loading failures."""


class FormKitNotFound(FormKitStoreError):
	"""Raised when a kit or requested file cannot be located."""


class FormKitStore:
	"""Minimal async interface for loading kit assets."""

	async def load_schema(self, kit_id: str, schema_file: str = "schema.json") -> dict:
		raise NotImplementedError

	async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
		raise NotImplementedError

	async def load_manifest(self, manifest_file: str = "index.json") -> dict:
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
		except (json.JSONDecodeError, OSError) as exc:
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
			return {"forms": forms}

		for kit_dir in self.root.iterdir():
			if not kit_dir.is_dir():
				continue

			kit_id = kit_dir.name
			schema_path = kit_dir / "schema.json"

			if not schema_path.exists():
				continue

			# Extract label from schema
			try:
				schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
				label = schema_data.get("title", kit_id)
			except (json.JSONDecodeError, IOError):
				label = kit_id

			# Find PDF file
			pdf_file = "form.pdf"
			if not (kit_dir / "form.pdf").exists():
				pdf_files = list(kit_dir.glob("*.pdf"))
				if pdf_files:
					pdf_file = pdf_files[0].name

			forms.append({
				"id": kit_id,
				"label": label,
				"schemaFile": "schema.json",
				"schemaPath": f"/form-kits/{kit_id}/schema.json",
				"pdfFile": pdf_file,
				"pdfPath": f"/form-kits/{kit_id}/{pdf_file}",
			})

		_log.info("form_kits.local_manifest_generated", count=len(forms))
		return {"forms": forms}


class GCSFormKitStore(FormKitStore):
	"""Form kit store using authenticated Google Cloud Storage client."""

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
		except json.JSONDecodeError as exc:
			raise FormKitStoreError(
				f"Invalid schema JSON for {kit_id}/{schema_file}: {exc}"
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
			return json.loads(data.decode("utf-8"))
		except json.JSONDecodeError as exc:
			raise FormKitStoreError(f"Invalid manifest JSON at gs://{self.bucket_name}/{blob_path}: {exc}") from exc


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
