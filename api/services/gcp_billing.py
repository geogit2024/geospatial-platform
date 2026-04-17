from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from config import get_settings

settings = get_settings()

_TABLE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_-]+$")


class BillingExportConfigError(RuntimeError):
    """Raised when billing export settings are missing or invalid."""


def _validate_table_id(table_id: str) -> str:
    normalized = table_id.strip()
    if not normalized:
        raise BillingExportConfigError(
            "GCP_BILLING_EXPORT_TABLE nao configurado. "
            "Informe no formato projeto.dataset.tabela."
        )
    if not _TABLE_ID_RE.match(normalized):
        raise BillingExportConfigError(
            "GCP_BILLING_EXPORT_TABLE invalido. Use projeto.dataset.tabela."
        )
    return normalized


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _daterange(start: date, end: date) -> list[date]:
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def _run_daily_cost_query(*, table_id: str, start: date, end: date, project_id: str) -> list[dict[str, Any]]:
    try:
        from google.cloud import bigquery
    except Exception as exc:  # pragma: no cover - dependency/runtime variation
        raise BillingExportConfigError(
            "google-cloud-bigquery nao disponivel. Instale a dependencia no servico da API."
        ) from exc

    query = f"""
    WITH line_items AS (
      SELECT
        DATE(usage_start_time) AS day,
        LOWER(service.description) AS service_desc,
        LOWER(sku.description) AS sku_desc,
        CAST(cost AS NUMERIC)
          + IFNULL((SELECT SUM(CAST(c.amount AS NUMERIC)) FROM UNNEST(credits) c), 0) AS net_cost,
        currency
      FROM `{table_id}`
      WHERE DATE(usage_start_time) BETWEEN @start_date AND @end_date
        AND (@project_id = '' OR project.id = @project_id)
    ),
    daily AS (
      SELECT
        day,
        SUM(net_cost) AS total_cost,
        SUM(
          CASE
            WHEN REGEXP_CONTAINS(service_desc, r'storage')
              OR REGEXP_CONTAINS(sku_desc, r'storage|gibibyte month|byte-seconds|snapshot')
            THEN net_cost ELSE 0
          END
        ) AS storage_cost,
        SUM(
          CASE
            WHEN REGEXP_CONTAINS(sku_desc, r'download|egress|internet')
              OR REGEXP_CONTAINS(service_desc, r'network')
            THEN net_cost ELSE 0
          END
        ) AS download_cost,
        ANY_VALUE(currency) AS currency
      FROM line_items
      GROUP BY day
    )
    SELECT
      FORMAT_DATE('%Y-%m-%d', day) AS date,
      ROUND(total_cost, 6) AS total_cost,
      ROUND(storage_cost, 6) AS storage_cost,
      ROUND(download_cost, 6) AS download_cost,
      ROUND(total_cost - storage_cost - download_cost, 6) AS processing_cost,
      currency
    FROM daily
    ORDER BY day
    """

    client_kwargs: dict[str, Any] = {}
    if settings.gcp_billing_export_project.strip():
        client_kwargs["project"] = settings.gcp_billing_export_project.strip()

    client = bigquery.Client(**client_kwargs)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start.isoformat()),
            bigquery.ScalarQueryParameter("end_date", "DATE", end.isoformat()),
            bigquery.ScalarQueryParameter("project_id", "STRING", project_id),
        ]
    )

    rows = client.query(query, job_config=job_config).result()
    return [dict(row.items()) for row in rows]


def _build_timeseries(
    rows: list[dict[str, Any]],
    *,
    start: date,
    end: date,
    currency_fallback: str,
) -> tuple[list[dict[str, Any]], str]:
    by_day = {str(item["date"]): item for item in rows}
    timeseries: list[dict[str, Any]] = []
    currency = currency_fallback

    for day in _daterange(start, end):
        key = day.isoformat()
        row = by_day.get(key)
        if row:
            currency = str(row.get("currency") or currency)
            total = _to_float(row.get("total_cost"))
            storage = _to_float(row.get("storage_cost"))
            processing = _to_float(row.get("processing_cost"))
            downloads = _to_float(row.get("download_cost"))
        else:
            total = 0.0
            storage = 0.0
            processing = 0.0
            downloads = 0.0

        timeseries.append(
            {
                "date": key,
                "value": round(total, 4),
                "storage": round(storage, 4),
                "processing": round(processing, 4),
                "downloads": round(downloads, 4),
            }
        )

    return timeseries, currency


async def get_billing_cost_metrics_from_export(
    *,
    window_days: int,
    project_id: str,
) -> dict[str, Any]:
    table_id = _validate_table_id(settings.gcp_billing_export_table)

    today = date.today()
    window_start = today - timedelta(days=max(window_days - 1, 0))
    month_start = today.replace(day=1)

    rows_window = await asyncio.to_thread(
        _run_daily_cost_query,
        table_id=table_id,
        start=window_start,
        end=today,
        project_id=project_id,
    )
    rows_month = await asyncio.to_thread(
        _run_daily_cost_query,
        table_id=table_id,
        start=month_start,
        end=today,
        project_id=project_id,
    )

    cost_timeseries, currency = _build_timeseries(
        rows_window,
        start=window_start,
        end=today,
        currency_fallback=settings.billing_currency,
    )
    month_series, currency = _build_timeseries(
        rows_month,
        start=month_start,
        end=today,
        currency_fallback=currency,
    )

    window_storage = sum(item["storage"] for item in cost_timeseries)
    window_processing = sum(item["processing"] for item in cost_timeseries)
    window_downloads = sum(item["downloads"] for item in cost_timeseries)
    window_total = sum(item["value"] for item in cost_timeseries)
    month_total = sum(item["value"] for item in month_series)
    month_storage = sum(item["storage"] for item in month_series)

    avg_daily = window_total / max(window_days, 1)
    projection_30_days = avg_daily * 30

    return {
        "currency": currency or settings.billing_currency,
        "window_total": round(window_total, 2),
        "window_storage": round(window_storage, 2),
        "window_processing": round(window_processing, 2),
        "window_downloads": round(window_downloads, 2),
        "month_total": round(month_total, 2),
        "month_storage": round(month_storage, 2),
        "projection_30_days": round(projection_30_days, 2),
        "cost_timeseries": cost_timeseries,
    }
