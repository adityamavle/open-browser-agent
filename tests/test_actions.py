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

    assert summary.details["value"] == "Summary text"
    assert table.details["value"] == "row1 row2"


def test_action_error_is_reported() -> None:
    class BrokenPage(FakePage):
        def click(self, selector: str) -> None:
            raise RuntimeError("missing selector")

    result = ActionAPI(lambda: BrokenPage()).click("#missing")
    assert result.ok is False
    assert result.error == "missing selector"


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
