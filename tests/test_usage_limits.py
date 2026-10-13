import pytest

from backend.errors import ApiError
from backend.usage_limits import _field_count, check_limits


def test_check_limits_allows_when_under_both():
    check_limits(user_count=5, global_count=100, user_limit=12, global_limit=400)  # no raise


def test_check_limits_blocks_at_user_limit():
    with pytest.raises(ApiError) as exc_info:
        check_limits(user_count=12, global_count=0, user_limit=12, global_limit=400)
    assert exc_info.value.status_code == 429
    assert exc_info.value.error_code == "daily_limit_reached"


def test_check_limits_blocks_at_global_limit_even_if_user_is_fine():
    with pytest.raises(ApiError) as exc_info:
        check_limits(user_count=0, global_count=400, user_limit=12, global_limit=400)
    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == "service_busy"


def test_check_limits_allows_one_below_limit():
    check_limits(user_count=11, global_count=399, user_limit=12, global_limit=400)  # no raise


class _RealisticFirestoreSnapshot:
    """Mimics the one surprising bit of real DocumentSnapshot behaviour that
    caused a live 500 (backend/usage_limits.py's own docstring/comment):
    .get(field_path) raises KeyError when the document exists but that
    field doesn't, unlike dict.get(). _field_count() must never call
    .get(field) -- only .to_dict() -- so this class doesn't even implement
    .get(), to prove that.
    """
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


def test_field_count_missing_field_on_existing_document():
    # The exact live bug: users/{uid}/usage/{today} exists (has
    # "extractions" from an earlier call) but has no "questions" field yet
    # -- the first /api/extract then /api/ask of the day.
    snap = _RealisticFirestoreSnapshot({"extractions": 1})
    assert _field_count(snap, "questions") == 0


def test_field_count_present_field():
    snap = _RealisticFirestoreSnapshot({"extractions": 3, "questions": 7})
    assert _field_count(snap, "questions") == 7


def test_field_count_document_does_not_exist():
    snap = _RealisticFirestoreSnapshot(None)
    assert _field_count(snap, "questions") == 0
