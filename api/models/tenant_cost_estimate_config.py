import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .image import Base


class TenantCostEstimateConfig(Base):
    __tablename__ = "tenant_cost_estimate_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    expected_monthly_downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    avg_download_size_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)

    processed_size_ratio_raster: Mapped[float] = mapped_column(Float, nullable=False, default=0.65)
    processed_size_ratio_vector: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)

    processing_base_units: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    processing_units_per_gb_raster: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    processing_units_per_gb_vector: Mapped[float] = mapped_column(Float, nullable=False, default=1.2)

    uncertainty_min_factor: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    uncertainty_max_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.4)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
