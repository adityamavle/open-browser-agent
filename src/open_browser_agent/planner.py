from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib import request as urllib_request

from open_browser_agent.constants.agent_constants import (
    ALLOWED_STEP_ARGS,
    ANTHROPIC_DEFAULT_BASE_URL,
    ANTHROPIC_DEFAULT_MAX_TOKENS,
    ANTHROPIC_DEFAULT_MODEL,
    ANTHROPIC_DEFAULT_VERSION,
    ANTHROPIC_PLANNER_SYSTEM_PROMPT,
    ANTHROPIC_PLANNER_USER_PROMPT_LINES,
    BESTBUY_COMPARISON_PLANNER_HINTS,
    REQUIRED_STEP_ARGS,
    SUPPORTED_VERIFICATION_KINDS,
    WIKIPEDIA_COMPARISON_PLANNER_HINTS,
    WIKIPEDIA_PLANNER_HINTS,
)
from open_browser_agent.comparison import parse_comparison_intent
from open_browser_agent.schemas.step import Step
from open_browser_agent.tasks.registry import find_task_by_goal
from open_browser_agent.verifier import VerificationRule


def _is_bestbuy_goal(goal: str, task_id: str | None) -> bool:
    lowered = goal.strip().lower()
    return task_id == "bestbuy-laptop-comparison" or "best buy" in lowered or "bestbuy" in lowered


@dataclass(slots=True)
class PlanRequest:
    goal: str
    site: str | None = None
    observation_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderPlan:
    steps: list[Step | dict[str, Any]]
    task_id: str | None = None
    verifier_hint: str = ""
    verification_rules: list[VerificationRule] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlanResult:
    steps: list[Step]
    provider_name: str
    task_id: str | None = None
    verifier_hint: str = ""
    verification_rules: list[VerificationRule] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "task": self.task_id,
            "verifier_hint": self.verifier_hint,
            "metadata": self.metadata,
            "steps": [
                {
                    "id": step.id,
                    "type": step.type,
                    "args": step.args,
                    "expected": step.expected,
                    "timeout_ms": step.timeout_ms,
                }
                for step in self.steps
            ],
        }


class PlannerError(ValueError):
    """Raised when a planner provider cannot produce a valid step plan."""


class PlannerProvider(Protocol):
    name: str

    def plan(self, request: PlanRequest) -> ProviderPlan:
        """Return step-schema-shaped plan data for the planner to validate."""


class PlannerTransport(Protocol):
    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        """Execute a JSON POST request and return the decoded JSON response."""


class UrllibPlannerTransport:
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


class TaskRegistryPlannerProvider:
    """Default provider that resolves goals to bundled task plans."""

    name = "task-registry"

    def plan(self, request: PlanRequest) -> ProviderPlan:
        task = find_task_by_goal(request.goal)
        if task is None:
            raise PlannerError("No matching task found. Planner/executor implementation pending.")
        return ProviderPlan(
            steps=list(task.steps),
            task_id=task.task_id,
            verifier_hint=task.verifier_hint,
            verification_rules=list(task.verification_rules),
            metadata={"site": request.site, "mode": "task_lookup"},
        )


