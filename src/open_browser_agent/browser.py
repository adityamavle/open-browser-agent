from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class BrowserConfig:
    headless: bool = True
    timeout_ms: int = 10_000


class BrowserSessionError(RuntimeError):
    """Raised when the browser session is unavailable or misconfigured."""


class BrowserSession:
    """Thin wrapper around the Playwright browser lifecycle."""

    def __init__(
        self,
        config: BrowserConfig | None = None,
        playwright_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config or BrowserConfig()
        self._playwright_factory = playwright_factory
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    @property
    def page(self) -> Any:
        if self._page is None:
            raise BrowserSessionError("Browser session has not been started.")
        return self._page

    def start(self) -> Any:
        if self._page is not None:
            return self._page

        factory = self._playwright_factory or self._default_playwright_factory
        self._playwright = factory().start()
        self._browser = self._playwright.chromium.launch(headless=self.config.headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.config.timeout_ms)
        return self._page

    def stop(self) -> None:
        errors: list[str] = []

        for resource_name in ("_page", "_context", "_browser", "_playwright"):
            resource = getattr(self, resource_name)
            if resource is None:
                continue
            try:
                resource.close() if resource_name != "_playwright" else resource.stop()
            except Exception as exc:  # pragma: no cover - defensive close path
                errors.append(f"{resource_name}: {exc}")
            finally:
                setattr(self, resource_name, None)

        if errors:
            raise BrowserSessionError("; ".join(errors))

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    def _default_playwright_factory(self) -> Any:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on external package
            raise BrowserSessionError(
                "Playwright is not installed. Install requirements and run 'playwright install chromium'."
            ) from exc
        return sync_playwright()
