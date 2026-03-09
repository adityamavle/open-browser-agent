from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class ActionResult:
    ok: bool
    action: str
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ActionAPIError(RuntimeError):
    """Raised when the action layer is misconfigured."""


class ActionAPI:
    """Structured browser actions used by the executor."""

    def __init__(self, page_provider: Callable[[], Any]) -> None:
        self._page_provider = page_provider

    def _page(self) -> Any:
        page = self._page_provider()
        if page is None:
            raise ActionAPIError("ActionAPI page provider returned no page.")
        return page

    def goto(self, url: str) -> ActionResult:
        page = self._page()
        try:
            page.goto(url)
            return ActionResult(ok=True, action="goto", details={"url": url, "current_url": page.url})
        except Exception as exc:
            return ActionResult(ok=False, action="goto", error=str(exc), details={"url": url})

    def click(self, selector: str) -> ActionResult:
        page = self._page()
        try:
            page.click(selector)
            return ActionResult(ok=True, action="click", details={"selector": selector})
        except Exception as exc:
            return ActionResult(ok=False, action="click", error=str(exc), details={"selector": selector})

    def type(self, selector: str, text: str) -> ActionResult:
        page = self._page()
        try:
            page.fill(selector, text)
            return ActionResult(ok=True, action="type", details={"selector": selector, "text": text})
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="type",
                error=str(exc),
                details={"selector": selector, "text": text},
            )

    def press(self, keys: str) -> ActionResult:
        page = self._page()
        try:
            page.keyboard.press(keys)
            return ActionResult(ok=True, action="press", details={"keys": keys})
        except Exception as exc:
            return ActionResult(ok=False, action="press", error=str(exc), details={"keys": keys})

    def wait_for(self, selector: str) -> ActionResult:
        page = self._page()
        try:
            page.wait_for_selector(selector)
            return ActionResult(ok=True, action="wait_for", details={"selector": selector})
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="wait_for",
                error=str(exc),
                details={"selector": selector},
            )

    def extract(self, target: str) -> ActionResult:
        page = self._page()
        try:
            if target == "summary":
                value = page.locator("p").inner_text()
            elif target == "table":
                value = page.locator("table").inner_text()
            else:
                value = page.locator(target).inner_text()
            return ActionResult(ok=True, action="extract", details={"target": target, "value": value})
        except Exception as exc:
            return ActionResult(ok=False, action="extract", error=str(exc), details={"target": target})
