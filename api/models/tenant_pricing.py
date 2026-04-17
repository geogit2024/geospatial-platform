import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .image import Base


class TenantPricing(Base):
    __tablename__ = "tenant_pricing"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    cost_per_gb_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    cost_per_process: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    cost_per_download: Mapped[float] = mapped_column(Float, nullable=False, default=0.01)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="BRL")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
