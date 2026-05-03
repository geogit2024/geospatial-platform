import uuid
from datetime import datetime

from sqlalchemy import BIGINT, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .image import Base


class UploadCostEstimateSession(Base):
    __tablename__ = "upload_cost_estimate_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=True)

    temp_bucket: Mapped[str] = mapped_column(String(128), nullable=True)
    temp_object_key: Mapped[str] = mapped_column(String(1024), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="started")
    analysis_json: Mapped[str] = mapped_column(Text, nullable=True)
    assumptions_json: Mapped[str] = mapped_column(Text, nullable=True)
    estimate_json: Mapped[str] = mapped_column(Text, nullable=True)
    accepted_estimate_json: Mapped[str] = mapped_column(Text, nullable=True)
    accepted_input_json: Mapped[str] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
