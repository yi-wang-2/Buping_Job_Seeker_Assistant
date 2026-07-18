"""Interview preparation and mock interview service."""

from __future__ import annotations

import time
import hashlib
import html as html_lib
import io
import json
import os
import re
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.services.config_service import load_secrets
from backend.services.config_service import resolve_llm_model

import config as cfg

DATA_FOLDER = Path("data_folder")
OUTPUT_FOLDER = DATA_FOLDER / "output"


def _normalize_interview_model_type(model_type: str, base_url: str = "") -> str:
    """Map settings provider ids to the protocol ids used by interview LLM code."""
    raw_model = (model_type or "").strip().lower()
    raw_url = (base_url or "").strip().lower()
    if raw_model in {"anthropic", "claude", "minimax-anth"} or "minimaxi.com/anthropic" in raw_url:
        return "anthropic"
    if raw_model in {
        "openai",
        "openai_chat",
        "openai-resp",
        "openai_response",
        "minimax-chat",
        "minimax-resp",
        "deepseek",
        "moonshot",
        "qwen",
        "doubao",
        "yi",
        "zhipu",
        "ollama",
    }:
        return "openai"
    return raw_model or "anthropic"


def _get_effective_config(api_key: str = "", model_type: str = "", base_url: str = "", model_name: str = "") -> dict[str, str]:
    """Resolve effective LLM config from args > secrets > config.py."""
    secrets = load_secrets()
    raw_model_type = model_type or secrets.get("llm_model_type", "anthropic")
    effective_base_url = base_url or secrets.get("llm_base_url", "") or cfg.ANTHROPIC_BASE_URL
    return {
        "api_key": api_key or secrets.get("llm_api_key", "") or cfg.ANTHROPIC_AUTH_TOKEN,
        "model_type": _normalize_interview_model_type(raw_model_type, effective_base_url),
        "model_name": resolve_llm_model(raw_model_type, model_name, secrets.get("llm_model", ""), secrets.get("llm_model_provider", "")),
        "base_url": effective_base_url,
    }


def generate_interview_prep(
    api_key: str,
    model_type: str,
    model_name: str,
    base_url: str,
    job_description: str,
    interview_type: str = "综合面试",
    question_count: int = 10,
    resume_language: str = "zh",
) -> dict[str, Any]:
    """Generate interview preparation report. Returns {report, file_path, status}."""
    from src.libs.interview_prep import InterviewPrepGenerator

    effective = _get_effective_config(api_key, model_type, base_url, model_name)

    resume_file = DATA_FOLDER / ("plain_text_resume.yaml" if resume_language == "en" else "plain_text_resume_zh.yaml")
    with open(resume_file, "r", encoding="utf-8") as f:
        resume_text = f.read()

    generator = InterviewPrepGenerator(
        api_key=effective["api_key"],
        model_type=effective["model_type"],
        base_url=effective["base_url"],
        model_name=effective["model_name"],
    )
    report = generator.generate(
        resume_text=resume_text,
        job_description=job_description or "",
        interview_type=interview_type,
        question_count=int(question_count),
        language=resume_language,
    )

    output_dir = OUTPUT_FOLDER / "interview_prep"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"interview_prep_{timestamp}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return {"report": report, "file_path": str(output_path), "status": "success"}


# In-memory mock interview sessions
_sessions: dict[str, Any] = {}
_chattts_engine: Any = None
_chattts_infer_params: Any = None
_chattts_device: str = ""
_chattts_load_errors: list[str] = []
_kokoro_pipeline: Any = None
_kokoro_load_error: str = ""
_tts_cache: dict[str, tuple[bytes, str]] = {}
_TTS_CACHE_LIMIT = 64
_KOKORO_DEFAULT_REPO = "hexgrad/Kokoro-82M-v1.1-zh"
_KOKORO_DEFAULT_VOICE = "zf_001"


def _get_kokoro_repo_id() -> str:
    return os.getenv("KOKORO_REPO_ID", _KOKORO_DEFAULT_REPO)


