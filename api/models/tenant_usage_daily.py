import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .image import Base


class TenantUsageDaily(Base):
    __tablename__ = "tenant_usage_daily"
    __table_args__ = (UniqueConstraint("tenant_id", "usage_date", name="uq_tenant_usage_daily"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    storage_used_gb: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uploads_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    downloads_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
