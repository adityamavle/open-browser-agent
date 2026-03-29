from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class ActionResult:
    ok: bool
    action: str
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_code: str | None = None


class ActionAPIError(RuntimeError):
    """Raised when the action layer is misconfigured."""


class ActionAPI:
    """Structured browser actions used by the executor."""

    def __init__(
        self,
        page_provider: Callable[[], Any],
        url_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self._page_provider = page_provider
        self._url_resolver = url_resolver or (lambda url: url)

    def _page(self) -> Any:
        page = self._page_provider()
        if page is None:
            raise ActionAPIError("ActionAPI page provider returned no page.")
        return page

    def _with_timeout(self, fn: Callable[..., Any], timeout_ms: int | None, *args: Any) -> Any:
        if timeout_ms is None:
            return fn(*args)
        try:
            return fn(*args, timeout=timeout_ms)
        except TypeError:
            return fn(*args)

    def _classify_error(self, exc: Exception) -> str:
        lowered = str(exc).lower()
        if "timeout" in lowered:
            return "timeout"
        if "strict mode violation" in lowered:
            return "strict_mode"
        if "no node found" in lowered or "not found" in lowered or "missing selector" in lowered:
            return "selector_not_found"
        if "navigation" in lowered or "net::" in lowered:
            return "navigation"
        return "unknown"

    def goto(self, url: str, timeout_ms: int | None = None) -> ActionResult:
        page = self._page()
        resolved_url = self._url_resolver(url)
        try:
            self._with_timeout(page.goto, timeout_ms, resolved_url)
            return ActionResult(
                ok=True,
                action="goto",
                details={
                    "url": url,
                    "resolved_url": resolved_url,
                    "current_url": page.url,
                    "timeout_ms": timeout_ms,
                },
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="goto",
                error=str(exc),
                error_code=self._classify_error(exc),
                details={"url": url, "resolved_url": resolved_url, "timeout_ms": timeout_ms},
            )

    def click(self, selector: str, timeout_ms: int | None = None) -> ActionResult:
        page = self._page()
        try:
            self._with_timeout(page.click, timeout_ms, selector)
            return ActionResult(
                ok=True,
                action="click",
                details={"selector": selector, "timeout_ms": timeout_ms},
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="click",
                error=str(exc),
                error_code=self._classify_error(exc),
                details={"selector": selector, "timeout_ms": timeout_ms},
            )

    def type(self, selector: str, text: str, timeout_ms: int | None = None) -> ActionResult:
        page = self._page()
        try:
            self._with_timeout(page.fill, timeout_ms, selector, text)
            return ActionResult(
                ok=True,
                action="type",
                details={"selector": selector, "text": text, "timeout_ms": timeout_ms},
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="type",
                error=str(exc),
                error_code=self._classify_error(exc),
                details={"selector": selector, "text": text, "timeout_ms": timeout_ms},
            )

    def press(self, keys: str, timeout_ms: int | None = None) -> ActionResult:
        page = self._page()
        try:
            page.keyboard.press(keys)
            return ActionResult(
                ok=True,
                action="press",
                details={"keys": keys, "timeout_ms": timeout_ms},
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="press",
                error=str(exc),
                error_code=self._classify_error(exc),
                details={"keys": keys, "timeout_ms": timeout_ms},
            )

    def wait_for(self, selector: str, timeout_ms: int | None = None) -> ActionResult:
        page = self._page()
        try:
            self._with_timeout(page.wait_for_selector, timeout_ms, selector)
            return ActionResult(
                ok=True,
                action="wait_for",
                details={"selector": selector, "timeout_ms": timeout_ms},
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="wait_for",
                error=str(exc),
                error_code=self._classify_error(exc),
                details={"selector": selector, "timeout_ms": timeout_ms},
            )

    def extract(self, target: str, timeout_ms: int | None = None) -> ActionResult:
        page = self._page()
        try:
            if target == "summary":
                if hasattr(page, "evaluate"):
                    value = page.evaluate(
                        """
                        () => {
                          const paragraphs = Array.from(document.querySelectorAll('main p, article p, p'));
                          const first = paragraphs.find((node) => (node.innerText || '').trim().length > 0);
                          return first ? first.innerText.trim() : '';
                        }
                        """
                    )
                else:
                    value = page.locator("p").inner_text()
            elif target == "table":
                value = page.locator("table").inner_text()
            else:
                value = page.locator(target).inner_text()
            return ActionResult(
                ok=True,
                action="extract",
                details={"target": target, "value": value, "timeout_ms": timeout_ms},
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="extract",
                error=str(exc),
                error_code=self._classify_error(exc),
                details={"target": target, "timeout_ms": timeout_ms},
            )
