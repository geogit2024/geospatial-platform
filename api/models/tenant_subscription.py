import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .image import Base


class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), index=True, nullable=False)
    scheduled_plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    billing_cycle: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    current_period_start: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    current_period_end: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    provider: Mapped[str] = mapped_column(String(32), nullable=True)
    provider_customer_id: Mapped[str] = mapped_column(String(128), nullable=True)
    provider_subscription_id: Mapped[str] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
