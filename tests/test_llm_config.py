import pytest

from backend.services.config_service import discover_llm_models, resolve_llm_model


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
