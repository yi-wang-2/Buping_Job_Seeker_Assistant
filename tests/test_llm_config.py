import pytest
import yaml

from backend.services import config_service
from backend.services.config_service import PUBLIC_DEMO_MODE, discover_llm_models, resolve_llm_model


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_provider_default_does_not_reuse_saved_model_from_other_provider():
    assert resolve_llm_model("deepseek", saved_model="MiniMax-M3") == "deepseek-chat"


def test_explicit_model_always_wins():
    assert resolve_llm_model("deepseek", "deepseek-reasoner", "MiniMax-M3") == "deepseek-reasoner"


def test_saved_custom_model_is_used_only_for_same_provider():
    assert resolve_llm_model("deepseek", saved_model="deepseek-reasoner", saved_provider="deepseek") == "deepseek-reasoner"


def test_unknown_provider_requires_explicit_model():
    with pytest.raises(ValueError, match="Model ID is required"):
        resolve_llm_model("custom-provider")


@pytest.mark.anyio
async def test_model_discovery_skips_request_without_credentials():
    assert await discover_llm_models("", "https://api.deepseek.com/v1", "openai_chat") == []


def test_public_demo_mode_constant_is_available():
    assert isinstance(PUBLIC_DEMO_MODE, bool)


def test_public_demo_mode_redacts_and_never_persists_secrets(tmp_path, monkeypatch):
    secrets_path = tmp_path / "secrets.yaml"
    secrets_path.write_text(
        yaml.safe_dump({"llm_api_key": "secret", "minimax_tts_api_key": "tts-secret"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_service, "DATA_FOLDER", tmp_path)
    monkeypatch.setattr(config_service, "PUBLIC_DEMO_MODE", True)

    loaded = config_service.load_secrets()
    assert loaded["llm_api_key"] == ""
    assert loaded["minimax_tts_api_key"] == ""

    config_service.save_secrets({"llm_api_key": "replacement"})
    persisted = yaml.safe_load(secrets_path.read_text(encoding="utf-8"))
    assert persisted["llm_api_key"] == "secret"
