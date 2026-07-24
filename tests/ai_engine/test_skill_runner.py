from dataclasses import dataclass

from src.libs.ai_engine.models import TokenUsage
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
from src.libs.ai_engine.runtime import AIRuntime
from src.libs.ai_engine.skills import SkillRegistry
from src.libs.ai_engine.skills.builtin import TextRewriterSkill


@dataclass
class Response:
    content: str = "改写结果"
    response_metadata: dict = None
    usage_metadata: dict = None

    def __post_init__(self):
        self.response_metadata = {"model": "fake"}
        self.usage_metadata = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}


class Client:
    def invoke(self, messages):
        assert messages[0]["role"] == "system"
        return Response()


def test_runtime_executes_text_rewriter_end_to_end():
    prompts = {"zh": {"fix_grammar": "修正语法"}, "en": {"fix_grammar": "Fix grammar"}}
    registry = SkillRegistry()
    registry.register(TextRewriterSkill(prompts))
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: Client())

    result = AIRuntime(gateway, registry).execute(
        "text_rewriter",
        {"text": "测试", "mode": "fix_grammar", "target_language": "zh"},
        provider="fake",
        model="fake",
    )

    assert result.content == "改写结果"
    assert result.usage == TokenUsage(5, 2, 7)