def _get_kokoro_model_filename(repo_id: str) -> str:
    return "kokoro-v1_1-zh.pth" if repo_id.endswith("Kokoro-82M-v1.1-zh") else "kokoro-v1_0.pth"


def _get_kokoro_model_dir(repo_id: str) -> Path:
    default_name = repo_id.rsplit("/", 1)[-1]
    return Path(os.getenv("KOKORO_MODEL_DIR", "") or DATA_FOLDER / "models" / default_name)


def get_mock_interview_tts_voices() -> dict[str, list[dict[str, str]]]:
    """Return locally available TTS voices without loading a speech model."""
    voices_dir = _get_kokoro_model_dir(_get_kokoro_repo_id()) / "voices"
    kokoro_voices: list[dict[str, str]] = []
    if voices_dir.is_dir():
        for voice_path in sorted(voices_dir.glob("*.pt")):
            voice_id = voice_path.stem
            gender = "女声" if voice_id.startswith(("af_", "bf_", "zf_")) else "男声"
            kokoro_voices.append({"id": voice_id, "label": f"{gender} {voice_id}"})
    if not kokoro_voices:
        kokoro_voices.append({"id": _KOKORO_DEFAULT_VOICE, "label": f"女声 {_KOKORO_DEFAULT_VOICE}"})
    return {"kokoro": kokoro_voices}


