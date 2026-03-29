from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from open_browser_agent.schemas.observation import Observation


@dataclass(slots=True)
class VerificationResult:
    success: bool
    reason: str
    checks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class VerificationCheck:
    kind: str
    label: str
    value: str
    passed: bool
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerificationRule:
    kind: str
    value: Any
    label: str = ""


@dataclass(slots=True)
class VerificationInput:
    observation: Observation
    artifacts: dict[str, Any] = field(default_factory=dict)


class Verifier:
    """Task-specific success checks."""

    def __init__(self, rules: list[VerificationRule] | None = None) -> None:
        self.rules = rules or []

    def verify(self, verification_input: Observation | VerificationInput) -> VerificationResult:
        context = self._coerce_input(verification_input)
        checks: list[dict[str, Any]] = []
        for rule in self.rules:
            passed, reason, evidence = self._evaluate(rule, context)
            checks.append(
                VerificationCheck(
                    kind=rule.kind,
                    label=rule.label or rule.kind,
                    value=str(rule.value),
                    passed=passed,
                    evidence=evidence,
                ).to_dict()
            )
            if not passed:
                return VerificationResult(success=False, reason=reason, checks=checks)
        return VerificationResult(success=True, reason="All verification rules passed.", checks=checks)

    def _coerce_input(self, verification_input: Observation | VerificationInput) -> VerificationInput:
        if isinstance(verification_input, VerificationInput):
            return verification_input
        return VerificationInput(observation=verification_input)

    def _evaluate(self, rule: VerificationRule, verification_input: VerificationInput) -> tuple[bool, str, str]:
        label = rule.label or rule.kind
        observation = verification_input.observation
        if rule.kind == "url_contains":
            passed = str(rule.value) in observation.url
            return passed, f"Verification failed for {label}.", observation.url
        if rule.kind == "text_contains":
            passed = str(rule.value) in observation.visible_text
            evidence = str(rule.value) if passed else observation.visible_text[:200]
            return passed, f"Verification failed for {label}.", evidence
        if rule.kind == "dom_contains":
            matched_node = next((node for node in observation.dom_summary if str(rule.value) in node), "")
            passed = bool(matched_node)
            evidence = matched_node if passed else " | ".join(observation.dom_summary[:5])
            return passed, f"Verification failed for {label}.", evidence
        if rule.kind == "artifact_exists":
            path = str(rule.value)
            resolved = self._resolve_artifact(verification_input.artifacts, path)
            passed = resolved is not None
            evidence = path if passed else f"missing:{path}"
            return passed, f"Verification failed for {label}.", evidence
        if rule.kind == "artifact_text_contains":
            if not isinstance(rule.value, dict):
                raise ValueError("artifact_text_contains requires {'path': ..., 'contains': ...}.")
            path = str(rule.value.get("path", ""))
            expected = str(rule.value.get("contains", ""))
            resolved = self._resolve_artifact(verification_input.artifacts, path)
            passed = isinstance(resolved, str) and expected in resolved
            evidence = expected if passed else str(resolved)[:200]
            return passed, f"Verification failed for {label}.", evidence
        if rule.kind == "artifact_list_min_length":
            if not isinstance(rule.value, dict):
                raise ValueError("artifact_list_min_length requires {'path': ..., 'min': ...}.")
            path = str(rule.value.get("path", ""))
            minimum = int(rule.value.get("min", 0))
            resolved = self._resolve_artifact(verification_input.artifacts, path)
            length = len(resolved) if isinstance(resolved, list) else 0
            passed = isinstance(resolved, list) and length >= minimum
            evidence = f"len={length}"
            return passed, f"Verification failed for {label}.", evidence
        raise ValueError(f"Unsupported verification rule: {rule.kind}")

    def _resolve_artifact(self, artifacts: dict[str, Any], path: str) -> Any:
        current: Any = artifacts
        for segment in path.split("."):
            if not segment:
                return None
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
        return current
