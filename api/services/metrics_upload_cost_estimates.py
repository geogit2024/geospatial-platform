from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import UploadCostEstimateSession
from services.upload_cost_estimator import loads_json


def _to_gb(size_bytes: int | float | None) -> float:
    value = float(size_bytes or 0.0)
    return value / (1024.0 * 1024.0 * 1024.0)


def _extract_money_from_estimate(estimate: dict[str, Any]) -> tuple[float, float, str]:
    breakdown = estimate.get("breakdown", {}) if isinstance(estimate, dict) else {}
    currency = str(estimate.get("currency") or "BRL") if isinstance(estimate, dict) else "BRL"
    first_month_total = float(breakdown.get("first_month_total") or 0.0)
    recurring_monthly_total = float(breakdown.get("recurring_monthly_total") or 0.0)
    return first_month_total, recurring_monthly_total, currency


def _session_to_item(session: UploadCostEstimateSession) -> dict[str, Any]:
    estimate = loads_json(session.accepted_estimate_json) or loads_json(session.estimate_json)
    first_month_total, recurring_monthly_total, currency = _extract_money_from_estimate(estimate)
    assumptions_used = (
        estimate.get("assumptions_used", {})
        if isinstance(estimate, dict)
        else {}
    )
    expected_downloads = int(assumptions_used.get("expected_monthly_downloads") or 0)

    return {
        "session_id": session.id,
        "status": session.status,
        "filename": session.filename,
        "asset_type": str(session.asset_type or "unknown"),
        "size_gb": round(_to_gb(session.size_bytes), 4),
        "expected_monthly_downloads": expected_downloads,
        "first_month_total": round(first_month_total, 2),
        "recurring_monthly_total": round(recurring_monthly_total, 2),
        "currency": currency,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "accepted_at": session.accepted_at.isoformat() if session.accepted_at else None,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
    }


async def get_upload_cost_estimate_audit(
    db: AsyncSession,
    *,
    tenant_id: str,
    window_days: int,
    limit: int,
) -> dict[str, Any]:
    now = datetime.utcnow()
    start = now - timedelta(days=max(int(window_days), 1))
    max_items = min(max(int(limit), 1), 100)

    count_stmt = (
        select(UploadCostEstimateSession.status, func.count().label("total"))
        .where(UploadCostEstimateSession.tenant_id == tenant_id)
        .where(UploadCostEstimateSession.created_at >= start)
        .group_by(UploadCostEstimateSession.status)
    )
    count_rows = await db.execute(count_stmt)
    status_counts = {str(row.status): int(row.total or 0) for row in count_rows.all()}

    total_sessions = sum(status_counts.values())
    accepted_count = int(status_counts.get("accepted", 0) + status_counts.get("consumed", 0))
    consumed_count = int(status_counts.get("consumed", 0))
    estimated_count = int(status_counts.get("estimated", 0))
    acceptance_rate = (accepted_count / total_sessions * 100.0) if total_sessions > 0 else 0.0
    conversion_rate = (consumed_count / accepted_count * 100.0) if accepted_count > 0 else 0.0

    expired_stmt = (
        select(func.count())
        .select_from(UploadCostEstimateSession)
        .where(UploadCostEstimateSession.tenant_id == tenant_id)
        .where(UploadCostEstimateSession.expires_at < now)
    )
    expired_total = int((await db.execute(expired_stmt)).scalar() or 0)

    accepted_sessions_stmt = (
        select(UploadCostEstimateSession)
        .where(UploadCostEstimateSession.tenant_id == tenant_id)
        .where(UploadCostEstimateSession.created_at >= start)
        .where(UploadCostEstimateSession.status.in_(["accepted", "consumed"]))
    )
    accepted_rows = await db.execute(accepted_sessions_stmt)
    accepted_sessions = list(accepted_rows.scalars())
    accepted_first_month: list[float] = []
    accepted_recurring: list[float] = []
    currency = "BRL"
    for session in accepted_sessions:
        estimate = loads_json(session.accepted_estimate_json) or loads_json(session.estimate_json)
        first_month_total, recurring_monthly_total, item_currency = _extract_money_from_estimate(estimate)
        currency = item_currency or currency
        if first_month_total > 0:
            accepted_first_month.append(first_month_total)
        if recurring_monthly_total > 0:
            accepted_recurring.append(recurring_monthly_total)

    recent_stmt = (
        select(UploadCostEstimateSession)
        .where(UploadCostEstimateSession.tenant_id == tenant_id)
        .where(UploadCostEstimateSession.created_at >= start)
        .order_by(UploadCostEstimateSession.created_at.desc())
        .limit(max_items)
    )
    recent_rows = await db.execute(recent_stmt)
    recent_sessions = list(recent_rows.scalars())

    return {
        "tenant_id": tenant_id,
        "window_days": int(window_days),
        "totals": {
            "sessions": int(total_sessions),
            "estimated": estimated_count,
            "accepted": int(status_counts.get("accepted", 0)),
            "consumed": consumed_count,
            "expired_total": expired_total,
        },
        "rates": {
            "acceptance_rate_pct": round(acceptance_rate, 2),
            "conversion_to_upload_pct": round(conversion_rate, 2),
        },
        "accepted_averages": {
            "currency": currency,
            "first_month_total": round(
                (sum(accepted_first_month) / len(accepted_first_month)) if accepted_first_month else 0.0,
                2,
            ),
            "recurring_monthly_total": round(
                (sum(accepted_recurring) / len(accepted_recurring)) if accepted_recurring else 0.0,
                2,
            ),
        },
        "status_breakdown": [
            {"status": status, "count": count}
            for status, count in sorted(status_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "recent_sessions": [_session_to_item(item) for item in recent_sessions],
    }


async def cleanup_expired_upload_cost_estimate_sessions(
    db: AsyncSession,
    *,
    tenant_id: str,
    limit: int,
) -> dict[str, Any]:
    now = datetime.utcnow()
    max_items = min(max(int(limit), 1), 2000)

    pick_stmt = (
        select(UploadCostEstimateSession.id, UploadCostEstimateSession.expires_at)
        .where(UploadCostEstimateSession.tenant_id == tenant_id)
        .where(UploadCostEstimateSession.expires_at < now)
        .order_by(UploadCostEstimateSession.expires_at.asc())
        .limit(max_items)
    )
    rows = await db.execute(pick_stmt)
    picked = list(rows.all())
    if not picked:
        return {
            "tenant_id": tenant_id,
            "deleted_count": 0,
            "limit": max_items,
            "executed_at": now.isoformat(),
            "oldest_expires_at": None,
            "newest_expires_at": None,
        }

    ids = [str(row.id) for row in picked]
    oldest = min(row.expires_at for row in picked)
    newest = max(row.expires_at for row in picked)

    await db.execute(delete(UploadCostEstimateSession).where(UploadCostEstimateSession.id.in_(ids)))
    await db.commit()

    return {
        "tenant_id": tenant_id,
        "deleted_count": len(ids),
        "limit": max_items,
        "executed_at": now.isoformat(),
        "oldest_expires_at": oldest.isoformat() if oldest else None,
        "newest_expires_at": newest.isoformat() if newest else None,
    }
