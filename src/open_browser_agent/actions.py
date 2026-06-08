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

    def _evaluate_or_default(self, page: Any, script: str, default: Any, arg: Any = None) -> Any:
        if not hasattr(page, "evaluate"):
            return default() if callable(default) else default
        if arg is None:
            return page.evaluate(script)
        return page.evaluate(script, arg)

    def goto(self, url: str, timeout_ms: int | None = None) -> ActionResult:
        page = self._page()
        resolved_url = self._url_resolver(url)
        try:
            try:
                if timeout_ms is None:
                    page.goto(resolved_url, wait_until="domcontentloaded")
                else:
                    page.goto(resolved_url, timeout=timeout_ms, wait_until="domcontentloaded")
            except TypeError:
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
                value = self._evaluate_or_default(
                    page,
                    """
                    () => {
                      const paragraphs = Array.from(document.querySelectorAll('main p, article p, p'));
                      const first = paragraphs.find((node) => (node.innerText || '').trim().length > 0);
                      return first ? first.innerText.trim() : '';
                    }
                    """,
                    lambda: page.locator("p").inner_text(),
                )
            elif target == "citation_links":
                value = self._evaluate_or_default(
                    page,
                    """
                    () => {
                      const links = Array.from(
                        document.querySelectorAll(
                          'main .reference a[href], main ol.references a[href], article .reference a[href], article ol.references a[href]'
                        )
                      );
                      const normalized = links
                        .map((node) => {
                          const href = (node.getAttribute('href') || '').trim();
                          const text = (node.innerText || node.textContent || '').trim().replace(/\\s+/g, ' ');
                          if (!href) {
                            return null;
                          }
                          return {
                            text,
                            href: href.startsWith('//') ? `https:${href}` : href,
                          };
                        })
                        .filter((item) => item && item.href)
                        .slice(0, 8);
                      return normalized;
                    }
                    """,
                    [],
                )
            elif target == "section_headings":
                value = self._evaluate_or_default(
                    page,
                    """
                    () => {
                      const root =
                        document.querySelector('#mw-content-text .mw-parser-output') ||
                        document.querySelector('main article') ||
                        document.querySelector('main');
                      const normalizeHeading = (node) =>
                        (node.innerText || node.textContent || '')
                          .replace(/\\[edit\\]/gi, '')
                          .replace(/\\s+/g, ' ')
                          .trim();
                      const headings = root ? Array.from(root.querySelectorAll('h2, h3')) : [];
                      return headings
                        .filter((node) => !node.closest('nav, aside, .vector-toc, [role="navigation"]'))
                        .map((node) => normalizeHeading(node))
                        .filter(Boolean)
                        .slice(0, 40);
                    }
                    """,
                    [],
                )
            elif target.startswith("section:"):
                section_name = target.split(":", 1)[1].strip()
                value = self._evaluate_or_default(
                    page,
                    """
                    (sectionName) => {
                      const root =
                        document.querySelector('#mw-content-text .mw-parser-output') ||
                        document.querySelector('main article') ||
                        document.querySelector('main');
                      const cleanText = (value) =>
                        String(value || '')
                          .replace(/\[edit\]/gi, '')
                          .replace(/\s+/g, ' ')
                          .trim();
                      const normalize = (value) =>
                        cleanText(value).toLowerCase();
                      const headingNodes = root ? Array.from(root.querySelectorAll('h2, h3')) : [];
                      const headingEntries = headingNodes
                        .map((node) => {
                          const headline =
                            node.querySelector('.mw-headline') ||
                            node.querySelector('[id]') ||
                            node;
                          const label = cleanText(headline.innerText || headline.textContent || '');
                          return { node, label };
                        })
                        .filter((entry) => entry.label);
                      const matchEntry = headingEntries.find((entry) => {
                        const text = normalize(entry.label);
                        const target = normalize(sectionName);
                        return text === target || text.includes(target) || target.includes(text);
                      });
                      if (!matchEntry) {
                        return '';
                      }
                      const match = matchEntry.node;
                      const level = match.tagName.toLowerCase();
                      const blocks = [];
                      let current = match.nextElementSibling;
                      const isReferenceContainer = (node) => {
                        if (!node || !node.matches) {
                          return false;
                        }
                        if (
                          node.matches(
                            '.reflist, .mw-references-wrap, .references, ol.references, .reference, .navbox, .vertical-navbox, .metadata, .catlinks'
                          )
                        ) {
                          return true;
                        }
                        return Boolean(
                          node.querySelector &&
                          node.querySelector('.reflist, .mw-references-wrap, .references, ol.references, .reference')
                        );
                      };
                      while (current) {
                        const tag = current.tagName.toLowerCase();
                        if (tag === 'h2' || (level === 'h3' && tag === 'h3')) {
                          break;
                        }
                        if (isReferenceContainer(current)) {
                          break;
                        }
                        if (
                          current.matches &&
                          current.matches('.mw-editsection')
                        ) {
                          current = current.nextElementSibling;
                          continue;
                        }
                        const allowedTags = new Set(['p', 'ul', 'ol', 'dl', 'div']);
                        if (!allowedTags.has(tag)) {
                          current = current.nextElementSibling;
                          continue;
                        }
                        const text = cleanText(current.innerText || current.textContent || '');
                        if (text) {
                          blocks.push(text);
                        }
                        current = current.nextElementSibling;
                      }
                      const direct = blocks.join('\\n\\n').trim();
                      if (direct) {
                        return direct;
                      }

                      const headingLabels = headingEntries.map((entry) => entry.label);
                      const matchLabel = matchEntry.label;
                      const matchIndex = headingLabels.findIndex((label) => normalize(label) === normalize(matchLabel));
                      const bodyText = cleanText((root.innerText || root.textContent || '').replace(/\\r/g, ''));
                      const startIndex = bodyText.lastIndexOf(matchLabel);
                      if (startIndex === -1) {
                        return '';
                      }
                      let endIndex = bodyText.length;
                      for (const nextLabel of headingLabels.slice(matchIndex + 1)) {
                        const foundIndex = bodyText.indexOf(nextLabel, startIndex + matchLabel.length);
                        if (foundIndex !== -1) {
                          endIndex = foundIndex;
                          break;
                        }
                      }
                      return bodyText.slice(startIndex + matchLabel.length, endIndex).trim();
                    }
                    """,
                    "",
                    arg=section_name,
                )
            elif target == "bestbuy_search_results":
                value = self._evaluate_or_default(
                    page,
                    """
                    () => {
                      const clean = (value) =>
                        String(value || '')
                          .replace(/\\s+/g, ' ')
                          .trim();
                      const priceText = (node) => {
                        const candidates = [
                          '.priceView-customer-price span[aria-hidden="true"]',
                          '[data-testid="customer-price"]',
                          '[data-testid="product-price"]',
                          '.price-current',
                          '.sr-only',
                        ];
                        for (const selector of candidates) {
                          const match = node.querySelector(selector);
                          const text = clean(match && (match.innerText || match.textContent || ''));
                          if (text) {
                            return text;
                          }
                        }
                        return '';
                      };
                      const titleText = (node) => {
                        const selectors = [
                          'h4',
                          '.sku-title a',
                          '[data-testid="product-title"]',
                          'a[data-testid="product-title-link"]',
                        ];
                        for (const selector of selectors) {
                          const match = node.querySelector(selector);
                          const text = clean(match && (match.innerText || match.textContent || ''));
                          if (text) {
                            return text;
                          }
                        }
                        return '';
                      };
                      const hrefFor = (node) => {
                        const link = node.matches && node.matches('a[href]') ? node : node.querySelector('a[href]');
                        if (!link) {
                          return '';
                        }
                        const href = clean(link.getAttribute('href') || '');
                        if (!href) {
                          return '';
                        }
                        if (href.startsWith('http')) {
                          return href;
                        }
                        const base =
                          window.location.protocol === 'http:' || window.location.protocol === 'https:'
                            ? window.location.origin
                            : window.location.href;
                        return new URL(href, base).href;
                      };
                      const cards = Array.from(
                        document.querySelectorAll('[data-testid="sku-card"], .sku-item, li.sku-item')
                      );
                      const productAnchors = Array.from(
                        document.querySelectorAll('a.sku-title[href], a.product-list-item-link[href]')
                      );
                      const candidates = cards.length ? cards : productAnchors;
                      const seen = new Set();
                      return candidates
                        .map((node) => {
                          const anchorNode = node.matches && node.matches('a[href]') ? node : null;
                          const container =
                            anchorNode && anchorNode.closest('[class*="product"], [class*="sku"], li, article')
                              ? anchorNode.closest('[class*="product"], [class*="sku"], li, article')
                              : node;
                          return {
                            title: anchorNode ? clean(anchorNode.innerText || anchorNode.textContent || '') : titleText(node),
                            href: hrefFor(node),
                            price: priceText(container || node),
                          };
                        })
                        .filter((item) => {
                          if (!item.title || !item.href || seen.has(item.href)) {
                            return false;
                          }
                          seen.add(item.href);
                          return true;
                        })
                        .slice(0, 8);
                    }
                    """,
                    [],
                )
            elif target == "bestbuy_product_facts":
                value = self._evaluate_or_default(
                    page,
                    """
                    () => {
                      const clean = (value) =>
                        String(value || '')
                          .replace(/\\s+/g, ' ')
                          .trim();
                      const lower = (value) => clean(value).toLowerCase();
                      const textFor = (selectors) => {
                        for (const selector of selectors) {
                          const node = document.querySelector(selector);
                          const text = clean(node && (node.innerText || node.textContent || ''));
                          if (text) {
                            return text;
                          }
                        }
                        return '';
                      };
                      const title = textFor([
                        '[data-testid="product-title"]',
                        'h1.heading-5',
                        'h1',
                      ]);
                      const price = textFor([
                        '.priceView-customer-price span[aria-hidden="true"]',
                        '[data-testid="customer-price"]',
                        '[data-testid="product-price"]',
                        '.price-current',
                      ]);
                      const skuText = textFor([
                        '[data-testid="product-sku"]',
                        '.product-data-value',
                        '.sku.product-data',
                      ]);
                      const specRows = Array.from(
                        document.querySelectorAll(
                          '[data-testid="specifications"] tr, .shop-specifications tr, .key-specs tr, .product-data-row'
                        )
                      );
                      const specs = {};
                      for (const row of specRows) {
                        const cells = Array.from(row.querySelectorAll('th, td, .product-data-title, .product-data-value'));
                        if (cells.length < 2) {
                          continue;
                        }
                        const label = clean(cells[0].innerText || cells[0].textContent || '');
                        const rawValue = clean(cells[cells.length - 1].innerText || cells[cells.length - 1].textContent || '');
                        if (!label || !rawValue) {
                          continue;
                        }
                        specs[label] = rawValue;
                      }
                      const normalizeSpec = (...needles) => {
                        for (const [label, rawValue] of Object.entries(specs)) {
                          const normalized = lower(label);
                          if (needles.some((needle) => normalized.includes(needle))) {
                            return rawValue;
                          }
                        }
                        return '';
                      };
                      return {
                        entity_name: title,
                        product_name: title,
                        product_url: window.location.href,
                        sku: skuText.replace(/^sku:\\s*/i, ''),
                        price,
                        specifications: specs,
                        facts: {
                          'model name': title,
                          'display size': normalizeSpec('screen size', 'display size'),
                          'ram': normalizeSpec('system memory', 'ram', 'memory'),
                          'storage':
                            normalizeSpec('solid state drive capacity', 'ssd capacity', 'storage capacity') ||
                            normalizeSpec('storage'),
                        },
                      };
                    }
                    """,
                    {},
                )
            elif target == "bestbuy_price":
                value = self._evaluate_or_default(
                    page,
                    """
                    () => {
                      const selectors = [
                        '.priceView-customer-price span[aria-hidden="true"]',
                        '[data-testid="customer-price"]',
                        '[data-testid="product-price"]',
                        '.price-current',
                      ];
                      for (const selector of selectors) {
                        const node = document.querySelector(selector);
                        const text = String((node && (node.innerText || node.textContent || '')) || '')
                          .replace(/\\s+/g, ' ')
                          .trim();
                        if (text) {
                          return text;
                        }
                      }
                      return '';
                    }
                    """,
                    "",
                )
            elif target == "table":
                value = page.locator("table").inner_text()
            else:
                value = page.locator(target).inner_text()
            return ActionResult(
                ok=True,
                action="extract",
                details={
                    "target": target,
                    "value": value,
                    "timeout_ms": timeout_ms,
                    "current_url": getattr(page, "url", ""),
                    "page_title": page.title() if hasattr(page, "title") else "",
                },
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action="extract",
                error=str(exc),
                error_code=self._classify_error(exc),
                details={"target": target, "timeout_ms": timeout_ms},
            )
