import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Image, ProcessingStatus
from services.storage import generate_upload_url
from services.queue import publish_upload_event

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".tif", ".tiff", ".geotiff", ".jp2", ".ecw", ".img"}

# Normalize browser-supplied content-type to a predictable value per extension.
# GCS signed PUT URLs are scoped to the content-type used during signing — mismatches
# cause 403 errors.  Browsers sometimes send "application/octet-stream" for .tif files.
_CONTENT_TYPE_MAP = {
    ".tif":     "image/tiff",
    ".tiff":    "image/tiff",
    ".geotiff": "image/tiff",
    ".jp2":     "image/jp2",
    ".ecw":     "image/x-ecw",
    ".img":     "application/octet-stream",
}


class UploadRequest(BaseModel):
    filename: str
    content_type: str = "image/tiff"


class UploadResponse(BaseModel):
    image_id: str
    upload_url: str
    raw_key: str
    expires_in: int


class UploadConfirmRequest(BaseModel):
    image_id: str


@router.post("/signed-url", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def get_signed_upload_url(
    request: UploadRequest,
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    ext = "." + request.filename.rsplit(".", 1)[-1].lower() if "." in request.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{ext}' not supported. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Normalize content-type — browser may send "application/octet-stream" for .tif
    content_type = _CONTENT_TYPE_MAP.get(ext, request.content_type or "image/tiff")

    image_id = str(uuid.uuid4())
    raw_key = f"{image_id}/original{ext}"

    image = Image(
        id=image_id,
        filename=request.filename,
        original_key=raw_key,
        status=ProcessingStatus.UPLOADING,
    )
    db.add(image)
    await db.commit()

    upload_url = generate_upload_url(raw_key, content_type)

    return UploadResponse(
        image_id=image_id,
        upload_url=upload_url,
        raw_key=raw_key,
        expires_in=3600,
    )


@router.post("/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_upload(
    request: UploadConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    image = await db.get(Image, request.image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if image.status != ProcessingStatus.UPLOADING:
        raise HTTPException(status_code=400, detail=f"Image already in status: {image.status}")

    image.status = ProcessingStatus.UPLOADED
    await db.commit()

    await publish_upload_event(
        image_id=image.id,
        raw_key=image.original_key,
        filename=image.filename,
    )

    return {"image_id": image.id, "status": image.status, "message": "Processing queued"}
