from dataclasses import dataclass, replace

from src.libs.ai_engine.models import TokenUsage
from src.libs.ai_engine.providers import GatewayConfig, LLMGateway
from src.libs.ai_engine.runtime import AIRuntime
from src.libs.ai_engine.context import ContextItem, ContextKind, ContextProviderResult
from src.libs.ai_engine.skills import SkillRegistry
from src.libs.ai_engine.skills.builtin import JDAnalyzerSkill, TextRewriterSkill


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


def test_jd_analyzer_executes_declared_archive_tool_after_validation():
    class JDClient:
        def invoke(self, messages):
            return Response(content='{"role":"AI 工程师","company":"示例公司","required_skills":["Python"]}')

    archived = []
    registry = SkillRegistry()
    registry.register(JDAnalyzerSkill())
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: JDClient())
    runtime = AIRuntime(
        gateway, registry,
        available_tools={"archive_job_description": lambda **kwargs: archived.append(kwargs) or {"id": "jd-1"}},
    )

    result = runtime.execute(
        "jd_analyzer", {"job_description": "示例公司招聘 AI 工程师，要求 Python"},
        provider="fake", model="fake",
    )

    assert archived[0]["role"] == "AI 工程师"
    assert result.tool_results[0]["output"]["id"] == "jd-1"


def test_runtime_context_provider_runs_before_budgeting_and_is_observable():
    prompts = {"zh": {"fix_grammar": "修正语法"}, "en": {"fix_grammar": "Fix grammar"}}
    skill = TextRewriterSkill(prompts)
    skill.metadata = replace(skill.metadata, context_providers=("test",))

    class Provider:
        def provide(self, **_kwargs):
            return ContextProviderResult(
                items=(ContextItem(
                    "retrieved", ContextKind.RETRIEVED, "外部依据", "test", relevance=1,
                ),),
                metadata={"knowledge_unit_ids": ["unit-1"]},
                warnings=("provider warning",),
            )

    registry = SkillRegistry()
    registry.register(skill)
    gateway = LLMGateway(GatewayConfig(), client_factory=lambda _: Client())
    result = AIRuntime(
        gateway, registry, context_providers={"test": Provider()},
    ).execute(
        "text_rewriter", {"text": "测试", "mode": "fix_grammar", "target_language": "zh"},
        provider="fake", model="fake",
    )

    assert result.context_metadata["knowledge_unit_ids"] == ["unit-1"]
    assert result.warnings == ("provider warning",)

