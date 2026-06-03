"""Codex usage allowance and credit estimation helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_ALLOWANCE_PATH


ALLOWANCE_SCHEMA = "codex-usage-tracker-allowance-v1"
CODEX_RATE_CARD_URL = "https://help.openai.com/en/articles/20001106-codex-rate-card"
CODEX_PRICING_URL = "https://developers.openai.com/codex/pricing"

DEFAULT_CREDIT_RATES = {
    "gpt-5.5": {
        "input_per_million": 125.0,
        "cached_input_per_million": 12.5,
        "output_per_million": 750.0,
    },
    "gpt-5.4": {
        "input_per_million": 62.5,
        "cached_input_per_million": 6.25,
        "output_per_million": 375.0,
    },
    "gpt-5.4-mini": {
        "input_per_million": 18.75,
        "cached_input_per_million": 1.875,
        "output_per_million": 113.0,
    },
    "gpt-5.3-codex": {
        "input_per_million": 43.75,
        "cached_input_per_million": 4.375,
        "output_per_million": 350.0,
    },
    "gpt-5.2": {
        "input_per_million": 43.75,
        "cached_input_per_million": 4.375,
        "output_per_million": 350.0,
    },
}

DEFAULT_ALIASES = {
    "codex-auto-review": {
        "model": "gpt-5.3-codex",
        "confidence": "estimated",
        "note": "Inferred from the Codex rate card note that code review runs on GPT-5.3-Codex.",
    }
}

DEFAULT_SOURCE = {
    "name": "OpenAI Codex rate card",
    "url": CODEX_RATE_CARD_URL,
    "pricing_url": CODEX_PRICING_URL,
    "fetched_at": "2026-06-03",
    "basis": "credits per 1M input, cached input, and output tokens",
}

ALLOWANCE_TEMPLATE = {
    "schema": ALLOWANCE_SCHEMA,
    "_comment": (
        "Optional. Copy remaining usage values from Codex Settings > Usage or "
        "from /status. Percent values can be 0-100 or 0-1. Add total_credits "
        "only when your plan or workspace exposes an exact credit allowance."
    ),
    "windows": [
        {
            "key": "five_hour",
            "label": "5h",
            "remaining_percent": None,
            "reset_at": None,
            "captured_at": None,
            "total_credits": None,
            "remaining_credits": None,
        },
        {
            "key": "weekly",
            "label": "Weekly",
            "remaining_percent": None,
            "reset_at": None,
            "captured_at": None,
            "total_credits": None,
            "remaining_credits": None,
        },
    ],
    "credit_rates": {},
    "aliases": {},
}


@dataclass(frozen=True)
class AllowanceWindow:
    """One configured usage-limit window from the user's local allowance file."""

    key: str
    label: str
    total_credits: float | None = None
    remaining_credits: float | None = None
    remaining_percent: float | None = None
    reset_at: str | None = None
    captured_at: str | None = None


@dataclass(frozen=True)
class UsageAllowanceConfig:
    """Local usage allowance config plus bundled Codex credit rates."""

    path: Path
    credit_rates: dict[str, dict[str, float]]
    aliases: dict[str, dict[str, str]]
    windows: list[AllowanceWindow]
    loaded: bool
    source: dict[str, Any]
    error: str | None = None


