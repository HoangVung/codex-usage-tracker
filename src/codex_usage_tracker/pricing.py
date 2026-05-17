"""Local-only pricing and efficiency helpers for aggregate usage rows."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from codex_usage_tracker.paths import DEFAULT_PRICING_PATH

OPENAI_PRICING_MD_URL = "https://developers.openai.com/api/docs/pricing.md"
PRICING_SCHEMA = "codex-usage-tracker-pricing-v1"
VALID_PRICING_TIERS = ("standard", "batch", "flex", "priority")

PRICING_TEMPLATE = {
    "_comment": (
        "Fill in current prices in USD per 1 million tokens. The tracker does "
        "not fetch pricing during normal reports. Prefer update-pricing when "
        "you want to cache current OpenAI-published rates locally."
    ),
    "models": {
        "replace-with-model-name": {
            "input_per_million": 0.0,
            "cached_input_per_million": 0.0,
            "output_per_million": 0.0,
        }
    },
}


@dataclass(frozen=True)
class PricingConfig:
    """Parsed local model pricing config."""

    path: Path
    models: dict[str, dict[str, float]]
    loaded: bool
    source: dict[str, Any] | None = None
    error: str | None = None

    def rates_for(self, model: object) -> dict[str, float] | None:
        if not isinstance(model, str) or not model:
            return None
        return self.models.get(model)


def load_pricing_config(path: Path = DEFAULT_PRICING_PATH) -> PricingConfig:
    """Load optional local pricing without contacting external services."""

    if not path.exists():
        return PricingConfig(path=path, models={}, loaded=False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        models = _parse_models(raw)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return PricingConfig(path=path, models={}, loaded=False, error=str(exc))
    source = raw.get("_source") if isinstance(raw, dict) else None
    return PricingConfig(
        path=path,
        models=models,
        loaded=True,
        source=source if isinstance(source, dict) else None,
    )


@dataclass(frozen=True)
class PricingUpdateResult:
    """Result from refreshing the local pricing cache."""

    path: Path
    source_url: str
    tier: str
    fetched_at: str
    model_count: int
    backup_path: Path | None = None


def write_pricing_template(path: Path = DEFAULT_PRICING_PATH, force: bool = False) -> Path:
    """Write a local pricing template for user-maintained cost estimates."""

    if path.exists() and not force:
        raise FileExistsError(f"Pricing config already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(PRICING_TEMPLATE, indent=2) + "\n", encoding="utf-8")
    return path


def update_pricing_from_openai_docs(
    path: Path = DEFAULT_PRICING_PATH,
    *,
    tier: str = "standard",
    source_url: str = OPENAI_PRICING_MD_URL,
    fetch_text: Callable[[str], str] | None = None,
) -> PricingUpdateResult:
    """Fetch OpenAI-published pricing rows and cache them in the local config."""

    if tier not in VALID_PRICING_TIERS:
        raise ValueError(
            f"unknown pricing tier {tier!r}; expected one of {', '.join(VALID_PRICING_TIERS)}"
        )
    fetcher = fetch_text or _fetch_text
    text = fetcher(source_url)
    models = parse_openai_pricing_markdown(text, tier=tier)
    if not models:
        raise ValueError(
            f"no text-token pricing rows were parsed from {source_url} for tier {tier}"
        )

    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    payload = {
        "_schema": PRICING_SCHEMA,
        "_source": {
            "name": "OpenAI Developers pricing docs",
            "url": source_url,
            "tier": tier,
            "fetched_at": fetched_at,
            "model_count": len(models),
        },
        "models": models,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = _backup_existing_pricing(path)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return PricingUpdateResult(
        path=path,
        source_url=source_url,
        tier=tier,
        fetched_at=fetched_at,
        model_count=len(models),
        backup_path=backup_path,
    )


def parse_openai_pricing_markdown(
    markdown: str, *, tier: str = "standard"
) -> dict[str, dict[str, float]]:
    """Parse text-token rows from OpenAI's pricing markdown for one service tier."""

    if tier not in VALID_PRICING_TIERS:
        raise ValueError(
            f"unknown pricing tier {tier!r}; expected one of {', '.join(VALID_PRICING_TIERS)}"
        )
    rows_block = _extract_text_token_rows_block(markdown, tier)
    models: dict[str, dict[str, float]] = {}
    for match in _OPENAI_PRICE_ROW_RE.finditer(rows_block):
        model = _normalize_model_name(match.group("model"))
        input_rate = _parse_openai_price_value(match.group("input"))
        cached_rate = _parse_openai_price_value(match.group("cached"))
        output_rate = _parse_openai_price_value(match.group("output"))
        if not model or input_rate is None or output_rate is None:
            continue
        if cached_rate is None:
            cached_rate = input_rate
        models[model] = {
            "input_per_million": input_rate,
            "cached_input_per_million": cached_rate,
            "output_per_million": output_rate,
        }
    return models


def annotate_rows_with_efficiency(
    rows: list[dict[str, Any]],
    pricing: PricingConfig | None = None,
    *,
    model_field: str = "model",
) -> list[dict[str, Any]]:
    """Return copied rows with local cost estimates and efficiency flags."""

    config = pricing or load_pricing_config()
    annotated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        model = copy.get(model_field)
        cost = estimate_cost_usd(copy, config, model=model)
        savings = estimate_cache_savings_usd(copy, config, model=model)
        copy["estimated_cost_usd"] = cost
        copy["estimated_cache_savings_usd"] = savings
        copy["efficiency_flags"] = efficiency_flags(copy)
        annotated.append(copy)
    return annotated


