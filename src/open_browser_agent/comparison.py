from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import request as urllib_request

from open_browser_agent.constants.agent_constants import (
    ANTHROPIC_DEFAULT_BASE_URL,
    ANTHROPIC_DEFAULT_MAX_TOKENS,
    ANTHROPIC_DEFAULT_MODEL,
    ANTHROPIC_DEFAULT_VERSION,
    COMPARISON_SYNTHESIS_SYSTEM_PROMPT,
    COMPARISON_SYNTHESIS_USER_PROMPT_LINES,
)


_CSV_REQUEST_PATTERNS = (
    r"\bcsv\b",
    r"\bspreadsheet\b",
    r"\bexport\b",
    r"\bsave (?:it )?(?:as|to)\b",
    r"\bwrite (?:it )?to (?:a )?csv\b",
    r"\boutput (?:it )?to (?:a )?csv\b",
)

_COMPARISON_LEAD_PATTERN = re.compile(
    r"^\s*(?:compare|create|build|make)\s+(?P<subject>.+?)(?:\s+by\s+(?P<columns>.+))?\s*$",
    flags=re.IGNORECASE,
)


@dataclass(slots=True)
class ComparisonIntent:
    subject: str
    requested_columns: list[str]
    output_mode: str


@dataclass(slots=True)
class ComparisonSynthesisResult:
    rows: list[dict[str, object]]
    provider: str
    model: str


class ComparisonSynthesisError(ValueError):
    """Raised when comparison row synthesis fails."""


class ComparisonTransport(Protocol):
    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        """Execute a JSON POST request and return the decoded JSON response."""


class UrllibComparisonTransport:
    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        req = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))


