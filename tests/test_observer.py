from __future__ import annotations

from open_browser_agent.observer import Observer


class FakeLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self) -> str:
        return self._text


class FakePage:
    url = "https://example.test/page"

    def __init__(self) -> None:
        self.saved_screenshot = None

    def locator(self, selector: str) -> FakeLocator:
        assert selector == "body"
        return FakeLocator("This is visible text")

    def title(self) -> str:
        return "Example Page"

    def screenshot(self, path: str) -> None:
        self.saved_screenshot = path

    def snapshot_dom_summary(self) -> list[str]:
        return ["main:Example", "button:Submit"]

    def snapshot_form_state(self) -> list[str]:
        return ["input:text:username=Ada Lovelace", "textarea:comments=Ready"]


def test_observer_capture_uses_page_snapshot() -> None:
    page = FakePage()
    observer = Observer(lambda: page)

    observation = observer.capture(screenshot_path="shot.png")

    assert observation.url == "https://example.test/page"
    assert observation.title == "Example Page"
    assert observation.visible_text == "This is visible text"
    assert observation.dom_summary == ["main:Example", "button:Submit"]
    assert observation.form_state == ["input:text:username=Ada Lovelace", "textarea:comments=Ready"]
    assert observation.screenshot_path == "shot.png"
    assert page.saved_screenshot == "shot.png"


def test_observer_capture_truncates_text_and_dom() -> None:
    class DensePage(FakePage):
        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator("abcdefghij")

        def snapshot_dom_summary(self) -> list[str]:
            return [f"node:{index}" for index in range(5)]

        def snapshot_form_state(self) -> list[str]:
            return [f"field:{index}" for index in range(5)]

    observer = Observer(lambda: DensePage(), max_text_chars=4, max_dom_nodes=2, max_form_controls=3)
    observation = observer.capture()

    assert observation.visible_text == "abcd"
    assert observation.dom_summary == ["node:0", "node:1"]
    assert observation.form_state == ["field:0", "field:1", "field:2"]


def test_observer_capture_uses_evaluate_fallback() -> None:
    class EvalPage:
        url = "https://example.test/fallback"

        def __init__(self) -> None:
            self.saved_screenshot = None

        def locator(self, selector: str) -> FakeLocator:
            assert selector == "body"
            return FakeLocator("Fallback body")

        def title(self) -> str:
            return "Fallback"

        def evaluate(self, script: str) -> list[str]:
            if "selectedOptions" in script:
                assert "nav, header, aside, footer" in script
                assert "main, [role=\"main\"], article" in script
                return ["input:text:username=Ada", "textarea:comments=Ready", "input:checkbox:newsletter=yes"]
            assert "querySelectorAll" in script
            return ["main:Fallback", "button:Go"]

    page = EvalPage()
    observer = Observer(lambda: page)

    observation = observer.capture()
    assert observation.dom_summary == ["main:Fallback", "button:Go"]
    assert observation.form_state == [
        "input:text:username=Ada",
        "textarea:comments=Ready",
        "input:checkbox:newsletter=yes",
    ]


def test_observer_capture_handles_pages_without_form_hooks() -> None:
    class MinimalPage:
        url = "https://example.test/minimal"

        def locator(self, selector: str) -> FakeLocator:
            assert selector == "body"
            return FakeLocator("Body only")

        def title(self) -> str:
            return "Minimal"

    observation = Observer(lambda: MinimalPage()).capture()

    assert observation.dom_summary == []
    assert observation.form_state == []
