"""
Document management API router.

Provides:
- POST /documents/upload — Upload a PDF
- GET /documents — List all documents
- GET /documents/{id} — Document detail
- GET /documents/{id}/status — Processing status
- DELETE /documents/{id} — Delete document
"""

import shutil
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    Query,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_app_settings, get_db_session, get_rag_service
from app.core.limiter import limiter
from app.core.exceptions import (
    DuplicatePDFError,
    DocumentNotFoundError,
    InvalidPDFError,
    PDFTooLargeError,
)
from app.core.logging import get_logger
from app.core.settings import AppSettings
from app.models.database import Document, DocumentStatus
from app.models.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Background task for document processing ──────────────────────────────

async def _process_document_background(
    document_id: int,
    file_path: str,
    original_filename: str,
    rag_service,
    session_factory,
) -> None:
    """Background task to process an uploaded PDF."""
    async with session_factory() as session:
        try:
            await rag_service.ingest_document(
                document_id=document_id,
                file_path=file_path,
                original_filename=original_filename,
                db_session=session,
            )
        except DuplicatePDFError:
            logger.warning(f"Duplicate document: {original_filename}")
        except Exception as e:
            logger.error(f"Background processing failed for {original_filename}: {e}")


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=202,
    summary="Upload a PDF document",
    description="Uploads a PDF and initiates background processing (parsing, chunking, embedding).",
)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file to upload"),
    settings: AppSettings = Depends(get_app_settings),
    db_session: AsyncSession = Depends(get_db_session),
    rag_service=Depends(get_rag_service),
):
    """Upload a PDF document for processing."""

    # ── Validate file type ───────────────────────────────────────
    if not file.filename:
        raise InvalidPDFError(user_message="No filename provided.")

    if not file.filename.lower().endswith(".pdf"):
        raise InvalidPDFError(
            user_message=f"Only PDF files are accepted. Got: {Path(file.filename).suffix}"
        )

    if file.content_type and file.content_type != "application/pdf":
        # Some browsers may not set content_type correctly, so just warn
        logger.warning(f"Unexpected content type: {file.content_type}")

    # ── Save to upload directory ─────────────────────────────────
    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to prevent collisions
    safe_name = f"{uuid.uuid4().hex}_{Path(file.filename).stem}.pdf"
    file_path = upload_dir / safe_name

    import hashlib
    file_hash_obj = hashlib.sha256()

    try:
        max_bytes = settings.pdf_max_file_size_mb * 1024 * 1024
        file_size = 0
        first_chunk = True

        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                if file_size > max_bytes:
                    raise PDFTooLargeError(
                        user_message=f"File size exceeds the maximum of {settings.pdf_max_file_size_mb}MB."
                    )

                # ── Validate magic bytes ─────────────────────────────
                if first_chunk:
                    if not chunk.startswith(b"%PDF"):
                        raise InvalidPDFError(
                            user_message="The uploaded file is not a valid PDF document."
                        )
                    first_chunk = False

                buffer.write(chunk)
                file_hash_obj.update(chunk)

    except (PDFTooLargeError, InvalidPDFError):
        # Clean up the partial file
        if file_path.exists():
            file_path.unlink()
        raise
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        logger.error(f"Failed to save upload: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # ── Create initial DB record ─────────────────────────────────
    file_hash = file_hash_obj.hexdigest()

    # Check for duplicate
    existing = await db_session.execute(
        select(Document).where(Document.file_hash == file_hash)
    )
    if existing.scalar_one_or_none():
        file_path.unlink(missing_ok=True)
        raise DuplicatePDFError(
            user_message=f"'{file.filename}' has already been uploaded."
        )

    doc = Document(
        filename=safe_name,
        original_filename=file.filename,
        file_hash=file_hash,
        file_size_bytes=file_size,
        status=DocumentStatus.PROCESSING,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    # ── Launch background processing ─────────────────────────────
    background_tasks.add_task(
        _process_document_background,
        doc.id,
        str(file_path),
        file.filename,
        rag_service,
        request.app.state.db_session_factory,
    )

    logger.info(f"Upload accepted: {file.filename} ({file_size} bytes) → id={doc.id}")

    return DocumentUploadResponse(
        id=doc.id,
        filename=file.filename,
        file_size_bytes=file_size,
        status=doc.status.value,
        message="Document uploaded successfully. Processing in background.",
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents",
    description="Returns a paginated list of all uploaded documents.",
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db_session: AsyncSession = Depends(get_db_session),
):
    """List all uploaded documents with pagination."""

    # Count total
    count_result = await db_session.execute(select(func.count(Document.id)))
    total = count_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    result = await db_session.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    documents = result.scalars().all()

    return DocumentListResponse(
        documents=[
            DocumentResponse.model_validate(doc) for doc in documents
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
)
async def get_document(
    document_id: int,
    db_session: AsyncSession = Depends(get_db_session),
):
    """Get details of a specific document."""
    result = await db_session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise DocumentNotFoundError(
            user_message=f"Document with ID {document_id} not found."
        )

    return DocumentResponse.model_validate(doc)


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Check processing status",
)
async def get_document_status(
    document_id: int,
    db_session: AsyncSession = Depends(get_db_session),
):
    """Check the processing status of a document."""
    result = await db_session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise DocumentNotFoundError(
            user_message=f"Document with ID {document_id} not found."
        )

    return DocumentStatusResponse(
        id=doc.id,
        status=doc.status.value,
        total_chunks=doc.total_chunks,
        error_message=doc.error_message,
    )


@router.delete(
    "/{document_id}",
    summary="Delete a document",
    description="Deletes a document and all its chunks from both databases.",
)
async def delete_document(
    document_id: int,
    db_session: AsyncSession = Depends(get_db_session),
    rag_service=Depends(get_rag_service),
    settings: AppSettings = Depends(get_app_settings),
):
    """Delete a document and all associated data."""
    # Get document first to find the file path
    result = await db_session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise DocumentNotFoundError(
            user_message=f"Document with ID {document_id} not found."
        )

    # Delete from vector DB + SQL DB
    await rag_service.delete_document(document_id, db_session)

    # Delete the uploaded file
    file_path = settings.upload_dir / doc.filename
    if file_path.exists():
        file_path.unlink()
        logger.info(f"Deleted file: {file_path}")

    return {"message": f"Document '{doc.original_filename}' deleted successfully."}
