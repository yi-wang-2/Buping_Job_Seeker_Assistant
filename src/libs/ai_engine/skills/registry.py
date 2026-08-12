from __future__ import annotations

from .base import Skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._disabled: set[str] = set()

    def register(self, skill: Skill, *, replace: bool = False) -> None:
        name = skill.metadata.name
        if name in self._skills and not replace:
            raise ValueError(f"Skill already registered: {name}")
        self._skills[name] = skill
        if skill.metadata.enabled:
            self._disabled.discard(name)
        else:
            self._disabled.add(name)

    def get(self, name: str) -> Skill:
        if name in self._disabled:
            raise ValueError(f"Skill is disabled: {name}")
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {name}") from exc

    def list(self, *, include_disabled: bool = False) -> tuple[Skill, ...]:
        return tuple(
            self._skills[name] for name in sorted(self._skills)
            if include_disabled or name not in self._disabled
        )

    def disable(self, name: str) -> None:
        if name not in self._skills:
            raise KeyError(f"Unknown skill: {name}")
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        if name not in self._skills:
            raise KeyError(f"Unknown skill: {name}")
        self._disabled.discard(name)

    def describe(self) -> tuple[dict[str, object], ...]:
        return tuple({
            "name": skill.metadata.name,
            "version": skill.metadata.version,
            "description": skill.metadata.description,
            "tags": skill.metadata.tags,
            "enabled": skill.metadata.name not in self._disabled,
        } for skill in self.list(include_disabled=True))

