"""Shared report application services for CLI and MCP surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from codex_usage_tracker.formatting import (
    format_calls,
    format_pricing_coverage,
    format_summary,
)
from codex_usage_tracker.pricing import (
    PricingConfig,
    annotate_rows_with_efficiency,
    load_pricing_config,
    summarize_pricing_coverage,
)
from codex_usage_tracker.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.projects import (
    annotate_rows_with_project_identity,
    load_project_config,
)
from codex_usage_tracker.recommendations import annotate_rows_with_recommendations
from codex_usage_tracker.store import (
    query_dashboard_events,
    query_most_expensive_calls,
    query_summary,
)


SUMMARY_GROUP_BY_CHOICES = (
    "date",
    "model",
    "effort",
    "cwd",
    "project",
    "project_tag",
    "thread",
    "session",
    "thread_source",
    "subagent_type",
    "agent_role",
    "parent_session",
    "parent_thread",
)
SUMMARY_PRESET_CHOICES = (
    "today",
    "last-7-days",
    "by-model",
    "by-cwd",
    "by-project",
    "by-project-tag",
    "by-thread",
    "by-subagent-role",
    "by-subagent-type",
    "expensive",
)
EXPENSIVE_PRESET_CHOICES = ("today", "last-7-days")

_SUMMARY_PRESET_GROUPS = {
    "by-model": "model",
    "by-cwd": "cwd",
    "by-project": "project",
    "by-project-tag": "project_tag",
    "by-thread": "thread",
    "by-subagent-role": "agent_role",
    "by-subagent-type": "subagent_type",
}


@dataclass(frozen=True)
class SummaryReport:
    """Resolved aggregate usage summary for one display surface."""

    rows: list[dict[str, Any]]
    group_by: str
    is_expensive: bool = False

    def render(self) -> str:
        if self.is_expensive:
            return format_calls(self.rows)
        return format_summary(self.rows, self.group_by)


@dataclass(frozen=True)
class PricingCoverageReport:
    """Resolved pricing coverage report."""

    payload: dict[str, Any]

    def render(self, limit: int = 20) -> str:
        return format_pricing_coverage(self.payload, limit=limit)


def resolve_summary_options(
    group_by: str, preset: str | None, since: str | None
) -> tuple[str, str | None]:
    """Resolve summary presets into a group and since filter."""

    return _SUMMARY_PRESET_GROUPS.get(preset, group_by), resolve_since(preset, since)


def resolve_since(preset: str | None, since: str | None) -> str | None:
    """Resolve date presets into an ISO date string."""

    if since:
        return since
    if preset == "today":
        return date.today().isoformat()
    if preset == "last-7-days":
        return (date.today() - timedelta(days=6)).isoformat()
    return None


def build_summary_report(
    *,
    db_path: Path,
    pricing_path: Path,
    group_by: str = "thread",
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
) -> SummaryReport:
    """Build a usage summary or expensive-call preset from aggregate rows."""

    resolved_group_by, since_filter = resolve_summary_options(group_by, preset, since)
    pricing = load_pricing_config(pricing_path)
    if preset == "expensive":
        rows = query_most_expensive_calls(db_path, limit=limit, since=since_filter)
        return SummaryReport(
            rows=annotate_rows_with_recommendations(annotate_rows_with_efficiency(rows, pricing)),
            group_by=resolved_group_by,
            is_expensive=True,
        )

    if resolved_group_by in {"project", "project_tag"}:
        rows = _project_summary_rows(
            db_path=db_path,
            pricing=pricing,
            group_by=resolved_group_by,
            limit=limit,
            since=since_filter,
            projects_path=projects_path,
        )
        return SummaryReport(rows=rows, group_by=resolved_group_by)

    rows = query_summary(
        db_path,
        group_by=resolved_group_by,
        limit=limit,
        since=since_filter,
    )
    if resolved_group_by == "model":
        rows = annotate_rows_with_efficiency(rows, pricing, model_field="group_key")
    return SummaryReport(rows=rows, group_by=resolved_group_by)


def build_expensive_calls_report(
    *,
    db_path: Path,
    pricing_path: Path,
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
) -> SummaryReport:
    """Build a highest-token-call report with pricing efficiency annotations."""

    pricing = load_pricing_config(pricing_path)
    rows = query_most_expensive_calls(
        db_path,
        limit=limit,
        since=resolve_since(preset, since),
    )
    return SummaryReport(
        rows=annotate_rows_with_recommendations(annotate_rows_with_efficiency(rows, pricing)),
        group_by="call",
        is_expensive=True,
    )


def build_pricing_coverage_report(
    *,
    db_path: Path,
    pricing_path: Path,
    limit: int = 1000,
    since: str | None = None,
    pricing: PricingConfig | None = None,
) -> PricingCoverageReport:
    """Build pricing coverage data grouped by model."""

    config = pricing or load_pricing_config(pricing_path)
    rows = query_summary(db_path, group_by="model", limit=limit, since=since)
    return PricingCoverageReport(summarize_pricing_coverage(rows, pricing=config))


def _project_summary_rows(
    *,
    db_path: Path,
    pricing: PricingConfig,
    group_by: str,
    limit: int,
    since: str | None,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
) -> list[dict[str, Any]]:
    rows = annotate_rows_with_project_identity(
        annotate_rows_with_efficiency(query_dashboard_events(db_path, limit=0, since=since), pricing),
        load_project_config(projects_path),
    )
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        if group_by == "project_tag":
            keys = row.get("project_tags") or ["untagged"]
        else:
            keys = [row.get("project_name") or "Unknown project"]
        for key in keys:
            bucket = buckets.setdefault(
                str(key),
                {
                    "group_key": str(key),
                    "model_calls": 0,
                    "sessions": set(),
                    "turns": set(),
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "uncached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "_cache_ratio_sum": 0.0,
                    "_reasoning_ratio_sum": 0.0,
                    "_context_sum": 0.0,
                    "latest_event": "",
                },
            )
            bucket["model_calls"] += 1
            bucket["sessions"].add(row.get("session_id"))
            if row.get("turn_id"):
                bucket["turns"].add(row.get("turn_id"))
            for token_key in (
                "input_tokens",
                "cached_input_tokens",
                "uncached_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
                "total_tokens",
            ):
                bucket[token_key] += int(row.get(token_key) or 0)
            bucket["estimated_cost_usd"] += float(row.get("estimated_cost_usd") or 0)
            bucket["_cache_ratio_sum"] += float(row.get("cache_ratio") or 0)
            bucket["_reasoning_ratio_sum"] += float(row.get("reasoning_output_ratio") or 0)
            bucket["_context_sum"] += float(row.get("context_window_percent") or 0)
            if str(row.get("event_timestamp") or "") > bucket["latest_event"]:
                bucket["latest_event"] = str(row.get("event_timestamp") or "")
    summaries: list[dict[str, Any]] = []
    for bucket in buckets.values():
        calls = max(int(bucket["model_calls"]), 1)
        bucket["sessions"] = len(bucket["sessions"])
        bucket["turns"] = len(bucket["turns"])
        bucket["avg_cache_ratio"] = bucket.pop("_cache_ratio_sum") / calls
        bucket["avg_reasoning_output_ratio"] = bucket.pop("_reasoning_ratio_sum") / calls
        bucket["avg_context_window_percent"] = bucket.pop("_context_sum") / calls
        summaries.append(bucket)
    summaries.sort(key=lambda row: (-int(row["total_tokens"]), str(row["group_key"])))
    return summaries[:limit]
