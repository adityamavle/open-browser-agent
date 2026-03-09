from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class Observation:
    url: str
    title: str
    visible_text: str
    dom_summary: list[str]
    screenshot_path: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