def load_allowance_config(path: Path = DEFAULT_ALLOWANCE_PATH) -> UsageAllowanceConfig:
    """Load optional allowance settings while always keeping bundled rate-card data."""

    credit_rates = dict(DEFAULT_CREDIT_RATES)
    aliases = dict(DEFAULT_ALIASES)
    windows: list[AllowanceWindow] = []
    if not path.exists():
        return UsageAllowanceConfig(
            path=path,
            credit_rates=credit_rates,
            aliases=aliases,
            windows=windows,
            loaded=False,
            source=dict(DEFAULT_SOURCE),
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        credit_rates.update(parse_credit_rates(raw.get("credit_rates", {})))
        aliases.update(parse_aliases(raw.get("aliases", {})))
        windows = parse_windows(raw.get("windows", []))
        source = raw.get("_source") if isinstance(raw.get("_source"), dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return UsageAllowanceConfig(
            path=path,
            credit_rates=credit_rates,
            aliases=aliases,
            windows=[],
            loaded=False,
            source=dict(DEFAULT_SOURCE),
            error=str(exc),
        )

    return UsageAllowanceConfig(
        path=path,
        credit_rates=credit_rates,
        aliases=aliases,
        windows=windows,
        loaded=True,
        source={**DEFAULT_SOURCE, **source},
    )


def write_allowance_template(
    path: Path = DEFAULT_ALLOWANCE_PATH, force: bool = False
) -> Path:
    """Write a local template for optional allowance-window settings."""

    if path.exists() and not force:
        raise FileExistsError(f"Allowance config already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ALLOWANCE_TEMPLATE, indent=2) + "\n", encoding="utf-8")
    return path


def annotate_rows_with_allowance(
    rows: list[dict[str, Any]],
    config: UsageAllowanceConfig | None = None,
    *,
    model_field: str = "model",
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
) -> list[dict[str, Any]]:
    """Return copied rows with Codex credit usage annotations."""

    resolved = config or load_allowance_config(allowance_path)
    annotated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        model = copy.get(model_field)
        match = resolve_credit_rate(model, resolved)
        if match is None:
            copy.update(
                {
                    "usage_credits": None,
                    "usage_credit_model": None,
                    "usage_credit_confidence": "unknown",
                    "usage_credit_source": "No Codex credit rate",
                    "usage_credit_note": "No bundled or configured credit rate matched this model.",
                }
            )
        else:
            rated_model, rates, confidence, note = match
            copy.update(
                {
                    "usage_credits": estimate_usage_credits(copy, rates),
                    "usage_credit_model": rated_model,
                    "usage_credit_confidence": confidence,
                    "usage_credit_source": resolved.source.get("name", "Codex credit rates"),
                    "usage_credit_note": note,
                }
            )
        annotated.append(copy)
    return annotated


def summarize_allowance_usage(
    rows: list[dict[str, Any]], config: UsageAllowanceConfig | None = None
) -> dict[str, Any]:
    """Summarize Codex credit usage and configured allowance windows."""

    resolved = config or load_allowance_config()
    total_tokens = sum(_number(row.get("total_tokens")) for row in rows)
    rated_tokens = sum(
        _number(row.get("total_tokens"))
        for row in rows
        if row.get("usage_credits") is not None
    )
    usage_credits = sum(
        _number(row.get("usage_credits"))
        for row in rows
        if row.get("usage_credits") is not None
    )
    estimated_credits = sum(
        _number(row.get("usage_credits"))
        for row in rows
        if row.get("usage_credit_confidence") == "estimated"
    )
    exact_credits = max(usage_credits - estimated_credits, 0.0)
    return {
        "usage_credits": usage_credits,
        "exact_usage_credits": exact_credits,
        "estimated_usage_credits": estimated_credits,
        "rated_tokens": rated_tokens,
        "unrated_tokens": max(total_tokens - rated_tokens, 0.0),
        "credit_token_ratio": rated_tokens / total_tokens if total_tokens else 0.0,
        "windows": [asdict(window) for window in resolved.windows],
        "source": resolved.source,
        "configured": resolved.loaded,
        "error": resolved.error,
    }


def resolve_credit_rate(
    model: object, config: UsageAllowanceConfig
) -> tuple[str, dict[str, float], str, str] | None:
    """Resolve a model label into a credit rate, confidence, and note."""

    normalized = _normalize_model(model)
    if not normalized:
        return None
    direct = config.credit_rates.get(normalized)
    if direct is not None:
        return normalized, direct, "exact", "Direct match to bundled or configured Codex credit rates."

    alias = config.aliases.get(normalized)
    if not alias:
        return None
    target = _normalize_model(alias.get("model"))
    if not target:
        return None
    rates = config.credit_rates.get(target)
    if rates is None:
        return None
    confidence = alias.get("confidence") or "estimated"
    note = alias.get("note") or f"Mapped from {normalized} to {target} by local alias."
    return target, rates, confidence, note


def estimate_usage_credits(row: dict[str, Any], rates: dict[str, float]) -> float:
    """Estimate Codex credits from aggregate token counters."""

    input_rate = rates["input_per_million"]
    cached_rate = rates["cached_input_per_million"]
    output_rate = rates["output_per_million"]
    cached_input = _number(row.get("cached_input_tokens"))
    uncached_input = _number(row.get("uncached_input_tokens"))
    if uncached_input <= 0:
        uncached_input = max(_number(row.get("input_tokens")) - cached_input, 0.0)
    output_tokens = _number(row.get("output_tokens"))
    return (
        (uncached_input * input_rate)
        + (cached_input * cached_rate)
        + (output_tokens * output_rate)
    ) / 1_000_000


def parse_credit_rates(raw: object) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, dict[str, float]] = {}
    for model, rates in raw.items():
        normalized = _normalize_model(model)
        if not normalized or not isinstance(rates, dict):
            continue
        parsed[normalized] = {
            "input_per_million": _required_rate(rates, "input_per_million", normalized),
            "cached_input_per_million": _required_rate(
                rates, "cached_input_per_million", normalized
            ),
            "output_per_million": _required_rate(rates, "output_per_million", normalized),
        }
    return parsed


def parse_aliases(raw: object) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, dict[str, str]] = {}
    for source, target in raw.items():
        source_model = _normalize_model(source)
        if not source_model:
            continue
        if isinstance(target, str):
            parsed[source_model] = {
                "model": _normalize_model(target) or target,
                "confidence": "estimated",
                "note": f"Mapped from {source_model} by local allowance config.",
            }
        elif isinstance(target, dict):
            target_model = _normalize_model(target.get("model"))
            if not target_model:
                continue
            parsed[source_model] = {
                "model": target_model,
                "confidence": _optional_str(target.get("confidence")) or "estimated",
                "note": _optional_str(target.get("note"))
                or f"Mapped from {source_model} by local allowance config.",
            }
    return parsed


def parse_windows(raw: object) -> list[AllowanceWindow]:
    if isinstance(raw, dict):
        rows = [{**value, "key": key} for key, value in raw.items() if isinstance(value, dict)]
    elif isinstance(raw, list):
        rows = [value for value in raw if isinstance(value, dict)]
    else:
        rows = []

    windows: list[AllowanceWindow] = []
    for row in rows:
        key = _optional_str(row.get("key"))
        if not key:
            continue
        label = _optional_str(row.get("label")) or key.replace("_", " ").title()
        windows.append(
            AllowanceWindow(
                key=key,
                label=label,
                total_credits=_optional_positive_number(row.get("total_credits")),
                remaining_credits=_optional_positive_number(row.get("remaining_credits")),
                remaining_percent=_optional_percent(row.get("remaining_percent")),
                reset_at=_optional_str(row.get("reset_at")),
                captured_at=_optional_str(row.get("captured_at")),
            )
        )
    return windows


def _normalize_model(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower().replace("_", "-")


def _required_rate(raw: dict[str, Any], key: str, model: str) -> float:
    parsed = _optional_positive_number(raw.get(key))
    if parsed is None:
        raise ValueError(f"missing {key} for Codex credit model {model}")
    return parsed


def _optional_positive_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    number = _number(value)
    if number < 0:
        raise ValueError("allowance values cannot be negative")
    return number


def _optional_percent(value: object) -> float | None:
    parsed = _optional_positive_number(value)
    if parsed is None:
        return None
    return parsed / 100 if parsed > 1 else parsed


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0
