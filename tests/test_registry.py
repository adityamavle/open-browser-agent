from __future__ import annotations

from open_browser_agent.tasks.registry import find_task_by_goal


def test_find_task_by_goal_matches_alias() -> None:
    task = find_task_by_goal("wiki summary")
    assert task is not None
    assert task.task_id == "wikipedia-summary"


def test_find_task_by_goal_matches_summary_substring() -> None:
    task = find_task_by_goal("html table")
    assert task is not None
    assert task.task_id == "table-scrape"


def test_find_task_by_goal_returns_none_for_empty_input() -> None:
    assert find_task_by_goal("") is None


def test_find_task_by_goal_matches_press_task_alias() -> None:
    task = find_task_by_goal("wiki press")
    assert task is not None
    assert task.task_id == "wikipedia-search-press"


def test_find_task_by_goal_builds_dynamic_wikipedia_task_from_topic_prompt() -> None:
    task = find_task_by_goal("summarize Grace Hopper from Wikipedia")

    assert task is not None
    assert task.task_id == "wikipedia-summary"
    assert task.steps[0].args["url"] == "https://en.wikipedia.org/wiki/Grace_Hopper"
    assert task.steps[3].args["target"] == "citation_links"
    assert task.verification_rules[0].value == "Grace_Hopper"
    assert task.verification_rules[1].kind == "artifact_exists"
    assert task.verification_rules[1].value == "extracts.summary"
    assert task.verification_rules[2].kind == "artifact_list_min_length"


def test_find_task_by_goal_builds_dynamic_wikipedia_task_from_article_url() -> None:
    task = find_task_by_goal("open https://en.wikipedia.org/wiki/Alan_Turing and extract the summary")

    assert task is not None
    assert task.task_id == "wikipedia-summary"
    assert task.steps[0].args["url"] == "https://en.wikipedia.org/wiki/Alan_Turing"
    assert task.verification_rules[0].value == "Alan_Turing"
    assert task.verification_rules[1].value == "extracts.summary"
    assert task.verification_rules[2].value == {"path": "extracts.citation_links", "min": 1}


def test_find_task_by_goal_builds_wikipedia_section_task() -> None:
    task = find_task_by_goal("extract the filmography section for Leonardo DiCaprio from Wikipedia")

    assert task is not None
    assert task.task_id == "wikipedia-section"
    assert task.steps[0].args["url"] == "https://en.wikipedia.org/wiki/Leonardo_DiCaprio"
    assert task.steps[2].args["target"] == "section_headings"
    assert task.steps[3].args["target"] == "section:Filmography"
    assert task.verification_rules[2].kind == "artifact_text_min_length"
    assert task.verification_rules[2].value == {"path": "extracts.section:Filmography", "min_chars": 20}


def test_find_task_by_goal_builds_wikipedia_section_headings_task() -> None:
    task = find_task_by_goal("show section headings for Grace Hopper from Wikipedia")

    assert task is not None
    assert task.task_id == "wikipedia-section-headings"
    assert task.steps[2].args["target"] == "section_headings"


def test_find_task_by_goal_builds_bestbuy_comparison_task() -> None:
    task = find_task_by_goal("Compare Best Buy laptops by price, display size, RAM, and storage and export to csv")

    assert task is not None
    assert task.task_id == "bestbuy-laptop-comparison"
    assert task.steps[0].args["url"].startswith("file:///")
    assert task.steps[2].args["target"] == "bestbuy_search_results"
    assert task.steps[5].args["target"] == "bestbuy_product_facts"
    assert task.steps[10].args["target"] == "bestbuy_price"


def test_find_task_by_goal_builds_bestbuy_comparison_task_from_multiline_goal() -> None:
    task = find_task_by_goal(
        "Compare Best Buy laptops by price,\n"
        "  display size, RAM, and storage and export to\n"
        "  csv"
    )

    assert task is not None
    assert task.task_id == "bestbuy-laptop-comparison"


def test_find_task_by_goal_builds_live_bestbuy_comparison_task() -> None:
    task = find_task_by_goal(
        "Compare live Best Buy gaming laptops by price, GPU, display size, RAM, and storage and export to csv"
    )

    assert task is not None
    assert task.task_id == "bestbuy-live-comparison"
    assert task.steps[0].args["url"] == "https://www.bestbuy.com/site/searchpage.jsp?st=gaming+laptops"
    assert [step.type for step in task.steps] == ["navigate", "wait_for", "extract"]
    assert task.steps[2].args["target"] == "bestbuy_search_results"


def test_find_task_by_goal_caps_live_bestbuy_product_count() -> None:
    task = find_task_by_goal("Compare live Best Buy top 9 laptops by price and storage and export to csv")

    assert task is not None
    assert task.steps[0].args["url"] == "https://www.bestbuy.com/site/searchpage.jsp?st=laptops"
    assert "up to 5 search results" in task.verifier_hint