class AnthropicComparisonRowSynthesizer:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = ANTHROPIC_DEFAULT_BASE_URL,
        transport: ComparisonTransport | None = None,
        timeout_s: float = 30.0,
        anthropic_version: str = ANTHROPIC_DEFAULT_VERSION,
        max_tokens: int = ANTHROPIC_DEFAULT_MAX_TOKENS,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.transport = transport or UrllibComparisonTransport()
        self.timeout_s = timeout_s
        self.anthropic_version = anthropic_version
        self.max_tokens = max_tokens

    @classmethod
    def from_env(cls) -> "AnthropicComparisonRowSynthesizer":
        load_local_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("OBA_ANTHROPIC_API_KEY", "").strip()
        model = os.getenv("OBA_ANTHROPIC_MODEL", ANTHROPIC_DEFAULT_MODEL).strip()
        base_url = os.getenv("OBA_ANTHROPIC_BASE_URL", ANTHROPIC_DEFAULT_BASE_URL).strip()
        if not api_key:
            raise ComparisonSynthesisError(
                "ANTHROPIC_API_KEY or OBA_ANTHROPIC_API_KEY is required for comparison row synthesis."
            )
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            anthropic_version=os.getenv("OBA_ANTHROPIC_VERSION", ANTHROPIC_DEFAULT_VERSION).strip(),
            max_tokens=int(os.getenv("OBA_ANTHROPIC_MAX_TOKENS", str(ANTHROPIC_DEFAULT_MAX_TOKENS)).strip()),
        )

    def synthesize(
        self,
        subject: str,
        columns: list[str],
        raw_rows: list[dict[str, object]],
    ) -> ComparisonSynthesisResult:
        response = self.transport.post_json(
            url=self.base_url,
            headers=self._headers(),
            payload=self._payload(subject=subject, columns=columns, raw_rows=raw_rows),
            timeout_s=self.timeout_s,
        )
        content = self._extract_message_content(response)
        payload = self._parse_json_payload(content)
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ComparisonSynthesisError("Comparison synthesis response did not include a non-empty rows list.")
        normalized_rows: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ComparisonSynthesisError("Comparison synthesis rows must be objects.")
            normalized_rows.append(dict(row))
        return ComparisonSynthesisResult(rows=normalized_rows, provider=self.name, model=self.model)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }

    def _payload(self, subject: str, columns: list[str], raw_rows: list[dict[str, object]]) -> dict[str, Any]:
        lines = [
            f"Subject: {subject}",
            f"Columns: {json.dumps(columns, ensure_ascii=False)}",
            f"Raw rows: {json.dumps(raw_rows, ensure_ascii=False)}",
            *COMPARISON_SYNTHESIS_USER_PROMPT_LINES,
        ]
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "system": COMPARISON_SYNTHESIS_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": "\n".join(lines)}],
        }

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        content = response.get("content")
        if not isinstance(content, list) or not content:
            raise ComparisonSynthesisError("Comparison synthesis response did not include content blocks.")
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        if not text_parts:
            raise ComparisonSynthesisError("Comparison synthesis response did not include text content.")
        return "\n".join(part for part in text_parts if part)

    def _parse_json_payload(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or start >= end:
                parsed = self._parse_python_literal_dict(stripped)
                if parsed is not None:
                    return parsed
                raise ComparisonSynthesisError("Comparison synthesis response did not contain valid JSON.") from None
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                parsed = self._parse_python_literal_dict(stripped[start : end + 1])
                if parsed is not None:
                    return parsed
                raise ComparisonSynthesisError("Comparison synthesis response JSON could not be parsed.") from None

    def _parse_python_literal_dict(self, content: str) -> dict[str, Any] | None:
        try:
            parsed = ast.literal_eval(content)
        except (SyntaxError, ValueError):
            return None
        if isinstance(parsed, dict):
            return parsed
        return None


def infer_output_mode(goal: str) -> str:
    lowered = _normalize_goal_text(goal).lower()
    if not lowered:
        return "text"
    for pattern in _CSV_REQUEST_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return "csv"
    return "text"


def extract_requested_columns(goal: str, max_columns: int = 5) -> list[str]:
    if max_columns < 1:
        raise ValueError("max_columns must be at least 1")

    match = _COMPARISON_LEAD_PATTERN.match(_strip_output_clauses(goal))
    if match is None:
        return []

    raw_columns = match.group("columns")
    if not raw_columns:
        return []

    normalized = raw_columns.strip().rstrip(".")
    normalized = re.sub(r"\s+(?:in|as)\s+csv$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+and\s+", ", ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+plus\s+", ", ", normalized, flags=re.IGNORECASE)
    parts = [part.strip(" .") for part in normalized.split(",")]

    columns: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        compact = re.sub(r"\s+", " ", part)
        lowered = compact.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        columns.append(compact)
        if len(columns) >= max_columns:
            break
    return columns


def parse_comparison_intent(goal: str, max_columns: int = 5) -> ComparisonIntent | None:
    cleaned_goal = _strip_output_clauses(goal)
    match = _COMPARISON_LEAD_PATTERN.match(cleaned_goal)
    if match is None:
        return None

    subject = re.sub(r"\s+", " ", match.group("subject").strip(" ."))
    if not subject:
        return None

    return ComparisonIntent(
        subject=subject,
        requested_columns=extract_requested_columns(goal, max_columns=max_columns),
        output_mode=infer_output_mode(goal),
    )


def load_local_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        cleaned_key = key.strip()
        cleaned_value = value.strip().strip("'").strip('"')
        if cleaned_key and cleaned_key not in os.environ:
            os.environ[cleaned_key] = cleaned_value


def _strip_output_clauses(goal: str) -> str:
    cleaned = _normalize_goal_text(goal)
    patterns = (
        r"\s+and (?:save|export|write|output).*$",
        r"\s+(?:save|export|write|output) .*$",
        r"\s+in csv\s*$",
        r"\s+as csv\s*$",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _normalize_goal_text(goal: str) -> str:
    return re.sub(r"\s+", " ", goal).strip()