class AnthropicPlannerProvider:
    """LLM planner provider for Anthropic's Messages API."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = ANTHROPIC_DEFAULT_BASE_URL,
        transport: PlannerTransport | None = None,
        timeout_s: float = 30.0,
        anthropic_version: str = ANTHROPIC_DEFAULT_VERSION,
        max_tokens: int = ANTHROPIC_DEFAULT_MAX_TOKENS,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.transport = transport or UrllibPlannerTransport()
        self.timeout_s = timeout_s
        self.anthropic_version = anthropic_version
        self.max_tokens = max_tokens

    @classmethod
    def from_env(cls) -> "AnthropicPlannerProvider":
        load_local_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("OBA_ANTHROPIC_API_KEY", "").strip()
        model = os.getenv("OBA_ANTHROPIC_MODEL", ANTHROPIC_DEFAULT_MODEL).strip()
        base_url = os.getenv("OBA_ANTHROPIC_BASE_URL", ANTHROPIC_DEFAULT_BASE_URL).strip()
        if not api_key:
            raise PlannerError("ANTHROPIC_API_KEY or OBA_ANTHROPIC_API_KEY is required for the anthropic planner.")
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            anthropic_version=os.getenv("OBA_ANTHROPIC_VERSION", ANTHROPIC_DEFAULT_VERSION).strip(),
            max_tokens=int(os.getenv("OBA_ANTHROPIC_MAX_TOKENS", str(ANTHROPIC_DEFAULT_MAX_TOKENS)).strip()),
        )

    def plan(self, request: PlanRequest) -> ProviderPlan:
        response = self.transport.post_json(
            url=self.base_url,
            headers=self._headers(),
            payload=self._payload(request),
            timeout_s=self.timeout_s,
        )
        content = self._extract_message_content(response)
        raw_plan = self._parse_plan_json(content, response=response)
        steps = raw_plan.get("steps")
        if not isinstance(steps, list) or not steps:
            raise PlannerError("LLM planner response did not include a non-empty 'steps' list.")
        verification_rules = self._coerce_verification_rules(raw_plan.get("verification_rules"))
        metadata = {
            "site": request.site,
            "mode": "llm",
            "model": self.model,
            "response_id": response.get("id"),
        }
        if isinstance(raw_plan.get("metadata"), dict):
            metadata.update(raw_plan["metadata"])
        return ProviderPlan(
            steps=steps,
            task_id=raw_plan.get("task_id"),
            verifier_hint=str(raw_plan.get("verifier_hint") or ""),
            verification_rules=verification_rules,
            metadata=metadata,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }

    def _payload(self, request: PlanRequest) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "system": ANTHROPIC_PLANNER_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": self._build_user_prompt(request),
                },
            ],
        }

    def _build_user_prompt(self, request: PlanRequest) -> str:
        lines = [
            f"Goal: {request.goal}",
            f"Site constraint: {request.site or 'none'}",
            *ANTHROPIC_PLANNER_USER_PROMPT_LINES,
        ]
        task = find_task_by_goal(request.goal)
        comparison_intent = parse_comparison_intent(request.goal)
        if task is not None:
            lines.extend(
                [
                    f"Bundled task match: {task.task_id}",
                    f"Bundled task summary: {task.summary}",
                    "Use the same task intent as the bundled task. Do not change the topic or destination.",
                    f"Canonical verifier hint: {task.verifier_hint}",
                    f"Canonical step outline: {self._task_outline(task.steps)}",
                ]
            )
            lines.extend(self._task_specific_hints(task.task_id))
        if comparison_intent is not None:
            comparison_hints = (
                BESTBUY_COMPARISON_PLANNER_HINTS
                if _is_bestbuy_goal(request.goal, getattr(task, "task_id", None))
                else WIKIPEDIA_COMPARISON_PLANNER_HINTS
            )
            lines.extend(
                [
                    "Comparison intent detected.",
                    f"Comparison subject: {comparison_intent.subject}",
                    f"Requested output mode: {comparison_intent.output_mode}",
                    f"Requested columns (bounded): {json.dumps(comparison_intent.requested_columns, ensure_ascii=True)}",
                    *comparison_hints,
                ]
            )
        if request.observation_summary:
            lines.append(f"Observation summary: {json.dumps(request.observation_summary, ensure_ascii=True)}")
        return "\n".join(lines)

    def _task_specific_hints(self, task_id: str | None) -> tuple[str, ...]:
        if task_id in {"wikipedia-summary", "wikipedia-search-press", "wikipedia-section", "wikipedia-section-headings"}:
            return WIKIPEDIA_PLANNER_HINTS
        return ()

    def _task_outline(self, steps: list[Step]) -> str:
        outline_parts: list[str] = []
        for step in steps:
            if step.type in {"navigate", "goto"}:
                outline_parts.append(f"{step.type}(url={step.args.get('url')})")
            elif step.type == "extract":
                outline_parts.append(f"extract(target={step.args.get('target')})")
            elif "selector" in step.args:
                outline_parts.append(f"{step.type}(selector={step.args.get('selector')})")
            elif "keys" in step.args:
                outline_parts.append(f"{step.type}(keys={step.args.get('keys')})")
            else:
                outline_parts.append(step.type)
        return " -> ".join(outline_parts)

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        content = response.get("content")
        if not isinstance(content, list) or not content:
            raise PlannerError("Anthropic planner response did not include content blocks.")
        text_parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        if not text_parts:
            raise PlannerError("Anthropic planner response did not include text content.")
        return "\n".join(part for part in text_parts if part)

    def _parse_plan_json(self, content: str, response: dict[str, Any] | None = None) -> dict[str, Any]:
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
                self._raise_parse_error(response, "LLM planner response did not contain valid JSON.")
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError as exc:
                parsed = self._parse_python_literal_dict(stripped[start : end + 1])
                if parsed is not None:
                    return parsed
                self._raise_parse_error(response, "LLM planner response JSON could not be parsed.")

    def _parse_python_literal_dict(self, content: str) -> dict[str, Any] | None:
        try:
            parsed = ast.literal_eval(content)
        except (SyntaxError, ValueError):
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    def _raise_parse_error(self, response: dict[str, Any] | None, default_message: str) -> None:
        if isinstance(response, dict):
            stop_reason = str(response.get("stop_reason") or "").strip().lower()
            if stop_reason == "max_tokens":
                raise PlannerError(
                    "LLM planner response was truncated at max_tokens. Increase OBA_ANTHROPIC_MAX_TOKENS or shorten the comparison plan."
                ) from None
        raise PlannerError(default_message) from None

    def _coerce_verification_rules(self, raw_rules: Any) -> list[VerificationRule]:
        if raw_rules is None:
            return []
        if not isinstance(raw_rules, list):
            raise PlannerError("LLM planner verification_rules must be a list.")
        rules: list[VerificationRule] = []
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                raise PlannerError("LLM planner verification rule must be an object.")
            if "kind" not in raw_rule or "value" not in raw_rule:
                raise PlannerError("LLM planner verification rule requires 'kind' and 'value'.")
            kind = str(raw_rule["kind"])
            if kind not in SUPPORTED_VERIFICATION_KINDS:
                raise PlannerError(f"LLM planner emitted unsupported verification kind: {kind}")
            rules.append(
                VerificationRule(
                    kind=kind,
                    value=raw_rule["value"],
                    label=str(raw_rule.get("label") or ""),
                )
            )
        return rules


def build_planner(provider_name: str = "task-registry") -> "Planner":
    if provider_name == "task-registry":
        return Planner(TaskRegistryPlannerProvider())
    if provider_name == "anthropic":
        return Planner(AnthropicPlannerProvider.from_env())
    raise PlannerError(f"Unsupported planner provider: {provider_name}")


class Planner:
    """Provider-based planner that validates output into the shared step schema."""

    def __init__(self, provider: PlannerProvider | None = None) -> None:
        self.provider = provider or TaskRegistryPlannerProvider()

    def plan(
        self,
        goal: str,
        site: str | None = None,
        observation_summary: dict[str, Any] | None = None,
    ) -> PlanResult:
        request = PlanRequest(goal=goal, site=site, observation_summary=observation_summary or {})
        provider_plan = self.provider.plan(request)
        steps = [self._coerce_step(step) for step in provider_plan.steps]
        steps = self._normalize_goal_specific_steps(goal=goal, steps=steps)
        metadata = dict(provider_plan.metadata)
        self._validate_goal_specific_constraints(
            goal=goal,
            steps=steps,
            metadata=metadata,
            task_id=provider_plan.task_id,
        )
        return PlanResult(
            steps=steps,
            provider_name=self.provider.name,
            task_id=provider_plan.task_id,
            verifier_hint=provider_plan.verifier_hint,
            verification_rules=list(provider_plan.verification_rules),
            metadata=metadata,
        )

    def _coerce_step(self, step: Step | dict[str, Any]) -> Step:
        if isinstance(step, Step):
            return step
        if not isinstance(step, dict):
            raise PlannerError(f"Planner step must be a Step or dict, got: {type(step).__name__}")

        required_keys = {"id", "type"}
        missing = required_keys - set(step)
        if missing:
            raise PlannerError(f"Planner step missing required keys: {sorted(missing)}")

        timeout_ms = step.get("timeout_ms", 10_000)
        try:
            timeout_value = int(timeout_ms)
        except (TypeError, ValueError) as exc:
            raise PlannerError(f"Planner step timeout_ms must be an integer, got: {timeout_ms!r}") from exc

        raw_args = step.get("args", {})
        if not isinstance(raw_args, dict):
            raise PlannerError(f"Planner step args must be an object, got: {type(raw_args).__name__}")

        step_type = str(step["type"])
        self._validate_step_args(step_type, raw_args)

        raw_expected = step.get("expected", {})
        if isinstance(raw_expected, dict):
            expected = dict(raw_expected)
        elif raw_expected in (None, ""):
            expected = {}
        else:
            expected = {"description": str(raw_expected)}

        return Step(
            id=str(step["id"]),
            type=step_type,
            args=dict(raw_args),
            expected=expected,
            timeout_ms=timeout_value,
        )

    def _validate_step_args(self, step_type: str, args: dict[str, Any]) -> None:
        if step_type not in ALLOWED_STEP_ARGS:
            return
        actual_keys = set(args)
        missing = REQUIRED_STEP_ARGS[step_type] - actual_keys
        extra = actual_keys - ALLOWED_STEP_ARGS[step_type]
        if missing:
            raise PlannerError(f"Planner step '{step_type}' missing required args: {sorted(missing)}")
        if extra:
            raise PlannerError(f"Planner step '{step_type}' has unsupported args: {sorted(extra)}")
        if step_type == "extract":
            target = args.get("target")
            if not isinstance(target, str) or not target.strip():
                raise PlannerError("Planner step 'extract' requires a non-empty string target.")
            if len(target) > 120:
                raise PlannerError("Planner step 'extract' target is too long and looks like a natural-language instruction.")

    def _validate_goal_specific_constraints(
        self,
        goal: str,
        steps: list[Step],
        metadata: dict[str, Any],
        task_id: str | None,
    ) -> None:
        comparison_intent = parse_comparison_intent(goal)
        if comparison_intent is None:
            return

        if self._is_bestbuy_comparison_task(goal=goal, task_id=task_id, steps=steps):
            product_extracts = [
                str(step.args.get("target") or "")
                for step in steps
                if step.type == "extract" and str(step.args.get("target") or "") == "bestbuy_product_facts"
            ]
            if len(product_extracts) < 2:
                raise PlannerError("Best Buy comparison plans must extract bestbuy_product_facts from at least 2 product pages.")
            disallowed_extracts = [
                str(step.args.get("target") or "")
                for step in steps
                if step.type == "extract"
                and str(step.args.get("target") or "") not in {"bestbuy_search_results", "bestbuy_product_facts", "bestbuy_price"}
            ]
            if disallowed_extracts:
                raise PlannerError("Best Buy comparison plans may only use extract targets bestbuy_search_results, bestbuy_product_facts, and bestbuy_price.")
            return

        wiki_urls = [
            str(step.args.get("url") or "")
            for step in steps
            if step.type in {"navigate", "goto"} and str(step.args.get("url") or "").startswith("https://en.wikipedia.org/wiki/")
        ]
        unique_wiki_urls = list(dict.fromkeys(wiki_urls))
        if len(unique_wiki_urls) < 2:
            raise PlannerError("Wikipedia comparison plans must visit at least 2 Wikipedia entity pages.")
        if len(unique_wiki_urls) > 5:
            raise PlannerError("Wikipedia comparison plans must not visit more than 5 entity pages.")

        extract_targets = [
            str(step.args.get("target") or "")
            for step in steps
            if step.type == "extract"
        ]
        if any(target == "table" for target in extract_targets):
            raise PlannerError("Wikipedia comparison plans must not use extract target 'table'; the comparison table is synthesized after extraction.")

        if comparison_intent.requested_columns:
            section_targets = [target for target in extract_targets if target == "section_headings" or target.startswith("section:")]
            if not section_targets:
                raise PlannerError(
                    "Wikipedia comparison plans with explicit columns must extract at least one section target in addition to summaries."
                )

        raw_columns = metadata.get("columns")
        if raw_columns is not None:
            if not isinstance(raw_columns, list):
                raise PlannerError("Wikipedia comparison metadata.columns must be a list when provided.")
            if len(raw_columns) > 5:
                raise PlannerError("Wikipedia comparison metadata.columns must not exceed 5 entries.")

    def _normalize_goal_specific_steps(self, goal: str, steps: list[Step]) -> list[Step]:
        comparison_intent = parse_comparison_intent(goal)
        if comparison_intent is None:
            return steps
        if _is_bestbuy_goal(goal, None):
            return steps
        if any(
            step.type == "extract"
            and str(step.args.get("target") or "").startswith("section:")
            for step in steps
        ):
            return steps

        inferred_sections = self._comparison_section_targets(comparison_intent.requested_columns)
        if not inferred_sections:
            return steps

        normalized: list[Step] = []
        insert_index = 1
        for step in steps:
            normalized.append(step)
            if step.type == "extract" and str(step.args.get("target") or "") == "summary":
                for section_name in inferred_sections:
                    normalized.append(
                        Step(
                            id=f"{step.id}-section-{insert_index}",
                            type="extract",
                            args={"target": f"section:{section_name}"},
                            expected={},
                            timeout_ms=step.timeout_ms,
                        )
                    )
                    insert_index += 1
        return normalized

    def _comparison_section_targets(self, requested_columns: list[str]) -> list[str]:
        section_map = (
            ("conservation", "Conservation"),
            ("habitat", "Habitat"),
            ("physical attributes", "Description"),
            ("description", "Description"),
            ("status", "Status"),
            ("distribution", "Distribution"),
            ("ecology", "Ecology"),
            ("diet", "Diet"),
        )
        targets: list[str] = []
        normalized_columns = [" ".join(column.lower().split()) for column in requested_columns]
        for column in normalized_columns:
            for needle, section_name in section_map:
                if needle in column and section_name not in targets:
                    targets.append(section_name)
                    break
            if len(targets) >= 2:
                break
        return targets

    def _is_bestbuy_comparison_task(self, goal: str, task_id: str | None, steps: list[Step]) -> bool:
        if _is_bestbuy_goal(goal, task_id):
            return True
        return any(
            step.type == "extract" and str(step.args.get("target") or "").startswith("bestbuy_")
            for step in steps
        )
