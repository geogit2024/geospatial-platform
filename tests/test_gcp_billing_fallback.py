from pathlib import Path
import asyncio
import sys
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from services import gcp_billing


def test_query_with_project_filter_without_fallback(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_run_daily_cost_query(*, table_id: str, start: date, end: date, project_id: str):
        calls.append(project_id)
        return [{"date": "2026-04-20", "total_cost": 1.23}]

    monkeypatch.setattr(gcp_billing, "_run_daily_cost_query", _fake_run_daily_cost_query)

    rows = asyncio.run(
        gcp_billing._run_daily_cost_query_with_fallback(
            table_id="p.d.t",
            start=date(2026, 4, 1),
            end=date(2026, 4, 20),
            project_id="geopublish",
        )
    )

    assert len(rows) == 1
    assert calls == ["geopublish"]


def test_query_without_project_filter_runs_once(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_run_daily_cost_query(*, table_id: str, start: date, end: date, project_id: str):
        calls.append(project_id)
        return []

    monkeypatch.setattr(gcp_billing, "_run_daily_cost_query", _fake_run_daily_cost_query)

    rows = asyncio.run(
        gcp_billing._run_daily_cost_query_with_fallback(
            table_id="p.d.t",
            start=date(2026, 4, 1),
            end=date(2026, 4, 20),
            project_id="",
        )
    )

    assert rows == []
    assert calls == [""]


def test_query_falls_back_to_all_projects_when_filtered_is_empty(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_run_daily_cost_query(*, table_id: str, start: date, end: date, project_id: str):
        calls.append(project_id)
        if project_id:
            return []
        return [{"date": "2026-04-20", "total_cost": 9.87}]

    monkeypatch.setattr(gcp_billing, "_run_daily_cost_query", _fake_run_daily_cost_query)

    rows = asyncio.run(
        gcp_billing._run_daily_cost_query_with_fallback(
            table_id="p.d.t",
            start=date(2026, 4, 1),
            end=date(2026, 4, 20),
            project_id="geopublish",
        )
    )

    assert len(rows) == 1
    assert calls == ["geopublish", ""]
