from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Observation:
    url: str
    title: str
    visible_text: str
    dom_summary: list[str]
    form_state: list[str] = field(default_factory=list)
    screenshot_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
