from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
    write_allowance_template,
)


def test_allowance_estimates_exact_codex_credit_usage() -> None:
    rows = annotate_rows_with_allowance(
        [
            {
                "model": "gpt-5.5",
                "input_tokens": 1000,
                "cached_input_tokens": 200,
                "uncached_input_tokens": 800,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
        ]
    )

    assert rows[0]["usage_credit_model"] == "gpt-5.5"
    assert rows[0]["usage_credit_confidence"] == "exact"
    assert rows[0]["usage_credits"] == 0.1775


def test_allowance_marks_inferred_auto_review_mapping() -> None:
    rows = annotate_rows_with_allowance(
        [
            {
                "model": "codex-auto-review",
                "input_tokens": 1000,
                "cached_input_tokens": 500,
                "uncached_input_tokens": 500,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
        ]
    )

    assert rows[0]["usage_credit_model"] == "gpt-5.3-codex"
    assert rows[0]["usage_credit_confidence"] == "estimated"
    assert rows[0]["usage_credits"] == 0.0590625


def test_allowance_config_loads_windows_and_local_aliases(tmp_path: Path) -> None:
    path = tmp_path / "allowance.json"
    path.write_text(
        json.dumps(
            {
                "windows": {
                    "five_hour": {
                        "label": "5h",
                        "remaining_percent": 79,
                        "reset_at": "2026-06-03T18:50:00-04:00",
                    }
                },
                "aliases": {
                    "local-codex": {
                        "model": "gpt-5.4-mini",
                        "confidence": "estimated",
                        "note": "Local test alias.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_allowance_config(path)
    rows = annotate_rows_with_allowance(
        [
            {
                "model": "local-codex",
                "input_tokens": 1000,
                "cached_input_tokens": 0,
                "uncached_input_tokens": 1000,
                "output_tokens": 100,
                "total_tokens": 1100,
            }
        ],
        config,
    )

    assert config.loaded is True
    assert config.windows[0].remaining_percent == 0.79
    assert config.windows[0].reset_at == "2026-06-03T18:50:00-04:00"
    assert rows[0]["usage_credit_model"] == "gpt-5.4-mini"
    assert rows[0]["usage_credit_note"] == "Local test alias."


def test_write_allowance_template_refuses_to_overwrite(tmp_path: Path) -> None:
    path = write_allowance_template(tmp_path / "allowance.json")

    try:
        write_allowance_template(path)
    except FileExistsError as exc:
        assert "Allowance config already exists" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")
