from __future__ import annotations

from .base import Skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill, *, replace: bool = False) -> None:
        name = skill.metadata.name
        if name in self._skills and not replace:
            raise ValueError(f"Skill already registered: {name}")
        self._skills[name] = skill

    def get(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {name}") from exc

    def list(self) -> tuple[Skill, ...]:
        return tuple(self._skills[name] for name in sorted(self._skills))

