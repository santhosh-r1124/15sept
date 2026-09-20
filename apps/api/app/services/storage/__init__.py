"""File storage for matter documents (Phase 9).

``LocalFileStorage`` (free, on disk) backs development and small deployments; production would
swap in object storage (S3 / Supabase Storage) behind the same ``FileStorage`` protocol - that
is a Phase 15 deployment choice, not made here.

Safety rules that apply regardless of backend, and are enforced in this module:

* the client never influences where bytes land - keys are server-generated hex names;
* the declared content type must be on an allowlist **and** the leading bytes must match it
  (a ``.pdf`` that isn't a PDF is rejected), which stops trivial type spoofing;
* the client's file name is sanitised before it goes anywhere near a response header.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from app.core.config import Settings
from app.core.errors import AppError, ValidationAppError

# content type -> (extension, accepted magic prefixes)
_ALLOWED: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "application/pdf": (".pdf", (b"%PDF-",)),
    "image/png": (".png", (b"\x89PNG\r\n\x1a\n",)),
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
    # .docx is a zip container; legacy .doc is an OLE compound file.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        ".docx",
        (b"PK\x03\x04",),
    ),
    "application/msword": (".doc", (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)),
    "text/plain": (".txt", ()),  # no magic number; checked as UTF-8 text instead
}
_KEY_RE = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]")
# Characters that are never legitimate in a download name (controls, path separators,
# header-breaking quotes, Windows-reserved punctuation); everything else - including Indian
# scripts - is kept for the UTF-8 form.
_DISALLOWED_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
_MISMATCH = "The file's contents don't match its declared type."


class FileTooLargeError(AppError):
    code = "file_too_large"
    message = "That file is too large."
    status_code = 413


class FileStorage(Protocol):
    async def save(self, key: str, data: bytes) -> None: ...

    async def read(self, key: str) -> bytes: ...


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        # Keys are ours, but never trust anything that becomes a path component.
        if not _KEY_RE.match(key):
            raise ValueError("invalid storage key")
        return self._root / key

    async def save(self, key: str, data: bytes) -> None:
        path = self._path(key)

        def _write() -> None:
            self._root.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)


def get_storage(settings: Settings) -> FileStorage:
    return LocalFileStorage(Path(settings.upload_dir))


def validate_upload(content_type: str, data: bytes, *, max_bytes: int) -> str:
    """Return the storage extension for a valid upload, or raise (413 / 422)."""
    if len(data) > max_bytes:
        raise FileTooLargeError(f"Files can be at most {max_bytes // (1024 * 1024)} MB.")
    if not data:
        raise ValidationAppError("That file is empty.")
    entry = _ALLOWED.get(content_type)
    if entry is None:
        raise ValidationAppError(
            "That file type isn't allowed. Upload a PDF, Word document, PNG, JPEG or text file."
        )
    extension, magics = entry
    if magics:
        if not any(data.startswith(m) for m in magics):
            raise ValidationAppError(_MISMATCH)
    else:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationAppError(_MISMATCH) from exc
        if b"\x00" in data:
            raise ValidationAppError(_MISMATCH)
    return extension


def new_storage_key(extension: str) -> str:
    return f"{uuid.uuid4().hex}{extension}"


def safe_download_name(name: str) -> str:
    cleaned = _UNSAFE_NAME_CHARS.sub("_", name.strip())[:150].strip(" .")
    return cleaned or "document"


def content_disposition(name: str) -> str:
    """An ``attachment`` header that is header-injection-safe and keeps non-Latin names intact.

    Sends both the sanitised ASCII ``filename`` (old clients) and the RFC 5987 ``filename*``
    UTF-8 form (every modern browser), so a Hindi or Tamil file name downloads as itself
    rather than as a row of underscores.
    """
    unicode_name = _DISALLOWED_NAME_CHARS.sub("_", name.strip())[:150].strip(" .") or "document"
    return (
        f'attachment; filename="{safe_download_name(name)}"; '
        f"filename*=UTF-8''{quote(unicode_name, safe='')}"
    )
