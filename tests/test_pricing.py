from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.pricing import (
    OPENAI_PRICING_MD_URL,
    PRICING_SCHEMA,
    load_pricing_config,
    parse_openai_pricing_markdown,
    update_pricing_from_openai_docs,
)


OPENAI_PRICING_FIXTURE = """
<TextTokenPricingTables
  client:load
  tier="standard"
  rows={[
    ["gpt-5.5 (<272K context length)", 5, 0.5, 30],
    ["gpt-5.4-mini", 0.75, 0.075, 4.5],
    ["gpt-5-pro", 15, null, 120],
  ]}
/>
<TextTokenPricingTables
  client:load
  tier="batch"
  rows={[
    ["gpt-5.5 (<272K context length)", 2.5, 0.25, 15],
  ]}
/>
"""


def test_parse_openai_pricing_markdown_for_selected_tier() -> None:
    models = parse_openai_pricing_markdown(OPENAI_PRICING_FIXTURE, tier="standard")

    assert models["gpt-5.5"]["input_per_million"] == 5
    assert models["gpt-5.5"]["cached_input_per_million"] == 0.5
    assert models["gpt-5.5"]["output_per_million"] == 30
    assert models["gpt-5.4-mini"]["output_per_million"] == 4.5
    assert models["gpt-5-pro"]["cached_input_per_million"] == 15


def test_parse_openai_pricing_markdown_uses_requested_tier() -> None:
    models = parse_openai_pricing_markdown(OPENAI_PRICING_FIXTURE, tier="batch")

    assert models == {
        "gpt-5.5": {
            "input_per_million": 2.5,
            "cached_input_per_million": 0.25,
            "output_per_million": 15.0,
        }
    }


def test_update_pricing_from_openai_docs_writes_source_metadata(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"

    result = update_pricing_from_openai_docs(
        pricing_path,
        fetch_text=lambda url: OPENAI_PRICING_FIXTURE,
    )
    raw = json.loads(pricing_path.read_text(encoding="utf-8"))
    config = load_pricing_config(pricing_path)

    assert result.model_count == 3
    assert result.source_url == OPENAI_PRICING_MD_URL
    assert raw["_schema"] == PRICING_SCHEMA
    assert raw["_source"]["url"] == OPENAI_PRICING_MD_URL
    assert raw["_source"]["tier"] == "standard"
    assert config.loaded
    assert config.source and config.source["name"] == "OpenAI Developers pricing docs"
    assert config.models["gpt-5.5"]["output_per_million"] == 30
