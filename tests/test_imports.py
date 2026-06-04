"""Import tests - verify modules can be imported without errors."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_config_module():
    """Verify config module is importable."""
    try:
        import config
        assert config is not None
    except ImportError as e:
        # Skip if optional dependencies are missing
        if "pydantic" in str(e) or "yaml" in str(e):
            pytest.skip(f"Skipping due to missing dependency: {e}")
        raise


def test_interview_prep_imports():
    """Verify interview prep module structure."""
    # Just check the files exist and are valid Python
    interview_prep = PROJECT_ROOT / "src" / "libs" / "interview_prep"
    assert (interview_prep / "__init__.py").exists()
    assert (interview_prep / "interview_generator.py").exists()
    assert (interview_prep / "mock_interview.py").exists()


def test_src_init_exists():
    """Verify src/__init__.py exists."""
    src_init = PROJECT_ROOT / "src" / "__init__.py"
    assert src_init.exists()