def estimate_cost_usd(
    row: dict[str, Any], pricing: PricingConfig, *, model: object | None = None
) -> float | None:
    """Estimate call cost from aggregate tokens and local model rates."""

    rates = pricing.rates_for(model if model is not None else row.get("model"))
    if not rates:
        return None

    input_rate = rates.get("input_per_million")
    cached_rate = rates.get("cached_input_per_million", input_rate)
    output_rate = rates.get("output_per_million")
    if input_rate is None or cached_rate is None or output_rate is None:
        return None

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


def estimate_cache_savings_usd(
    row: dict[str, Any], pricing: PricingConfig, *, model: object | None = None
) -> float | None:
    """Estimate local cache savings when cached input has a lower configured rate."""

    rates = pricing.rates_for(model if model is not None else row.get("model"))
    if not rates:
        return None
    input_rate = rates.get("input_per_million")
    cached_rate = rates.get("cached_input_per_million")
    if input_rate is None or cached_rate is None or cached_rate >= input_rate:
        return None
    return (_number(row.get("cached_input_tokens")) * (input_rate - cached_rate)) / 1_000_000


def efficiency_flags(row: dict[str, Any]) -> list[str]:
    """Generate aggregate-only signals worth reviewing."""

    flags: list[str] = []
    total_tokens = _number(row.get("total_tokens"))
    output_tokens = _number(row.get("output_tokens"))
    input_tokens = _number(row.get("input_tokens"))
    context = _number(row.get("context_window_percent"))
    cache = _number(row.get("cache_ratio"))
    reasoning = _number(row.get("reasoning_output_ratio"))
    cost = row.get("estimated_cost_usd")

    if context >= 0.8:
        flags.append("high context use")
    elif context >= 0.5:
        flags.append("elevated context use")
    if reasoning >= 0.75 and output_tokens >= 100:
        flags.append("high reasoning share")
    if input_tokens >= 10_000 and cache < 0.1:
        flags.append("low cache reuse")
    if total_tokens >= 20_000 and output_tokens <= 100:
        flags.append("expensive low-output call")
    if isinstance(cost, int | float) and cost >= 1:
        flags.append("high estimated cost")
    return flags


def _parse_models(raw: object) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        raise ValueError("pricing config must be a JSON object")
    model_payload = raw.get("models", raw)
    if not isinstance(model_payload, dict):
        raise ValueError("pricing config 'models' must be an object")

    models: dict[str, dict[str, float]] = {}
    for model, rates in model_payload.items():
        if not isinstance(model, str):
            continue
        if model.startswith("_"):
            continue
        if not isinstance(rates, dict):
            continue
        parsed = {
            "input_per_million": _required_rate(rates, "input_per_million", model),
            "cached_input_per_million": _optional_rate(
                rates, "cached_input_per_million"
            ),
            "output_per_million": _required_rate(rates, "output_per_million", model),
        }
        if parsed["cached_input_per_million"] is None:
            parsed["cached_input_per_million"] = parsed["input_per_million"]
        models[model] = {key: float(value) for key, value in parsed.items()}
    return models


_OPENAI_PRICE_ROW_RE = re.compile(
    r"""\[
        \s*"(?P<model>[^"]+)"\s*,
        \s*(?P<input>[^,\]\n]+)\s*,
        \s*(?P<cached>[^,\]\n]+)\s*,
        \s*(?P<output>[^,\]\n]+)\s*
    \]""",
    re.VERBOSE,
)


def _fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/markdown,text/plain;q=0.9,*/*;q=0.1",
            "User-Agent": "codex-usage-tracker/0.1",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"could not fetch pricing source {url}: {exc}") from exc


def _backup_existing_pricing(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.{stamp}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def _extract_text_token_rows_block(markdown: str, tier: str) -> str:
    tier_marker = f'tier="{tier}"'
    tier_index = markdown.find(tier_marker)
    if tier_index == -1:
        raise ValueError(f"pricing source does not contain tier {tier!r}")
    rows_marker_index = markdown.find("rows={[", tier_index)
    if rows_marker_index == -1:
        raise ValueError(f"pricing source tier {tier!r} does not contain rows")
    bracket_index = markdown.find("[", rows_marker_index)
    if bracket_index == -1:
        raise ValueError(f"pricing source tier {tier!r} has malformed rows")
    end_index = _find_matching_bracket(markdown, bracket_index)
    return markdown[bracket_index + 1 : end_index]


def _find_matching_bracket(text: str, start_index: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("pricing source contains an unterminated rows block")


def _normalize_model_name(model: str) -> str:
    return re.sub(r"\s+\([^)]*context length[^)]*\)\s*$", "", model.strip(), flags=re.I)


def _parse_openai_price_value(value: str) -> float | None:
    normalized = value.strip()
    if normalized in {"", "null", "undefined", "-", '""', "''", '"-"', "'-'"}:
        return None
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in {'"', "'"}
    ):
        normalized = normalized[1:-1].strip()
    if normalized in {"", "-", "Free"}:
        return None
    return float(normalized.replace("_", ""))


def _required_rate(rates: dict[str, Any], key: str, model: str) -> float:
    value = _optional_rate(rates, key)
    if value is None:
        raise ValueError(f"missing {key} for model {model}")
    return value


def _optional_rate(rates: dict[str, Any], key: str) -> float | None:
    value = rates.get(key)
    if value is None:
        return None
    parsed = _number(value)
    if parsed < 0:
        raise ValueError(f"{key} cannot be negative")
    return parsed


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0
