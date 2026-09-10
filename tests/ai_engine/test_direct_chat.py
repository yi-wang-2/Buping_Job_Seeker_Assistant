from src.libs.ai_engine.context import ContextKind
from src.libs.ai_engine.models import LLMResponse, TokenUsage
from src.libs.ai_engine.skills.builtin import DirectChatSkill


def test_direct_chat_keeps_request_protected_and_workspace_compressible():
    skill = DirectChatSkill()
    items = skill.context_items({
        "message": "解释当前匹配分",
        "page": "job-radar",
        "workspace_context": {"summary": "岗位匹配分来自偏好"},
        "conversation_summary": "用户之前询问过推荐规则",
        "language": "zh",
    })

    request = next(item for item in items if item.id == "direct-chat-request")
    workspace = next(item for item in items if item.id == "direct-chat-workspace")
    history = next(item for item in items if item.id == "direct-chat-history")
    assert request.protected is True
    assert workspace.protected is False and workspace.kind == ContextKind.TASK
    assert history.protected is False and history.kind == ContextKind.HISTORY


def test_direct_chat_returns_markdown_without_structured_route_payload():
    skill = DirectChatSkill()
    result = skill.parse_output(LLMResponse(
        content="### 结论\n\n匹配分用于排序，不等同于录用概率。",
        provider="test", model="test", usage=TokenUsage(total_tokens=20),
    ))
    skill.validate_output(result, {"message": "解释匹配分"})
    assert result.structured_output is None
    assert result.content.startswith("### 结论")
