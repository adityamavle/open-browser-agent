from __future__ import annotations

import pytest

from open_browser_agent.comparison import (
    AnthropicComparisonRowSynthesizer,
    extract_requested_columns,
    infer_output_mode,
    parse_comparison_intent,
)


def test_infer_output_mode_defaults_to_text() -> None:
    assert infer_output_mode("Compare endangered birds in South America by population and habitat") == "text"


def test_infer_output_mode_detects_csv_request() -> None:
    assert infer_output_mode("Compare endangered birds in South America by population and habitat and export to csv") == "csv"


def test_extract_requested_columns_preserves_bounded_requested_dimensions() -> None:
    columns = extract_requested_columns(
        "Compare endangered birds in South America by population, physical attributes, conservation initiatives, habitat, and status"
    )

    assert columns == [
        "population",
        "physical attributes",
        "conservation initiatives",
        "habitat",
        "status",
    ]


def test_extract_requested_columns_caps_at_five() -> None:
    columns = extract_requested_columns(
        "Compare endangered birds by population, habitat, status, threats, range, and initiatives"
    )

    assert columns == ["population", "habitat", "status", "threats", "range"]


def test_extract_requested_columns_returns_empty_when_not_present() -> None:
    assert extract_requested_columns("Compare endangered birds in South America") == []


def test_extract_requested_columns_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="max_columns must be at least 1"):
        extract_requested_columns("Compare endangered birds by habitat", max_columns=0)


def test_parse_comparison_intent_extracts_subject_columns_and_output_mode() -> None:
    intent = parse_comparison_intent(
        "Compare endangered birds in South America by population, habitat, and conservation initiatives and export to csv"
    )

    assert intent is not None
    assert intent.subject == "endangered birds in South America"
    assert intent.requested_columns == ["population", "habitat", "conservation initiatives"]
    assert intent.output_mode == "csv"


def test_parse_comparison_intent_normalizes_multiline_goal() -> None:
    intent = parse_comparison_intent(
        "Compare Best Buy laptops by price,\n"
        "  display size, RAM, and storage and export to\n"
        "  csv"
    )

    assert intent is not None
    assert intent.subject == "Best Buy laptops"
    assert intent.requested_columns == ["price", "display size", "RAM", "storage"]
    assert intent.output_mode == "csv"


def test_parse_comparison_intent_returns_none_for_non_comparison_goal() -> None:
    assert parse_comparison_intent("summarize Grace Hopper from Wikipedia") is None


def test_anthropic_comparison_synthesizer_parses_rows() -> None:
    class FakeTransport:
        def post_json(self, url, headers, payload, timeout_s):
            _ = url, headers, payload, timeout_s
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"rows":['
                            '{"entity_name":"Spix\'s macaw","article_url":"https://en.wikipedia.org/wiki/Spix%27s_macaw",'
                            '"habitat":"Gallery woodland in Bahia","conservation initiatives":"Reintroduction and breeding programs"}'
                            ']}'
                        ),
                    }
                ]
            }

    synthesizer = AnthropicComparisonRowSynthesizer(
        api_key="test-key",
        model="claude-sonnet-4-6",
        transport=FakeTransport(),
    )

    result = synthesizer.synthesize(
        subject="endangered birds in South America",
        columns=["habitat", "conservation initiatives"],
        raw_rows=[
            {
                "entity_name": "Spix's macaw",
                "article_url": "https://en.wikipedia.org/wiki/Spix%27s_macaw",
                "habitat": "Very long raw habitat text",
                "conservation initiatives": "Very long raw conservation text",
            }
        ],
    )

    assert result.provider == "anthropic"
    assert result.model == "claude-sonnet-4-6"
    assert result.rows[0]["habitat"] == "Gallery woodland in Bahia"
