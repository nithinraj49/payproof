import pytest

from backend.errors import ApiError
from backend.usage_limits import check_limits


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