def _markdown_line_to_pdf_html(text: str) -> str:
    escaped = html_lib.escape(text.strip())
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _write_mock_interview_pdf(markdown_text: str, output_path: Path) -> None:
    """Render a mock interview markdown report to PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass

    styles = getSampleStyleSheet()
    for style_name in ("Title", "Heading1", "Heading2", "Heading3", "BodyText"):
        styles[style_name].fontName = "STSong-Light"
        styles[style_name].leading = max(styles[style_name].leading, styles[style_name].fontSize + 4)
    styles["BodyText"].fontSize = 10
    styles["BodyText"].spaceAfter = 6

    story = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue
        if line == "---":
            story.append(Spacer(1, 8))
            continue

        if line.startswith("# "):
            story.append(Paragraph(_markdown_line_to_pdf_html(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(_markdown_line_to_pdf_html(line[3:]), styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(_markdown_line_to_pdf_html(line[4:]), styles["Heading3"]))
        else:
            story.append(Paragraph(_markdown_line_to_pdf_html(line), styles["BodyText"]))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Mock Interview Evaluation",
    )
    doc.build(story)


def start_mock_interview(
    api_key: str,
    model_type: str,
    model_name: str,
    base_url: str,
    resume_text: str,
    job_description: str,
    company_name: str = "",
    company_industry: str = "",
    job_title: str = "",
    interview_type: str = "综合面试",
    interview_style: str = "专业型",
) -> dict[str, Any]:
    """Start a mock interview session. Returns {history, session_id, status}."""
    from src.libs.interview_prep import (
        MockInterviewer,
        CandidateProfile,
        CompanyProfile,
        JobProfile,
        InterviewStyle,
    )

    effective = _get_effective_config(api_key, model_type, base_url, model_name)

    if not resume_text.strip():
        return {"history": [], "session_id": None, "status": "❌ 请先提供简历内容"}
    if not job_description.strip():
        return {"history": [], "session_id": None, "status": "❌ 请先提供职位描述 (JD)"}

    candidate = CandidateProfile(name="候选人", resume_text=resume_text, target_position=job_title or "应聘岗位")
    company = CompanyProfile(name=company_name or "某公司", industry=company_industry or "", culture="")
    job = JobProfile(title=job_title or "应聘岗位", description=job_description)

    style_map = {
        "友善型": InterviewStyle.FRIENDLY,
        "专业型": InterviewStyle.PROFESSIONAL,
        "压力型": InterviewStyle.PRESSURE,
        "学术型": InterviewStyle.ACADEMIC,
        "闲聊型": InterviewStyle.CASUAL,
    }
    style_enum = style_map.get(interview_style, InterviewStyle.PROFESSIONAL)

    interviewer = MockInterviewer(
        api_key=effective["api_key"],
        model_type=effective["model_type"],
        base_url=effective["base_url"],
        model_name=effective["model_name"],
    )
    session = interviewer.start_session(
        candidate=candidate,
        company=company,
        job=job,
        interview_type=interview_type,
        style=style_enum,
    )

    # Store session for later use
    _sessions[session.session_id] = {
        "interviewer": interviewer,
        "session": session,
        "config": {
            "api_key": effective["api_key"],
            "model_type": effective["model_type"],
            "model_name": effective["model_name"],
            "base_url": effective["base_url"],
            "resume_text": resume_text,
            "job_description": job_description,
            "company_name": company_name,
            "company_industry": company_industry,
            "job_title": job_title,
            "interview_type": interview_type,
            "interview_style": interview_style,
        },
    }

    history = [{"role": "assistant", "content": session.messages[0].content}] if session.messages else []
    return {"history": history, "session_id": session.session_id, "status": "✅ 面试已开始！"}


def submit_mock_answer(
    session_id: str,
    user_message: str,
    history: list[dict],
    context_window: int = 5,
) -> dict[str, Any]:
    """Submit an answer in a mock interview. Returns {history, session_id, status}."""
    from src.libs.interview_prep.mock_interview import InterviewMessage, InterviewRound

    if not session_id or session_id not in _sessions:
        return {"history": history, "session_id": session_id, "status": "❌ 请先开始面试"}
    if not user_message.strip():
        return {"history": history, "session_id": session_id, "status": "❌ 请输入回答"}

    stored = _sessions[session_id]
    interviewer = stored["interviewer"]

    # Re-create session from history for stateless call
    from src.libs.interview_prep import MockInterviewSession
    session = MockInterviewSession(
        session_id=session_id,
        candidate=interviewer.sessions[session_id].candidate,
        company=interviewer.sessions[session_id].company,
        job=interviewer.sessions[session_id].job,
        interview_type=stored["config"]["interview_type"],
        style=interviewer.sessions[session_id].style,
        context_window=max(1, min(int(context_window or 5), 10)),
    )
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user" and content:
            session.messages.append(InterviewMessage(role="candidate", content=content, timestamp=time.time(), round=InterviewRound.OPENING))
        elif role == "assistant" and content:
            session.messages.append(InterviewMessage(role="interviewer", content=content, timestamp=time.time(), round=InterviewRound.OPENING))

    interviewer.sessions[session_id] = session
    next_question_msg = interviewer.submit_answer(session_id, user_message)

    new_history = list(history) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": next_question_msg.content},
    ]
    return {"history": new_history, "session_id": session_id, "status": "✅ 已收到回答"}


async def synthesize_mock_interview_speech(
    text: str,
    voice: str = "",
    rate: str = "+0%",
    provider: str = "minimax",
) -> tuple[bytes, str]:
    """Synthesize interviewer speech and return (audio bytes, media type)."""
    clean_text = " ".join((text or "").split())
    if not clean_text:
        raise ValueError("Text cannot be empty")
    if len(clean_text) > 700:
        clean_text = clean_text[:700]

    provider_name = (provider or os.getenv("MOCK_INTERVIEW_TTS_PROVIDER", "minimax")).lower()
    max_token_setting = os.getenv("CHAT_TTS_MAX_NEW_TOKEN", "1280")
    cache_key = hashlib.sha256(f"{provider_name}|{voice}|{rate}|{max_token_setting}|{clean_text}".encode("utf-8")).hexdigest()
    if cache_key in _tts_cache:
        return _tts_cache[cache_key]

    primary_error: Exception | None = None
    if provider_name == "minimax":
        try:
            result = (await _synthesize_minimax_speech(clean_text, voice=voice, rate=rate), "audio/mpeg")
            _cache_tts_result(cache_key, result)
            return result
        except Exception as exc:
            primary_error = exc

    if provider_name == "kokoro":
        try:
            result = (_synthesize_kokoro_speech(clean_text, voice=voice, rate=rate), "audio/wav")
            _cache_tts_result(cache_key, result)
            return result
        except Exception as exc:
            primary_error = exc

    if provider_name == "chattts":
        try:
            result = (_synthesize_chattts_speech(clean_text), "audio/wav")
            _cache_tts_result(cache_key, result)
            return result
        except Exception as exc:
            # ChatTTS is preferred for quality, but edge-tts is a lighter network fallback.
            primary_error = exc

    if primary_error is not None:
        raise RuntimeError(f"{provider_name} TTS failed: {primary_error}") from primary_error
    raise RuntimeError(f"Unsupported TTS provider: {provider_name}")


async def stream_mock_interview_speech(
    text: str,
    voice: str = "",
    rate: str = "+0%",
    provider: str = "minimax",
):
    """Stream interviewer speech chunks as audio bytes."""
    clean_text = " ".join((text or "").split())
    if not clean_text:
        raise ValueError("Text cannot be empty")
    if len(clean_text) > 700:
        clean_text = clean_text[:700]

    provider_name = (provider or "minimax").lower()
    if provider_name != "minimax":
        audio, _ = await synthesize_mock_interview_speech(clean_text, voice=voice, rate=rate, provider=provider_name)
        yield audio
        return

    async for chunk in _stream_minimax_speech(clean_text, voice=voice, rate=rate):
        yield chunk


def _cache_tts_result(cache_key: str, result: tuple[bytes, str]) -> None:
    _tts_cache[cache_key] = result
    if len(_tts_cache) > _TTS_CACHE_LIMIT:
        _tts_cache.pop(next(iter(_tts_cache)))


def _rate_to_kokoro_speed(rate: str) -> float:
    match = re.match(r"^([+-]?\d+)%$", (rate or "").strip())
    if not match:
        return 1.0
    speed = 1.0 + (int(match.group(1)) / 100.0)
    return max(0.5, min(speed, 2.0))


def _get_minimax_tts_api_key() -> str:
    secrets = load_secrets()
    return (
        os.getenv("MINIMAX_TTS_API_KEY", "").strip()
        or str(secrets.get("minimax_tts_api_key", "")).strip()
        or str(secrets.get("minimax_api_key", "")).strip()
        or str(secrets.get("llm_api_key", "")).strip()
    )


def _get_minimax_tts_url() -> str:
    return os.getenv("MINIMAX_TTS_URL", "https://api-bj.minimaxi.com/v1/t2a_v2").strip()


def _get_minimax_voice(voice: str = "") -> str:
    return voice or os.getenv("MINIMAX_TTS_VOICE", "Chinese (Mandarin)_Reliable_Executive")


def _rate_to_minimax_speed(rate: str) -> float:
    match = re.match(r"^([+-]?\d+)%$", (rate or "").strip())
    if match:
        speed = 1.0 + int(match.group(1)) / 100.0
    else:
        speed = float(os.getenv("MINIMAX_TTS_SPEED", "1.0"))
    return max(0.5, min(speed, 2.0))


def _build_minimax_tts_payload(text: str, voice: str = "", rate: str = "+0%", stream: bool = False) -> dict[str, Any]:
    payload = {
        "model": os.getenv("MINIMAX_TTS_MODEL", "speech-2.8-turbo"),
        "text": text,
        "stream": stream,
        "voice_setting": {
            "voice_id": _get_minimax_voice(voice),
            "speed": _rate_to_minimax_speed(rate),
            "vol": float(os.getenv("MINIMAX_TTS_VOLUME", "1")),
            "pitch": int(os.getenv("MINIMAX_TTS_PITCH", "0")),
        },
        "audio_setting": {
            "sample_rate": int(os.getenv("MINIMAX_TTS_SAMPLE_RATE", "32000")),
            "bitrate": int(os.getenv("MINIMAX_TTS_BITRATE", "128000")),
            "format": "mp3",
            "channel": 1,
        },
        "language_boost": os.getenv("MINIMAX_TTS_LANGUAGE_BOOST", "Chinese"),
        "subtitle_enable": False,
    }
    if stream:
        payload["stream_options"] = {"exclude_aggregated_audio": True}
    return payload


def validate_minimax_tts_config() -> None:
    if not _get_minimax_tts_api_key():
        raise RuntimeError("MiniMax TTS API key is missing. Set MINIMAX_TTS_API_KEY or minimax_tts_api_key in secrets.yaml.")


def _decode_minimax_audio_hex(value: Any) -> bytes:
    if not value:
        return b""
    try:
        return bytes.fromhex(str(value))
    except ValueError as exc:
        raise RuntimeError("MiniMax TTS returned invalid audio hex.") from exc


def _minimax_error_from_payload(payload: dict[str, Any]) -> str:
    base_resp = payload.get("base_resp") or {}
    status_code = base_resp.get("status_code", 0)
    status_msg = base_resp.get("status_msg", "")
    if status_code and status_code != 0:
        return f"MiniMax TTS error {status_code}: {status_msg or 'unknown error'}"
    return ""


async def _synthesize_minimax_speech(text: str, voice: str = "", rate: str = "+0%") -> bytes:
    validate_minimax_tts_config()
    import httpx

    headers = {
        "Authorization": f"Bearer {_get_minimax_tts_api_key()}",
        "Content-Type": "application/json",
    }
    payload = _build_minimax_tts_payload(text, voice=voice, rate=rate, stream=False)
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(_get_minimax_tts_url(), headers=headers, json=payload)
        response.raise_for_status()
    data = response.json()
    if error := _minimax_error_from_payload(data):
        raise RuntimeError(error)
    audio = _decode_minimax_audio_hex((data.get("data") or {}).get("audio"))
    if not audio:
        raise RuntimeError("MiniMax TTS returned empty audio")
    return audio


async def _stream_minimax_speech(text: str, voice: str = "", rate: str = "+0%"):
    validate_minimax_tts_config()
    import httpx

    headers = {
        "Authorization": f"Bearer {_get_minimax_tts_api_key()}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = _build_minimax_tts_payload(text, voice=voice, rate=rate, stream=True)
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", _get_minimax_tts_url(), headers=headers, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                raw = line.strip()
                if not raw:
                    continue
                if raw.startswith("data:"):
                    raw = raw[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if error := _minimax_error_from_payload(event):
                    raise RuntimeError(error)
                audio = _decode_minimax_audio_hex((event.get("data") or {}).get("audio"))
                if audio:
                    yield audio


def _float_audio_to_wav_bytes(audio: Any, sample_rate: int = 24000) -> bytes:
    """Encode a float audio array to 16-bit PCM WAV bytes."""
    import numpy as np

    array = np.asarray(audio, dtype=np.float32)
    if array.ndim > 1:
        array = array.reshape(-1)
    array = np.nan_to_num(array)
    array = np.clip(array, -1.0, 1.0)
    pcm = (array * 32767).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _get_kokoro_pipeline() -> Any:
    """Lazy-load Kokoro for local Chinese TTS."""
    global _kokoro_pipeline, _kokoro_load_error
    if _kokoro_pipeline is not None:
        return _kokoro_pipeline

    try:
        from kokoro import KModel, KPipeline
    except ModuleNotFoundError as exc:
        _kokoro_load_error = "Kokoro is not installed. Please install project dependencies."
        raise RuntimeError(_kokoro_load_error) from exc

    lang_code = os.getenv("KOKORO_LANG_CODE", "z")
    repo_id = _get_kokoro_repo_id()
    model_dir = _get_kokoro_model_dir(repo_id)
    config_path = Path(os.getenv("KOKORO_CONFIG_PATH", "") or model_dir / "config.json")
    model_path = Path(os.getenv("KOKORO_MODEL_PATH", "") or model_dir / _get_kokoro_model_filename(repo_id))
    device = os.getenv("KOKORO_DEVICE", "auto").strip().lower()
    if device in {"", "auto"}:
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    try:
        if config_path.exists() and model_path.exists():
            model = KModel(repo_id=repo_id, config=str(config_path), model=str(model_path)).to(device).eval()
            _kokoro_pipeline = KPipeline(lang_code=lang_code, repo_id=repo_id, model=model)
        else:
            _kokoro_pipeline = KPipeline(lang_code=lang_code, repo_id=repo_id, device=device)
        _kokoro_load_error = ""
        return _kokoro_pipeline
    except Exception as exc:
        _kokoro_load_error = str(exc)
        raise RuntimeError(f"Kokoro failed to initialize: {exc}") from exc


def _synthesize_kokoro_speech(text: str, voice: str = _KOKORO_DEFAULT_VOICE, rate: str = "+0%") -> bytes:
    pipeline = _get_kokoro_pipeline()
    configured_voice = voice or os.getenv("KOKORO_VOICE", _KOKORO_DEFAULT_VOICE)
    voice_path = Path(os.getenv("KOKORO_VOICE_PATH", "") or _get_kokoro_model_dir(_get_kokoro_repo_id()) / "voices" / f"{configured_voice}.pt")
    voice_name = str(voice_path) if voice_path.exists() else configured_voice
    speed = _rate_to_kokoro_speed(rate)
    chunks: list[Any] = []
    generator = pipeline(text, voice=voice_name, speed=speed)
    for item in generator:
        audio = item[-1] if isinstance(item, tuple) else getattr(item, "audio", None)
        if audio is not None:
            chunks.append(audio)
    if not chunks:
        raise RuntimeError("Kokoro returned empty audio")
    if len(chunks) == 1:
        return _float_audio_to_wav_bytes(chunks[0], sample_rate=24000)

    import numpy as np

    return _float_audio_to_wav_bytes(np.concatenate(chunks), sample_rate=24000)


def _get_chattts_engine() -> tuple[Any, Any]:
    """Lazy-load ChatTTS and cache the model across requests."""
    global _chattts_engine, _chattts_infer_params, _chattts_device, _chattts_load_errors
    if _chattts_engine is not None:
        return _chattts_engine, _chattts_infer_params

    try:
        import ChatTTS
    except ModuleNotFoundError as exc:
        raise RuntimeError("ChatTTS is not installed. Please install project dependencies.") from exc

    try:
        import torch
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyTorch is required by ChatTTS but is not installed.") from exc

    model_path = Path(os.getenv("CHAT_TTS_MODEL_PATH", "") or DATA_FOLDER / "models" / "ChatTTS")
    allow_download = os.getenv("CHAT_TTS_ALLOW_DOWNLOAD", "").lower() in {"1", "true", "yes"}
    if not model_path.exists() and not allow_download:
        raise RuntimeError(
            "ChatTTS model is not available locally. "
            f"Set CHAT_TTS_MODEL_PATH to a downloaded ChatTTS model directory, "
            f"or place the model under {model_path}. "
            "Automatic model download is disabled because it is unstable in the Windows backend console."
        )

    requested_device = os.getenv("CHAT_TTS_DEVICE", "auto").strip().lower()
    if requested_device in {"", "auto"}:
        device_candidates = ["cuda", "cpu"] if torch.cuda.is_available() else ["cpu"]
    else:
        device_candidates = [requested_device]
        if requested_device != "cpu":
            device_candidates.append("cpu")

    load_errors: list[str] = []
    _chattts_load_errors = []
    chat = None
    loaded = False
    selected_device = "cpu"
    for device_name in device_candidates:
        chat = ChatTTS.Chat()
        device = torch.device(device_name)
        try:
            if model_path.exists():
                loaded = chat.load(source="custom", custom_path=str(model_path), compile=False, device=device)
            else:
                loaded = chat.load(source="huggingface", compile=False, device=device)
            if loaded is not False:
                selected_device = device_name
                break
        except Exception as exc:
            load_errors.append(f"{device_name}: {exc}")
            loaded = False
            try:
                chat.unload()
            except Exception:
                pass

    if loaded is False:
        raise RuntimeError(f"ChatTTS failed to load model from {model_path}. Tried devices: {', '.join(load_errors) or ', '.join(device_candidates)}")

    try:
        speaker = chat.sample_random_speaker()
        infer_kwargs = {
            "spk_emb": speaker,
            "temperature": 0.3,
            "top_P": 0.7,
            "top_K": 20,
            "max_new_token": int(os.getenv("CHAT_TTS_MAX_NEW_TOKEN", "1280")),
        }
        try:
            infer_params = ChatTTS.Chat.InferCodeParams(**infer_kwargs)
        except TypeError:
            infer_kwargs.pop("max_new_token", None)
            infer_params = ChatTTS.Chat.InferCodeParams(**infer_kwargs)
    except Exception:
        infer_params = None

    _chattts_engine = chat
    _chattts_infer_params = infer_params
    _chattts_device = selected_device
    _chattts_load_errors = load_errors
    if load_errors:
        print(f"ChatTTS device fallback details: {'; '.join(load_errors)}")
    print(f"ChatTTS loaded on device: {selected_device}")
    return _chattts_engine, _chattts_infer_params


def get_tts_diagnostics() -> dict[str, Any]:
    """Return TTS runtime diagnostics for troubleshooting device selection."""
    kokoro_repo_id = _get_kokoro_repo_id()
    kokoro_model_dir = _get_kokoro_model_dir(kokoro_repo_id)
    kokoro_model_path = Path(os.getenv("KOKORO_MODEL_PATH", "") or kokoro_model_dir / _get_kokoro_model_filename(kokoro_repo_id))
    kokoro_config_path = Path(os.getenv("KOKORO_CONFIG_PATH", "") or kokoro_model_dir / "config.json")
    kokoro_voice = os.getenv("KOKORO_VOICE", _KOKORO_DEFAULT_VOICE)
    kokoro_voice_path = Path(os.getenv("KOKORO_VOICE_PATH", "") or kokoro_model_dir / "voices" / f"{kokoro_voice}.pt")
    diagnostics: dict[str, Any] = {
        "default_provider": os.getenv("MOCK_INTERVIEW_TTS_PROVIDER", "minimax"),
        "minimax_tts_api_key_configured": bool(_get_minimax_tts_api_key()),
        "minimax_tts_url": _get_minimax_tts_url(),
        "minimax_tts_model": os.getenv("MINIMAX_TTS_MODEL", "speech-2.8-turbo"),
        "minimax_tts_voice": _get_minimax_voice(),
        "minimax_tts_speed": float(os.getenv("MINIMAX_TTS_SPEED", "1.08")),
        "kokoro_loaded": _kokoro_pipeline is not None,
        "kokoro_load_error": _kokoro_load_error,
        "kokoro_lang_code": os.getenv("KOKORO_LANG_CODE", "z"),
        "kokoro_voice": kokoro_voice,
        "kokoro_repo_id": kokoro_repo_id,
        "kokoro_device_env": os.getenv("KOKORO_DEVICE", "auto"),
        "kokoro_model_dir": str(kokoro_model_dir),
        "kokoro_config_path": str(kokoro_config_path),
        "kokoro_model_path": str(kokoro_model_path),
        "kokoro_voice_path": str(kokoro_voice_path),
        "kokoro_config_exists": kokoro_config_path.exists(),
        "kokoro_model_exists": kokoro_model_path.exists(),
        "kokoro_voice_exists": kokoro_voice_path.exists(),
        "chattts_loaded_device": _chattts_device or None,
        "chattts_load_errors": list(_chattts_load_errors),
        "chattts_device_env": os.getenv("CHAT_TTS_DEVICE", "auto"),
        "chattts_model_path": os.getenv("CHAT_TTS_MODEL_PATH", str(DATA_FOLDER / "models" / "ChatTTS")),
    }
    try:
        import torch

        diagnostics.update({
            "torch_installed": True,
            "torch_version": getattr(torch, "__version__", ""),
            "torch_cuda_available": bool(torch.cuda.is_available()),
            "torch_cuda_version": getattr(torch.version, "cuda", None),
            "torch_device_count": int(torch.cuda.device_count()),
            "torch_devices": [
                torch.cuda.get_device_name(i)
                for i in range(torch.cuda.device_count())
            ] if torch.cuda.is_available() else [],
        })
    except Exception as exc:
        diagnostics.update({
            "torch_installed": False,
            "torch_error": str(exc),
        })
    return diagnostics


def _synthesize_chattts_speech(text: str) -> bytes:
    chat, infer_params = _get_chattts_engine()
    params = infer_params
    if infer_params is not None:
        try:
            import ChatTTS

            base_tokens = int(os.getenv("CHAT_TTS_MAX_NEW_TOKEN", "1280"))
            dynamic_tokens = min(2048, max(base_tokens, len(text) * 8))
            params = ChatTTS.Chat.InferCodeParams(
                spk_emb=getattr(infer_params, "spk_emb", None),
                temperature=getattr(infer_params, "temperature", 0.3),
                top_P=getattr(infer_params, "top_P", 0.7),
                top_K=getattr(infer_params, "top_K", 20),
                max_new_token=dynamic_tokens,
            )
        except Exception:
            params = infer_params
    kwargs = {"params_infer_code": params} if params is not None else {}
    wavs = chat.infer([text], **kwargs)
    if not wavs:
        raise RuntimeError("ChatTTS returned empty audio")
    return _float_audio_to_wav_bytes(wavs[0], sample_rate=24000)


def end_mock_interview(session_id: str, history: list[dict]) -> dict[str, Any]:
    """End a mock interview and generate evaluation. Returns {evaluation, file_path, status}."""
    from src.libs.interview_prep import MockInterviewSession
    from src.libs.interview_prep.mock_interview import InterviewMessage, InterviewRound

    if not session_id or session_id not in _sessions:
        return {"evaluation": "❌ 没有进行中的面试", "file_path": "", "status": "error"}

    stored = _sessions[session_id]
    interviewer = stored["interviewer"]
    config = stored["config"]

    # Restore session
    session = MockInterviewSession(
        session_id=session_id,
        candidate=interviewer.sessions[session_id].candidate,
        company=interviewer.sessions[session_id].company,
        job=interviewer.sessions[session_id].job,
        interview_type=config["interview_type"],
        style=interviewer.sessions[session_id].style,
    )
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user" and content:
            session.messages.append(InterviewMessage(role="candidate", content=content, timestamp=time.time(), round=InterviewRound.OPENING))
        elif role == "assistant" and content:
            session.messages.append(InterviewMessage(role="interviewer", content=content, timestamp=time.time(), round=InterviewRound.OPENING))
    interviewer.sessions[session_id] = session

    evaluation = interviewer.end_session(session_id)

    # Save report
    output_dir = OUTPUT_FOLDER / "mock_interview"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"interview_eval_{timestamp}.md"
    pdf_path = output_dir / f"interview_eval_{timestamp}.pdf"

    full_report = f"""# 模拟面试评估报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**岗位**: {config.get("job_title", "")}
**公司**: {config.get("company_name", "")}

---

## 面试对话记录

"""
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user" and content:
            full_report += f"**候选人**: {content}\n\n"
        elif role == "assistant" and content:
            full_report += f"**面试官**: {content}\n\n"

    full_report += f"---\n\n## 评估报告\n\n{evaluation}"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_report)
    _write_mock_interview_pdf(full_report, pdf_path)

    # Cleanup
    del _sessions[session_id]

    return {
        "evaluation": evaluation,
        "file_path": str(output_path),
        "pdf_path": str(pdf_path),
        "pdf_filename": pdf_path.name,
        "status": "success",
    }
