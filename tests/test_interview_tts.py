from pathlib import Path

from backend.services import interview_service


def test_request_api_key_takes_precedence_for_minimax_tts(monkeypatch):
    monkeypatch.setenv("MINIMAX_TTS_API_KEY", "server-key")

    assert interview_service._get_minimax_tts_api_key("request-key") == "request-key"


def test_request_api_key_validates_without_server_secret(monkeypatch):
    monkeypatch.delenv("MINIMAX_TTS_API_KEY", raising=False)
    monkeypatch.setattr(interview_service, "load_secrets", lambda: {})

    interview_service.validate_minimax_tts_config("request-key")


def test_public_tts_rejects_missing_request_key_even_with_server_key(monkeypatch):
    monkeypatch.setattr(interview_service, "PUBLIC_DEMO_MODE", True)
    monkeypatch.setenv("MINIMAX_TTS_API_KEY", "server-key")

    try:
        interview_service.validate_minimax_tts_config()
    except RuntimeError as exc:
        assert "your own MiniMax API key" in str(exc)
    else:
        raise AssertionError("Public TTS accepted a missing request API key")


def test_minimax_rate_is_not_added_to_default_speed(monkeypatch):
    monkeypatch.setenv("MINIMAX_TTS_SPEED", "1.08")

    assert interview_service._rate_to_minimax_speed("+8%") == 1.08
    assert interview_service._rate_to_minimax_speed("-20%") == 0.8


def test_minimax_rate_uses_environment_only_without_valid_request(monkeypatch):
    monkeypatch.setenv("MINIMAX_TTS_SPEED", "1.12")

    assert interview_service._rate_to_minimax_speed("") == 1.12


def test_kokoro_voice_list_is_discovered_from_local_files(monkeypatch, tmp_path: Path):
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / "zf_001.pt").touch()
    (voices_dir / "zm_009.pt").touch()
    monkeypatch.setattr(interview_service, "_get_kokoro_model_dir", lambda _repo: tmp_path)

    result = interview_service.get_mock_interview_tts_voices()

    assert result["kokoro"] == [
        {"id": "zf_001", "label": "女声 zf_001"},
        {"id": "zm_009", "label": "男声 zm_009"},
    ]
