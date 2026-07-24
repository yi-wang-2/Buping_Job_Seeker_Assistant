from dataclasses import dataclass

import pytest

from src.libs.ai_engine.exceptions import ProviderInvocationError
from src.libs.ai_engine.models import LLMRequest, Message
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway


@dataclass
class FakeResponse:
    content: str = "ok"
    id: str = "response-1"
    response_metadata: dict = None
    usage_metadata: dict = None

    def __post_init__(self):
        self.response_metadata = self.response_metadata or {"model_name": "fake-model", "finish_reason": "stop"}
        self.usage_metadata = self.usage_metadata or {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}


class FakeClient:
    def __init__(self, effects):
        self.effects = iter(effects)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        effect = next(self.effects)
        if isinstance(effect, Exception):
            raise effect
        return effect


def request():
    return LLMRequest(messages=(Message("user", "hello"),), model="fake-model", provider="openai")


def test_gateway_normalizes_usage():
    client = FakeClient([FakeResponse()])
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: client)

    response = gateway.invoke(request())

    assert response.content == "ok"
    assert response.usage.total_tokens == 13
    assert response.retries == 0


def test_gateway_retries_timeout_with_bound():
    client = FakeClient([TimeoutError("slow"), FakeResponse()])
    gateway = LLMGateway(
        GatewayConfig(max_retries=1, retry_backoff_seconds=0),
        client_factory=lambda _: client,
        sleep=lambda _: None,
    )

    response = gateway.invoke(request())

    assert response.retries == 1
    assert client.calls == 2


def test_gateway_does_not_retry_non_retryable_error():
    client = FakeClient([ValueError("bad request")])
    gateway = LLMGateway(GatewayConfig(max_retries=5), client_factory=lambda _: client)

    with pytest.raises(ProviderInvocationError):
        gateway.invoke(request())

    assert client.calls == 1

