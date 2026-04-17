import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .image import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="BRL")
    price_monthly: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    storage_limit_gb: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    monthly_upload_limit: Mapped[int] = mapped_column(Integer, nullable=True)
    monthly_processing_limit: Mapped[int] = mapped_column(Integer, nullable=True)
    monthly_download_limit: Mapped[int] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
