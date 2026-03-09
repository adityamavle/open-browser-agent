from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from open_browser_agent.schemas.observation import Observation


@dataclass(slots=True)
class VerificationResult:
    success: bool
    reason: str


@dataclass(slots=True)
class VerificationRule:
    kind: str
    value: Any
    label: str = ""


class Verifier:
    """Task-specific success checks."""

    def __init__(self, rules: list[VerificationRule] | None = None) -> None:
        self.rules = rules or []

    def verify(self, observation: Observation) -> VerificationResult:
        for rule in self.rules:
            passed, reason = self._evaluate(rule, observation)
            if not passed:
                return VerificationResult(success=False, reason=reason)
        return VerificationResult(success=True, reason="All verification rules passed.")

    def _evaluate(self, rule: VerificationRule, observation: Observation) -> tuple[bool, str]:
        label = rule.label or rule.kind
        if rule.kind == "url_contains":
            passed = str(rule.value) in observation.url
            return passed, f"Verification failed for {label}."
        if rule.kind == "text_contains":
            passed = str(rule.value) in observation.visible_text
            return passed, f"Verification failed for {label}."
        if rule.kind == "dom_contains":
            passed = any(str(rule.value) in node for node in observation.dom_summary)
            return passed, f"Verification failed for {label}."
        raise ValueError(f"Unsupported verification rule: {rule.kind}")
