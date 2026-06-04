"""Smoke tests - basic imports and sanity checks."""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_python_version():
    """Verify Python version is 3.11+."""
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version_info}"


def test_project_root_exists():
    """Verify project root directory exists."""
    assert PROJECT_ROOT.exists()
    assert PROJECT_ROOT.is_dir()


def test_required_files_exist():
    """Verify essential project files exist."""
    required_files = [
        "app_ui.py",
        "main.py",
        "config.py",
        "requirements.txt",
        "README.md",
    ]
    for filename in required_files:
        filepath = PROJECT_ROOT / filename
        assert filepath.exists(), f"Missing required file: {filename}"


def test_src_directory_exists():
    """Verify src directory structure."""
    src = PROJECT_ROOT / "src"
    assert src.exists(), "Missing src/ directory"
    assert (src / "libs").exists(), "Missing src/libs/ directory"


def test_interview_prep_module_exists():
    """Verify interview preparation module exists."""
    interview_prep = PROJECT_ROOT / "src" / "libs" / "interview_prep"
    assert interview_prep.exists(), "Missing interview_prep module"
    assert (interview_prep / "__init__.py").exists()
    assert (interview_prep / "interview_generator.py").exists()
    assert (interview_prep / "mock_interview.py").exists()


def test_requirements_format():
    """Verify requirements.txt is readable."""
    req_file = PROJECT_ROOT / "requirements.txt"
    assert req_file.exists()
    content = req_file.read_text(encoding="utf-8")
    assert "gradio" in content
    assert "pytest" in content


def test_gitignore_exists():
    """Verify .gitignore exists and contains expected entries."""
    gitignore = PROJECT_ROOT / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert "__pycache__" in content
    assert ".env" in content


def test_data_folder_exists():
    """Verify data folder structure."""
    data_folder = PROJECT_ROOT / "data_folder"
    assert data_folder.exists(), "Missing data_folder/"
    assert (data_folder / "plain_text_resume.yaml").exists()
    assert (data_folder / "secrets.yaml").exists()
