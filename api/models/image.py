import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import String, DateTime, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    ERROR = "error"


class Base(DeclarativeBase):
    pass


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="default")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_key: Mapped[str] = mapped_column(String(1024), nullable=True)
    processed_key: Mapped[str] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ProcessingStatus.PENDING)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # Spatial metadata (populated after GDAL processing)
    crs: Mapped[str] = mapped_column(String(64), nullable=True)
    bbox_minx: Mapped[float] = mapped_column(nullable=True)
    bbox_miny: Mapped[float] = mapped_column(nullable=True)
    bbox_maxx: Mapped[float] = mapped_column(nullable=True)
    bbox_maxy: Mapped[float] = mapped_column(nullable=True)

    # OGC service URLs (populated after GeoServer publication)
    layer_name: Mapped[str] = mapped_column(String(256), nullable=True)
    wms_url: Mapped[str] = mapped_column(Text, nullable=True)
    wmts_url: Mapped[str] = mapped_column(Text, nullable=True)
    wcs_url: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
