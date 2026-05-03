from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Plan, PlanFeature, TenantSubscription

DEFAULT_PLANS = [
    {
        "code": "free",
        "name": "Free",
        "description": "Plano inicial para validacao do produto",
        "currency": "BRL",
        "price_monthly": 0.0,
        "storage_limit_gb": 5.0,
        "monthly_upload_limit": 50,
        "monthly_processing_limit": 50,
        "monthly_download_limit": 100,
        "is_active": True,
        "features": {
            "wms": True,
            "wmts": True,
            "wcs": False,
            "download_raw": False,
            "priority_support": False,
            "upload_cost_estimate_v1": False,
        },
    },
    {
        "code": "pro",
        "name": "Pro",
        "description": "Plano para operacao recorrente",
        "currency": "BRL",
        "price_monthly": 299.0,
        "storage_limit_gb": 500.0,
        "monthly_upload_limit": 2000,
        "monthly_processing_limit": 2000,
        "monthly_download_limit": 10000,
        "is_active": True,
        "features": {
            "wms": True,
            "wmts": True,
            "wcs": True,
            "download_raw": True,
            "priority_support": False,
            "upload_cost_estimate_v1": True,
        },
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Plano corporativo com limites customizaveis",
        "currency": "BRL",
        "price_monthly": 0.0,
        "storage_limit_gb": 5000.0,
        "monthly_upload_limit": None,
        "monthly_processing_limit": None,
        "monthly_download_limit": None,
        "is_active": True,
        "features": {
            "wms": True,
            "wmts": True,
            "wcs": True,
            "download_raw": True,
            "priority_support": True,
            "upload_cost_estimate_v1": True,
        },
    },
]


async def seed_default_plans(db: AsyncSession) -> None:
    existing_rows = await db.execute(select(Plan.code))
    existing_codes = {row[0] for row in existing_rows.all()}

    created: list[Plan] = []
    for item in DEFAULT_PLANS:
        if item["code"] in existing_codes:
            continue
        plan = Plan(
            code=item["code"],
            name=item["name"],
            description=item["description"],
            currency=item["currency"],
            price_monthly=float(item["price_monthly"]),
            storage_limit_gb=float(item["storage_limit_gb"]),
            monthly_upload_limit=item["monthly_upload_limit"],
            monthly_processing_limit=item["monthly_processing_limit"],
            monthly_download_limit=item["monthly_download_limit"],
            is_active=bool(item["is_active"]),
        )
        db.add(plan)
        created.append(plan)

    if created:
        await db.flush()

    plans_result = await db.execute(select(Plan))
    plans = plans_result.scalars().all()

    feature_rows = await db.execute(select(PlanFeature.plan_id, PlanFeature.feature_key))
    existing_features = {(row[0], row[1]) for row in feature_rows.all()}

    has_changes = bool(created)
    for plan in plans:
        defaults = next((p for p in DEFAULT_PLANS if p["code"] == plan.code), None)
        if not defaults:
            continue
        for feature_key, enabled in defaults["features"].items():
            marker = (plan.id, feature_key)
            if marker in existing_features:
                continue
            db.add(
                PlanFeature(
                    plan_id=plan.id,
                    feature_key=feature_key,
                    is_enabled=bool(enabled),
                    limit_value=None,
                )
            )
            existing_features.add(marker)
            has_changes = True

    if has_changes:
        await db.commit()


async def ensure_default_subscription(
    db: AsyncSession,
    *,
    tenant_external_id: str = "default",
) -> None:
    row = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_external_id)
    )
    existing = row.scalar_one_or_none()
    if existing is not None:
        return

    plan_row = await db.execute(select(Plan).where(Plan.code == "free"))
    free_plan = plan_row.scalar_one_or_none()
    if free_plan is None:
        return

    now = datetime.utcnow()
    db.add(
        TenantSubscription(
            tenant_id=tenant_external_id,
            plan_id=free_plan.id,
            status="active",
            billing_cycle="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            provider=None,
            provider_customer_id=None,
            provider_subscription_id=None,
        )
    )
    await db.commit()
