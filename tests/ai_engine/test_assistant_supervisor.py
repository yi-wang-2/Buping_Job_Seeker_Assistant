from src.libs.ai_engine.assistant import AssistantSupervisorSkill, AssistantTurnPresenter, SupervisorTurn
from src.libs.ai_engine.context import ContextManager, TokenBudgetAllocator
from src.libs.ai_engine.models import LLMResponse, TokenUsage
from src.libs.ai_engine.presentation import CalloutBlock, MarkdownRenderer, ResponseDocument
from src.libs.ai_engine.presentation.service import ensure_formatted_markdown


def test_supervisor_normalizes_provider_nulls_before_strict_validation():
    skill = AssistantSupervisorSkill()
    result = skill.parse_output(LLMResponse(
        content='{"kind":"skill_call","intent":"rewrite","target_refs":null,'
                '"name":"text_rewriter","arguments":null,"response":null,"reason_code":null}',
        model="test", provider="test", usage=TokenUsage(total_tokens=12),
    ))

    assert result.structured_output["target_refs"] == []
    assert result.structured_output["arguments"] == {}
    assert result.structured_output["response"] == ""
    assert result.structured_output["follow_up"] == ""
    assert result.structured_output["reason_code"] == "unspecified"


def test_direct_response_uses_generic_follow_up_block():
    document = AssistantTurnPresenter.present(SupervisorTurn(
        kind="final_response", intent="explain", response="这是问题的主要原因。",
        follow_up="需要我继续检查相关实现吗？", reason_code="informational_request",
    ))

    rendered = MarkdownRenderer.render(document)
    assert rendered == (
        "### 回答\n\n这是问题的主要原因。\n\n---\n\n需要我继续检查相关实现吗？"
    )


def test_legacy_final_response_is_rerouted_to_direct_chat():
    skill = AssistantSupervisorSkill()
    result = skill.parse_output(LLMResponse(
        content='{"kind":"final_response","intent":"explain","target_refs":[],"name":null,'
                '"arguments":{},"response":"旧的长回答","follow_up":"继续吗",'
                '"reason_code":"informational"}',
        model="test", provider="test", usage=TokenUsage(total_tokens=12),
    ))

    assert result.structured_output["kind"] == "skill_call"
    assert result.structured_output["name"] == "direct_chat"
    assert result.structured_output["response"] == ""


def test_callout_and_fallback_results_are_always_formatted_markdown():
    rendered = MarkdownRenderer.render(ResponseDocument((CalloutBlock("第一行\n第二行"),)))
    assert rendered == "> 第一行\n> 第二行"
    assert ensure_formatted_markdown("普通结果") == "### 处理结果\n\n普通结果"
    assert ensure_formatted_markdown("### 已有标题\n\n正文") == "### 已有标题\n\n正文"


def test_uploaded_documents_use_compressible_task_context():
    skill = AssistantSupervisorSkill()
    inputs = {
        "message": "总结文档", "page": "resume", "selected_objects": [],
        "available_skills": [], "available_workflows": [], "available_actions": [],
        "conversation_summary": "", "workspace_snapshot": {
            "language": "zh", "uploaded_documents": [{
                "id": "doc-1", "filename": "需求.txt", "content": "正文" * 2000,
                "truncated": False,
            }],
        },
    }

    items = skill.context_items(inputs)
    request = next(item for item in items if item.id == "supervisor-input")
    document = next(item for item in items if item.id == "supervisor-upload-0")
    assert "正文正文" not in request.content
    assert document.protected is False
    assert document.kind.value == "task"
    assert document.metadata["untrusted"] is True


def test_large_job_snapshot_is_not_embedded_in_protected_request():
    skill = AssistantSupervisorSkill()
    jobs = [{
        "id": f"job-{index}", "company": "很长的企业名称" * 8,
        "role": "人工智能智能体开发工程师" * 8, "match_score": 90 - index,
    } for index in range(20)]
    inputs = {
        "message": "给我推荐十个最适合我的岗位", "page": "job-radar",
        "available_skills": ["job_recommender"], "workspace_snapshot": {
            "job_preferences": {"target_roles": ["AI Agent开发"]}, "job_results": jobs,
        },
    }

    items = skill.context_items(inputs)
    request = next(item for item in items if item.id == "supervisor-input")
    workspace = next(item for item in items if item.id == "supervisor-workspace")
    assert "很长的企业名称" not in request.content
    assert workspace.protected is False
    allocation = TokenBudgetAllocator().allocate(skill.metadata.token_budget, skill.metadata.context_weights)
    bundle = ContextManager().build(items, allocation)
    assert any(item.id == "supervisor-input" for item in bundle.items)
