"""Configuration service — reads/writes secrets.yaml and resume content."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DATA_FOLDER = Path("data_folder")


def load_secrets() -> dict[str, Any]:
    """Load secrets from data_folder/secrets.yaml."""
    secrets_path = DATA_FOLDER / "secrets.yaml"
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_secrets(data: dict[str, Any]) -> None:
    """Merge and save data into secrets.yaml."""
    secrets_path = DATA_FOLDER / "secrets.yaml"
    existing: dict[str, Any] = {}
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    existing.update(data)
    with open(secrets_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, allow_unicode=True)


def load_resume_content(language: str = "zh") -> str:
    """Load resume YAML content by language."""
    filename = "plain_text_resume.yaml" if language == "en" else "plain_text_resume_zh.yaml"
    filepath = DATA_FOLDER / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def save_resume_content(content: str, language: str = "zh") -> None:
    """Save resume YAML content by language."""
    filename = "plain_text_resume.yaml" if language == "en" else "plain_text_resume_zh.yaml"
    filepath = DATA_FOLDER / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
