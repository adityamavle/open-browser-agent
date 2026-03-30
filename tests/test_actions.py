from __future__ import annotations

from open_browser_agent.actions import ActionAPI, ActionAPIError


class FakeLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self) -> str:
        return self._text


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    def press(self, keys: str) -> None:
        self.pressed.append(keys)


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test"
        self.keyboard = FakeKeyboard()
        self.clicked: list[str] = []
        self.filled: list[tuple[str, str]] = []
        self.waited: list[str] = []
        self.goto_urls: list[str] = []
        self.locator_values = {
            "p": "Summary text",
            "table": "row1 row2",
            "#target": "Target text",
        }
        self.evaluate_result = "Summary from evaluate"

    def goto(self, url: str) -> None:
        self.goto_urls.append(url)
        self.url = url

    def click(self, selector: str) -> None:
        self.clicked.append(selector)

    def fill(self, selector: str, text: str) -> None:
        self.filled.append((selector, text))

    def wait_for_selector(self, selector: str) -> None:
        self.waited.append(selector)

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self.locator_values[selector])

    def evaluate(self, script: str, arg=None):
        if "querySelectorAll('main p, article p, p')" in script:
            return self.evaluate_result
        if "reference a[href]" in script:
            return [
                {"text": "Example citation", "href": "https://example.com/citation"},
                {"text": "Another citation", "href": "https://example.com/another"},
            ]
        if "normalizeHeading" in script and "sectionName" not in script:
            return ["Early life", "Filmography", "Legacy"]
        if "sectionName" in script:
            assert arg == "Filmography"
            return "Section paragraph one.\n\nSection paragraph two."
        raise AssertionError("Unexpected evaluate script")


def test_actions_execute_successfully() -> None:
    page = FakePage()
    actions = ActionAPI(lambda: page)

    goto_result = actions.goto("https://example.test/form")
    click_result = actions.click("#submit")
    type_result = actions.type("#name", "Ada")
    press_result = actions.press("Enter")
    wait_result = actions.wait_for("form")
    extract_result = actions.extract("#target")

    assert goto_result.ok is True
    assert goto_result.details["current_url"] == "https://example.test/form"
    assert goto_result.details["resolved_url"] == "https://example.test/form"
    assert click_result.ok is True
    assert page.clicked == ["#submit"]
    assert type_result.ok is True
    assert page.filled == [("#name", "Ada")]
    assert press_result.ok is True
    assert page.keyboard.pressed == ["Enter"]
    assert wait_result.ok is True
    assert page.waited == ["form"]
    assert extract_result.details["value"] == "Target text"


def test_extract_uses_named_targets() -> None:
    page = FakePage()
    actions = ActionAPI(lambda: page)

    summary = actions.extract("summary")
    table = actions.extract("table")
    citation_links = actions.extract("citation_links")
    section_headings = actions.extract("section_headings")
    filmography = actions.extract("section:Filmography")

    assert summary.details["value"] == "Summary from evaluate"
    assert table.details["value"] == "row1 row2"
    assert citation_links.details["value"][0]["href"] == "https://example.com/citation"
    assert section_headings.details["value"][1] == "Filmography"
    assert "Section paragraph one." in filmography.details["value"]


def test_extract_summary_uses_evaluate_on_real_pages() -> None:
    class EvalPage(FakePage):
        def evaluate(self, script: str) -> str:
            assert "querySelectorAll('main p, article p, p')" in script
            return "Summary from evaluate"

    result = ActionAPI(lambda: EvalPage()).extract("summary")

    assert result.ok is True
    assert result.details["value"] == "Summary from evaluate"


def test_extract_citation_links_uses_evaluate_on_real_pages() -> None:
    result = ActionAPI(lambda: FakePage()).extract("citation_links")

    assert result.ok is True
    assert result.details["value"][0]["href"] == "https://example.com/citation"


