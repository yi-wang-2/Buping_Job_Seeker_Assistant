from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.assistant_service import AssistantService, MAX_ATTACHMENT_BYTES

router = APIRouter()

VALIDATED_CONTENT_CHUNK_SIZE = 12
VALIDATED_CONTENT_INTERVAL_SECONDS = 0.08


class SessionRequest(BaseModel):
    workspace_type: str = Field(min_length=1)
    workspace_object_id: str = "default"
    title: str = ""


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)
    page: str = Field(min_length=1)
    workspace_snapshot: dict[str, Any] = Field(default_factory=dict)
    selected_objects: list[str] = Field(default_factory=list)
    context_refs: list[str] | None = None
    context_labels: dict[str, str] = Field(default_factory=dict)
    api_key: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""


class ProposalApplyRequest(BaseModel):
    confirmation_token: str = Field(min_length=20)


def service() -> AssistantService:
    return AssistantService()


@router.post("/sessions")
def create_session(req: SessionRequest) -> dict[str, Any]:
    return service().create_session(**req.model_dump())


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    result = service().get_session(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Assistant session not found")
    return result


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str) -> dict[str, Any]:
    result = service().get_session(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Assistant session not found")
    return {"items": result["messages"]}


@router.post("/sessions/{session_id}/attachments")
async def upload_attachment(session_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        raw = await file.read(MAX_ATTACHMENT_BYTES + 1)
        return service().upload_attachment(
            session_id, filename=file.filename or "document.txt",
            content_type=file.content_type or "application/octet-stream", raw=raw,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: str, req: MessageRequest) -> dict[str, Any]:
    try:
        return service().send_message(session_id, **req.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Assistant request failed: {exc}") from exc


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(session_id: str, req: MessageRequest) -> StreamingResponse:
    """Stream truthful runtime events, then the validated final response over SSE."""
    assistant_service = service()

    async def event_stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        def publish(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("progress", event))

        async def run() -> None:
            try:
                result = await asyncio.to_thread(
                    assistant_service.send_message,
                    session_id,
                    **req.model_dump(),
                    event_sink=publish,
                )
                await queue.put(("result", result))
            except Exception as exc:
                await queue.put(("error", {"detail": str(exc), "error_type": type(exc).__name__}))
            finally:
                await queue.put(("done", None))

        task = asyncio.create_task(run())
        try:
            while True:
                event_type, payload = await queue.get()
                if event_type == "done":
                    break
                if event_type == "result":
                    content = str(payload.get("assistant_message", {}).get("content") or "")
                    start_payload = {
                        **payload,
                        "assistant_message": {**payload["assistant_message"], "content": ""},
                    }
                    yield _sse("result_start", start_payload)
                    for index in range(0, len(content), VALIDATED_CONTENT_CHUNK_SIZE):
                        yield _sse("content_delta", {
                            "delta": content[index:index + VALIDATED_CONTENT_CHUNK_SIZE],
                        })
                        await asyncio.sleep(VALIDATED_CONTENT_INTERVAL_SECONDS)
                    yield _sse("result_end", payload)
                else:
                    yield _sse(event_type, payload)
        finally:
            await task

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event_type: str, payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    result = service().repository.get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Assistant run not found")
    return result


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, Any]:
    result = service().repository.request_cancel(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Assistant run not found")
    if result["status"] not in {"cancel_requested", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"Assistant run is already {result['status']}")
    return result


@router.post("/proposals/{proposal_id}/confirm")
def confirm_proposal(proposal_id: str) -> dict[str, Any]:
    try:
        return service().confirm_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(proposal_id: str, req: ProposalApplyRequest) -> dict[str, Any]:
    try:
        return service().apply_proposal(proposal_id, req.confirmation_token)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/dismiss")
def dismiss_proposal(proposal_id: str) -> dict[str, Any]:
    try:
        return service().dismiss_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/undo")
def undo_proposal(proposal_id: str) -> dict[str, Any]:
    try:
        return service().undo_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
