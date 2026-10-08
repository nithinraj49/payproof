"""Tests for the Cloud Run fail-fast config check (backend/config.py).
All environment variables are mocked; no network calls, no real .env read."""
import pytest

from backend.config import get_settings


def _clear_relevant_env(monkeypatch):
    for name in ["K_SERVICE", "GEMINI_BACKEND", "PROJECT_ID", "VERTEX_LOCATION"]:
        monkeypatch.delenv(name, raising=False)


def test_local_dev_defaults_to_aistudio_without_error(monkeypatch):
    _clear_relevant_env(monkeypatch)
    # No K_SERVICE: this is local/dev, the aistudio default must not raise.
    settings = get_settings()
    assert settings.gemini_backend == "aistudio"


def test_cloud_run_with_valid_vertex_config_succeeds(monkeypatch):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("K_SERVICE", "payproof")
    monkeypatch.setenv("GEMINI_BACKEND", "vertex")
    monkeypatch.setenv("PROJECT_ID", "payproof-nithin-2026")
    monkeypatch.setenv("VERTEX_LOCATION", "global")
    settings = get_settings()
    assert settings.gemini_backend == "vertex"


def test_cloud_run_refuses_to_start_with_aistudio_backend(monkeypatch):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("K_SERVICE", "payproof")
    monkeypatch.setenv("GEMINI_BACKEND", "aistudio")
    monkeypatch.setenv("PROJECT_ID", "payproof-nithin-2026")
    monkeypatch.setenv("VERTEX_LOCATION", "global")
    with pytest.raises(RuntimeError, match="GEMINI_BACKEND"):
        get_settings()


def test_cloud_run_refuses_to_start_without_project_id(monkeypatch):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("K_SERVICE", "payproof")
    monkeypatch.setenv("GEMINI_BACKEND", "vertex")
    monkeypatch.setenv("PROJECT_ID", "")
    monkeypatch.setenv("VERTEX_LOCATION", "global")
    with pytest.raises(RuntimeError, match="PROJECT_ID"):
        get_settings()


def test_cloud_run_refuses_to_start_without_vertex_location(monkeypatch):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("K_SERVICE", "payproof")
    monkeypatch.setenv("GEMINI_BACKEND", "vertex")
    monkeypatch.setenv("PROJECT_ID", "payproof-nithin-2026")
    monkeypatch.setenv("VERTEX_LOCATION", "")
    with pytest.raises(RuntimeError, match="VERTEX_LOCATION"):
        get_settings()


def test_cloud_run_error_message_has_no_secret_values(monkeypatch):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("K_SERVICE", "payproof")
    monkeypatch.setenv("GEMINI_BACKEND", "aistudio")
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value-should-not-leak")
    monkeypatch.setenv("PROJECT_ID", "payproof-nithin-2026")
    monkeypatch.setenv("VERTEX_LOCATION", "global")
    with pytest.raises(RuntimeError) as exc_info:
        get_settings()
    assert "super-secret-value-should-not-leak" not in str(exc_info.value)
