import pytest

from backend.services.assistant_repository import AssistantRepository


def test_assistant_session_messages_runs_and_proposals_are_persisted(tmp_path):
    repository = AssistantRepository(tmp_path / "assistant.sqlite3")
    session = repository.get_or_create_session("resume", "resume-1")
    same_session = repository.get_or_create_session("resume", "resume-1")
    assert same_session["id"] == session["id"]

    message = repository.add_message(session["id"], "user", "润色这句话")
    run = repository.create_run(session["id"], "resume")
    proposal = repository.create_proposal(
        run["id"], proposal_type="resume_text_rewrite", target_ref="resume.selection",
        target_version="3", payload={"original_text": "旧", "replacement_text": "新"},
    )
    finished = repository.finish_run(
        run["id"], mode="direct_skill", intent="rewrite", dispatch_path="supervisor",
        policy={"allowed": True}, usage={"total_tokens": 12},
    )

    assert repository.list_messages(session["id"])[0]["id"] == message["id"]
    assert repository.get_proposal(proposal["id"])["payload"]["replacement_text"] == "新"
    assert repository.list_pending_proposals(session["id"])[0]["id"] == proposal["id"]
    assert repository.set_proposal_status(proposal["id"], "applied")["status"] == "applied"
    assert finished["effective_mode"] == "direct_skill"

    attachment = repository.create_attachment(
        session["id"], filename="jd.txt", mime_type="text/plain", size_bytes=12,
        content_text="AI Agent 工程师",
    )
    assert repository.list_attachments(session["id"])[0]["id"] == attachment["id"]
    loaded = repository.get_attachments(session["id"], [attachment["id"]])
    assert loaded[0]["content_text"] == "AI Agent 工程师"
    other = repository.get_or_create_session("resume", "resume-2")
    assert repository.get_attachments(other["id"], [attachment["id"]]) == []
    assert finished["usage"]["total_tokens"] == 12


def test_assistant_run_can_be_cancelled_and_discovered_after_refresh(tmp_path):
    repository = AssistantRepository(tmp_path / "assistant.sqlite3")
    session = repository.get_or_create_session("resume", "resume-cancel")
    run = repository.create_run(session["id"], "resume")

    assert repository.list_active_runs(session["id"])[0]["id"] == run["id"]
    assert repository.request_cancel(run["id"])["status"] == "cancel_requested"
    assert repository.is_cancel_requested(run["id"]) is True
    assert repository.mark_cancelled(run["id"])["status"] == "cancelled"
    assert repository.list_active_runs(session["id"]) == []


def test_proposal_requires_one_time_confirmation_token(tmp_path):
    repository = AssistantRepository(tmp_path / "assistant.sqlite3")
    session = repository.get_or_create_session("resume", "proposal-token")
    run = repository.create_run(session["id"], "resume")
    proposal = repository.create_proposal(
        run["id"], proposal_type="resume_text_rewrite", target_ref="resume.selection",
        target_version="1", payload={"original_text": "旧", "replacement_text": "新"},
    )
    token = repository.issue_confirmation_token(proposal["id"])

    applied = repository.apply_proposal_with_token(proposal["id"], token)

    assert applied["status"] == "applied"
    assert repository.list_actionable_proposals(session["id"])[0]["status"] == "applied"
    with pytest.raises(ValueError, match="already applied"):
        repository.apply_proposal_with_token(proposal["id"], token)
    assert repository.undo_proposal(proposal["id"])["status"] == "undone"
