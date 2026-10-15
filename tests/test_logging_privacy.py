"""Application logs must contain no user id (privacy rule: logs hold only
status codes, endpoint names, outcomes, token counts, costs and counts)."""
import ast
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from backend.auth import require_user_id
from backend.main import app

client = TestClient(app)
UID = "uid-SECRET-1234567890"


def test_delete_endpoint_logs_do_not_contain_user_id(monkeypatch, caplog):
    import backend.main as main_module
    app.dependency_overrides[require_user_id] = lambda: UID
    monkeypatch.setattr(main_module, "delete_all", lambda uid: 3)
    try:
        with caplog.at_level(logging.DEBUG):
            response = client.delete("/api/data")
    finally:
        app.dependency_overrides.pop(require_user_id, None)
    assert response.status_code == 200
    assert response.json()["documents_removed"] == 3
    assert any("delete" in r.getMessage() for r in caplog.records), "expected a delete log line"
    for record in caplog.records:
        assert UID not in record.getMessage()
        assert UID not in str(record.args)


def test_no_logging_call_in_source_passes_a_user_identifier():
    """Static guard: no logger/logging call may reference uid, user_id, token or
    email variables, or a uid= / token= / email= format field."""
    banned_names = {"uid", "user_id", "id_token", "token", "email"}
    banned_text = ("uid=", "user_id=", "token=", "email=")
    offenders = []
    root = Path(__file__).resolve().parent.parent
    for pkg in ("backend", "engine", "extraction"):
        for path in (root / pkg).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in {"debug", "info", "warning", "error", "exception", "critical"}:
                    continue
                base = node.func.value
                if not (isinstance(base, ast.Name) and base.id in {"logger", "logging", "_gemini_call_logger"}):
                    continue
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and sub.id in banned_names:
                        offenders.append(f"{path.name}:{node.lineno} uses {sub.id}")
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and any(b in sub.value for b in banned_text):
                        offenders.append(f"{path.name}:{node.lineno} format contains an identifier field")
    assert offenders == []
