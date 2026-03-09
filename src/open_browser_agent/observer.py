from __future__ import annotations

from typing import Any, Callable

from open_browser_agent.schemas.observation import Observation


class Observer:
    """Captures compact page state for planning, verification, and debugging."""

    def __init__(
        self,
        page_provider: Callable[[], Any],
        max_text_chars: int = 2_000,
        max_dom_nodes: int = 20,
    ) -> None:
        self._page_provider = page_provider
        self.max_text_chars = max_text_chars
        self.max_dom_nodes = max_dom_nodes

    def capture(self, screenshot_path: str | None = None) -> Observation:
        page = self._page_provider()
        visible_text = page.locator("body").inner_text().strip()
        visible_text = visible_text[: self.max_text_chars]
        dom_summary = self._capture_dom_summary(page)

        if screenshot_path:
            page.screenshot(path=screenshot_path)

        return Observation(
            url=page.url,
            title=page.title(),
            visible_text=visible_text,
            dom_summary=dom_summary[: self.max_dom_nodes],
            screenshot_path=screenshot_path,
        )

    def _capture_dom_summary(self, page: Any) -> list[str]:
        if hasattr(page, "snapshot_dom_summary"):
            return list(page.snapshot_dom_summary())

        summary = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('main, h1, h2, form, table, button, a'))
              .slice(0, 20)
              .map((element) => {
                const text = (element.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
                return `${element.tagName.toLowerCase()}:${text}`;
              })
            """
        )
        return [item for item in summary if item]
