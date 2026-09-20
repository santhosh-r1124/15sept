"""Document exchange inside a matter (Phase 9, FRD 10): the advocate requests documents, either
party uploads files, the advocate uploads the final deliverable, participants download.

Access follows the rest of the matter API (``services/matters/access``): outsiders get a 404,
admins may read and download but never write. Uploads are validated (type allowlist + magic
bytes + size cap) and stored under a server-generated key - see ``services/storage``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.matter import Matter, MatterStatus
from app.models.matter_document import (
    MatterDocumentRequest,
    MatterDocumentRequestStatus,
    MatterFile,
)
from app.schemas.matter_document import (
    CreateDocumentRequestRequest,
    DocumentRequestOut,
    MatterDocumentsOut,
    MatterFileOut,
)
from app.services.matters.access import load_matter, readable_by, require_actor
from app.services.matters.lifecycle import Actor
from app.services.notifications import content as notice
from app.services.notifications import deliver_request_emails, notify
from app.services.rate_limit import rate_limit
from app.services.storage import (
    content_disposition,
    get_storage,
    new_storage_key,
    validate_upload,
)

router = APIRouter()

# Documents change hands only once the advocate has taken the matter on and until it ends.
_EXCHANGE_STATUSES = (MatterStatus.ACCEPTED, MatterStatus.PAID, MatterStatus.SCHEDULED)
# The advocate's *final* deliverable is only meaningful after the client has paid.
_FINAL_STATUSES = (MatterStatus.PAID, MatterStatus.SCHEDULED)


def _request_out(request: MatterDocumentRequest) -> DocumentRequestOut:
    return DocumentRequestOut(
        id=request.id,
        matter_id=request.matter_id,
        description=request.description,
        status=request.status,
        created_at=request.created_at,
    )


def _file_out(file: MatterFile, matter: Matter) -> MatterFileOut:
    role = "CONSUMER" if file.uploader_id == matter.consumer_id else "ADVOCATE"
    return MatterFileOut(
        id=file.id,
        matter_id=file.matter_id,
        request_id=file.request_id,
        file_name=file.file_name,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        is_final=file.is_final,
        uploader_role=role,
        created_at=file.created_at,
    )


def _require_exchange_open(matter: Matter) -> None:
    if matter.status not in _EXCHANGE_STATUSES:
        raise ConflictError(
            "Documents can only be exchanged once the advocate has accepted the matter and "
            "until it ends.",
            code="documents_closed",
        )


@router.get(
    "/{matter_id}/documents", response_model=MatterDocumentsOut, summary="Requests and files"
)
async def list_documents(
    matter_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> MatterDocumentsOut:
    matter = await load_matter(db, matter_id)
    readable_by(user, matter)
    requests = (
        (
            await db.execute(
                select(MatterDocumentRequest)
                .where(MatterDocumentRequest.matter_id == matter.id)
                .order_by(MatterDocumentRequest.created_at, MatterDocumentRequest.id)
            )
        )
        .scalars()
        .all()
    )
    files = (
        (
            await db.execute(
                select(MatterFile)
                .where(MatterFile.matter_id == matter.id)
                .order_by(MatterFile.created_at, MatterFile.id)
            )
        )
        .scalars()
        .all()
    )
    return MatterDocumentsOut(
        requests=[_request_out(r) for r in requests], files=[_file_out(f, matter) for f in files]
    )


@router.post(
    "/{matter_id}/document-requests",
    response_model=DocumentRequestOut,
    status_code=201,
    summary="Advocate asks the client for a document",
)
async def create_document_request(
    matter_id: uuid.UUID,
    payload: CreateDocumentRequestRequest,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> DocumentRequestOut:
    matter = await load_matter(db, matter_id)
    if require_actor(user, matter) is not Actor.ADVOCATE:
        raise ForbiddenError("Only the advocate can request documents.")
    _require_exchange_open(matter)
    request = MatterDocumentRequest(
        matter_id=matter.id, requested_by_id=user.id, description=payload.description
    )
    db.add(request)
    await notify(
        db,
        settings,
        matter.consumer,
        notice.document_requested(
            matter_id=matter.id, title=matter.title, description=payload.description
        ),
    )
    await db.commit()
    await deliver_request_emails(db)
    await db.refresh(request)
    return _request_out(request)


@router.post(
    "/{matter_id}/files",
    response_model=MatterFileOut,
    status_code=201,
    summary="Upload a file",
    dependencies=[rate_limit("matter-upload", limit=30, window_seconds=3600)],
)
async def upload_file(
    matter_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    request_id: Annotated[uuid.UUID | None, Form()] = None,
    is_final: Annotated[bool, Form()] = False,
) -> MatterFileOut:
    matter = await load_matter(db, matter_id)
    actor = require_actor(user, matter)
    _require_exchange_open(matter)

    if is_final:
        if actor is not Actor.ADVOCATE:
            raise ForbiddenError("Only the advocate can upload final documents.")
        if matter.status not in _FINAL_STATUSES:
            raise ConflictError(
                "Final documents can be uploaded once the client has paid.",
                code="documents_closed",
            )

    fulfilled: MatterDocumentRequest | None = None
    if request_id is not None:
        fulfilled = await db.scalar(
            select(MatterDocumentRequest).where(
                MatterDocumentRequest.id == request_id, MatterDocumentRequest.matter_id == matter.id
            )
        )
        if fulfilled is None:
            raise NotFoundError("Document request not found.")

    # Read one byte past the cap so an oversized upload is detected without buffering it all.
    data = await file.read(settings.upload_max_bytes + 1)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    extension = validate_upload(content_type, data, max_bytes=settings.upload_max_bytes)

    key = new_storage_key(extension)
    await get_storage(settings).save(key, data)
    record = MatterFile(
        matter_id=matter.id,
        uploader_id=user.id,
        request_id=request_id,
        file_name=(file.filename or "document")[:255],
        content_type=content_type,
        size_bytes=len(data),
        storage_key=key,
        is_final=is_final,
    )
    db.add(record)
    if fulfilled is not None:
        fulfilled.status = MatterDocumentRequestStatus.FULFILLED
    recipient = matter.advocate_profile.user if actor is Actor.CONSUMER else matter.consumer
    await notify(
        db,
        settings,
        recipient,
        notice.document_uploaded(matter_id=matter.id, title=matter.title, is_final=is_final),
        coalesce=True,
    )
    await db.commit()
    await db.refresh(record)
    return _file_out(record, matter)


@router.get("/{matter_id}/files/{file_id}", summary="Download a file")
async def download_file(
    matter_id: uuid.UUID,
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> Response:
    matter = await load_matter(db, matter_id)
    readable_by(user, matter)
    record = await db.scalar(
        select(MatterFile).where(MatterFile.id == file_id, MatterFile.matter_id == matter.id)
    )
    if record is None:
        raise NotFoundError("File not found.")
    data = await get_storage(settings).read(record.storage_key)
    return Response(
        content=data,
        media_type=record.content_type,
        headers={
            "Content-Disposition": content_disposition(record.file_name),
            # Never let a browser second-guess the type and render an upload as HTML/script.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