def test_extract_section_headings_and_named_section_use_evaluate() -> None:
    actions = ActionAPI(lambda: FakePage())

    headings = actions.extract("section_headings")
    section = actions.extract("section:Filmography")

    assert headings.ok is True
    assert headings.details["value"] == ["Early life", "Filmography", "Legacy"]
    assert section.ok is True
    assert "Section paragraph two." in section.details["value"]


def test_extract_named_section_strips_edit_marker_only_results() -> None:
    class EditMarkerPage(FakePage):
        def evaluate(self, script: str, arg=None):
            if "sectionName" in script:
                return "Conservation actions paragraph.\n\nProtected habitat."
            return super().evaluate(script, arg)

    section = ActionAPI(lambda: EditMarkerPage()).extract("section:Conservation")

    assert section.ok is True
    assert "[edit]" not in section.details["value"]
    assert "Protected habitat." in section.details["value"]


def test_action_error_is_reported() -> None:
    class BrokenPage(FakePage):
        def click(self, selector: str) -> None:
            raise RuntimeError("missing selector")

    result = ActionAPI(lambda: BrokenPage()).click("#missing")
    assert result.ok is False
    assert result.error == "missing selector"
    assert result.error_code == "selector_not_found"


def test_action_failures_are_reported_for_other_methods() -> None:
    class BrokenPage:
        def __init__(self) -> None:
            self.url = "https://example.test"

        def goto(self, url: str) -> None:
            raise RuntimeError("goto failed")

        def fill(self, selector: str, text: str) -> None:
            raise RuntimeError("fill failed")

        def wait_for_selector(self, selector: str) -> None:
            raise RuntimeError("wait failed")

        @property
        def keyboard(self) -> FakeKeyboard:
            class BrokenKeyboard:
                def press(self, keys: str) -> None:
                    raise RuntimeError("press failed")

            return BrokenKeyboard()

    actions = ActionAPI(lambda: BrokenPage())

    assert actions.goto("https://example.test").error == "goto failed"
    assert actions.type("#name", "Ada").error == "fill failed"
    assert actions.wait_for("form").error == "wait failed"
    assert actions.press("Enter").error == "press failed"


def test_action_timeout_is_forwarded_when_supported() -> None:
    class TimeoutAwarePage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.timeout_seen: list[int] = []

        def goto(self, url: str, timeout: int | None = None) -> None:
            self.timeout_seen.append(timeout or 0)
            super().goto(url)

    page = TimeoutAwarePage()
    result = ActionAPI(lambda: page).goto("https://example.test/form", timeout_ms=4321)

    assert result.ok is True
    assert page.timeout_seen == [4321]
    assert result.details["timeout_ms"] == 4321


def test_action_timeout_error_code_is_classified() -> None:
    class TimeoutPage(FakePage):
        def wait_for_selector(self, selector: str) -> None:
            raise RuntimeError("Timeout 30000ms exceeded.")

    result = ActionAPI(lambda: TimeoutPage()).wait_for("#missing")

    assert result.ok is False
    assert result.error_code == "timeout"


def test_extract_error_is_reported() -> None:
    class MissingLocatorPage:
        def locator(self, selector: str) -> FakeLocator:
            raise RuntimeError("locator failed")

    result = ActionAPI(lambda: MissingLocatorPage()).extract("summary")
    assert result.ok is False
    assert result.error == "locator failed"


def test_missing_page_provider_raises() -> None:
    actions = ActionAPI(lambda: None)

    try:
        actions.goto("https://example.test")
    except ActionAPIError as exc:
        assert "no page" in str(exc).lower()
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected ActionAPIError")


def test_goto_uses_url_resolver() -> None:
    page = FakePage()
    actions = ActionAPI(lambda: page, url_resolver=lambda url: f"https://resolved.test/{url}")

    result = actions.goto("fixture://page")

    assert result.ok is True
    assert page.goto_urls == ["https://resolved.test/fixture://page"]
    assert result.details["resolved_url"] == "https://resolved.test/fixture://page"
