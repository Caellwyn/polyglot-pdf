from __future__ import annotations

"""Form kit storage helpers for loading schemas/PDFs in dev and prod."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import anyio
import httpx
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

		return await anyio.to_thread.run_sync(
			lambda: json.loads(path.read_text(encoding="utf-8"))
		)

	async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
		kit_dir = self._kit_dir(kit_id)
		path = kit_dir / pdf_filename
		if not path.exists():
			raise FormKitNotFound(f"PDF not found for {kit_id}: {pdf_filename}")

		return await anyio.to_thread.run_sync(path.read_bytes)


class RemoteFormKitStore(FormKitStore):
	def __init__(self, base_url: str, prefix: Optional[str] = None, timeout: float = 30.0):
		self.base_url = base_url.rstrip("/")
		self.prefix = (prefix or "").strip("/")
		self.timeout = timeout
		_log.info(
			"form_kits.remote_store",
			base_url=self.base_url,
			prefix=self.prefix or "/",
			timeout_sec=self.timeout,
		)

	def _build_url(self, kit_id: str, filename: str) -> str:
		url = self.base_url
		segments = [segment for segment in [self.prefix, kit_id, filename] if segment]
		if segments:
			url = f"{url}/{'/'.join(segments)}"
		return url

	async def _fetch_bytes(self, kit_id: str, filename: str) -> bytes:
		url = self._build_url(kit_id, filename)
		async with httpx.AsyncClient(timeout=self.timeout) as client:
			response = await client.get(url)

		if response.status_code == 404:
			raise FormKitNotFound(f"Remote asset not found at {url}")

		try:
			response.raise_for_status()
		except httpx.HTTPError as exc:
			raise FormKitStoreError(f"Failed to fetch {url}: {exc}") from exc

		return response.content

	async def load_schema(self, kit_id: str, schema_file: str = "schema.json") -> dict:
		data = await self._fetch_bytes(kit_id, schema_file)
		try:
			return json.loads(data.decode("utf-8"))
		except json.JSONDecodeError as exc:
			raise FormKitStoreError(
				f"Invalid schema JSON for {kit_id}/{schema_file}: {exc}"
			) from exc

	async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
		return await self._fetch_bytes(kit_id, pdf_filename)


@lru_cache(maxsize=1)
def get_form_kit_store() -> FormKitStore:
	settings = get_settings()
	mode = (settings.FORM_KITS_MODE or "local").lower()

	if mode == "gcs":
		base_url = settings.FORM_KITS_REMOTE_BASE_URL
		if not base_url:
			bucket = settings.FORM_KITS_GCS_BUCKET
			if not bucket:
				raise RuntimeError(
					"FORM_KITS_GCS_BUCKET or FORM_KITS_REMOTE_BASE_URL must be set when FORM_KITS_MODE=gcs"
				)
			base_url = f"https://storage.googleapis.com/{bucket.strip()}"

		return RemoteFormKitStore(
			base_url=base_url,
			prefix=settings.FORM_KITS_REMOTE_PREFIX,
			timeout=settings.FORM_KITS_REMOTE_TIMEOUT_SEC,
		)

	# Default to local filesystem
	root = Path(settings.FORM_KITS_LOCAL_ROOT).expanduser()
	if not root.exists():
		_log.warning("form_kits.local_root_missing", root=str(root))

	return LocalFormKitStore(root)
