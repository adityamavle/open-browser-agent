from __future__ import annotations

from open_browser_agent.browser import BrowserConfig, BrowserSession, BrowserSessionError


class FakePlaywrightRoot:
    def __init__(self) -> None:
        self.chromium = FakeChromium()
        self.stopped = False

    def start(self) -> "FakePlaywrightRoot":
        return self

    def stop(self) -> None:
        self.stopped = True


class FakeChromium:
    def __init__(self) -> None:
        self.launched = False
        self.browser = FakeBrowser()

    def launch(self, headless: bool) -> "FakeBrowser":
        self.launched = headless is False or headless is True
        return self.browser


class FakeBrowser:
    def __init__(self) -> None:
        self.context = FakeContext()
        self.closed = False

    def new_context(self) -> "FakeContext":
        return self.context

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()
        self.closed = False

    def new_page(self) -> "FakePage":
        return self.page

    def close(self) -> None:
        self.closed = True


class FakePage:
    def __init__(self) -> None:
        self.closed = False
        self.timeout_ms = None

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.timeout_ms = timeout_ms

    def close(self) -> None:
        self.closed = True


def test_browser_session_start_stop() -> None:
    root = FakePlaywrightRoot()
    session = BrowserSession(
        config=BrowserConfig(headless=True, timeout_ms=3210),
        playwright_factory=lambda: root,
    )

    page = session.start()

    assert page.timeout_ms == 3210
    assert session.page is page

    session.stop()

    assert root.stopped is True
    assert root.chromium.browser.closed is True
    assert root.chromium.browser.context.closed is True
    assert page.closed is True


def test_browser_session_page_requires_start() -> None:
    session = BrowserSession(playwright_factory=lambda: FakePlaywrightRoot())

    try:
        _ = session.page
    except BrowserSessionError as exc:
        assert "not been started" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected BrowserSessionError")


def test_browser_session_start_is_idempotent() -> None:
    root = FakePlaywrightRoot()
    session = BrowserSession(playwright_factory=lambda: root)

    first = session.start()
    second = session.start()

    assert first is second


def test_browser_session_context_manager() -> None:
    root = FakePlaywrightRoot()

    with BrowserSession(playwright_factory=lambda: root) as session:
        assert session.page is not None

    assert root.stopped is True


def test_browser_session_stop_aggregates_close_errors() -> None:
    class BrokenPage(FakePage):
        def close(self) -> None:
            raise RuntimeError("page close failed")

    root = FakePlaywrightRoot()
    root.chromium.browser.context.page = BrokenPage()
    session = BrowserSession(playwright_factory=lambda: root)
    session.start()

    try:
        session.stop()
    except BrowserSessionError as exc:
        assert "_page" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected BrowserSessionError")
