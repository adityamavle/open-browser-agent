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
        max_form_controls: int = 20,
    ) -> None:
        self._page_provider = page_provider
        self.max_text_chars = max_text_chars
        self.max_dom_nodes = max_dom_nodes
        self.max_form_controls = max_form_controls

    def capture(self, screenshot_path: str | None = None) -> Observation:
        page = self._page_provider()
        visible_text = page.locator("body").inner_text().strip()
        visible_text = visible_text[: self.max_text_chars]
        dom_summary = self._capture_dom_summary(page)
        form_state = self._capture_form_state(page)

        if screenshot_path:
            page.screenshot(path=screenshot_path)

        return Observation(
            url=page.url,
            title=page.title(),
            visible_text=visible_text,
            dom_summary=dom_summary[: self.max_dom_nodes],
            form_state=form_state[: self.max_form_controls],
            screenshot_path=screenshot_path,
        )

    def _capture_dom_summary(self, page: Any) -> list[str]:
        if hasattr(page, "snapshot_dom_summary"):
            return list(page.snapshot_dom_summary())
        if not hasattr(page, "evaluate"):
            return []

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

    def _capture_form_state(self, page: Any) -> list[str]:
        if hasattr(page, "snapshot_form_state"):
            return list(page.snapshot_form_state())
        if not hasattr(page, "evaluate"):
            return []

        state = page.evaluate(
            """
            () => {
              const chromeSelectors = 'nav, header, aside, footer, [role="navigation"], .sidebar, .td-sidebar';
              const contentSelectors = 'main, [role="main"], article';
              const normalize = (value) => {
                const text = String(value ?? '').trim().replace(/\\s+/g, ' ');
                return text ? text.slice(0, 80) : '<empty>';
              };

              const isVisible = (element) => {
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return (
                  style.display !== 'none' &&
                  style.visibility !== 'hidden' &&
                  rect.width > 0 &&
                  rect.height > 0
                );
              };

              const controls = Array.from(document.querySelectorAll('input, textarea, select'))
                .filter((element) => {
                  if (!isVisible(element)) {
                    return false;
                  }
                  if (element.closest(chromeSelectors)) {
                    return false;
                  }
                  if (element.disabled || element.readOnly) {
                    return false;
                  }
                  return true;
                });

              const contentControls = controls.filter((element) => element.closest(contentSelectors));
              const formControls = controls.filter((element) => element.closest('form, fieldset'));
              const relevantControls =
                contentControls.length > 0 ? contentControls : formControls.length > 0 ? formControls : controls;

              return relevantControls
                .map((element) => {
                  const tag = element.tagName.toLowerCase();
                  const name =
                    element.getAttribute('name') ||
                    element.id ||
                    element.getAttribute('aria-label') ||
                    '<anonymous>';

                  if (tag === 'textarea') {
                    return `textarea:${name}=${normalize(element.value)}`;
                  }

                  if (tag === 'select') {
                    const selected = Array.from(element.selectedOptions || [])
                      .map((option) => option.textContent || option.value || '')
                      .join('|');
                    return `select:${name}=${normalize(selected)}`;
                  }

                  const type = (element.getAttribute('type') || 'text').toLowerCase();
                  if (['hidden', 'password', 'file', 'submit', 'button', 'reset', 'image'].includes(type)) {
                    return null;
                  }
                  if (type === 'checkbox' || type === 'radio') {
                    if (!element.checked) {
                      return null;
                    }
                    return `input:${type}:${name}=${normalize(element.value || 'checked')}`;
                  }

                  return `input:${type}:${name}=${normalize(element.value)}`;
                })
                .filter(Boolean);
            }
            """
        )
        return [item for item in state if item]
