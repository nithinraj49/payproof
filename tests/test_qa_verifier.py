"""Unit tests for backend/qa.py's number verifier (REQUIREMENTS.md section
7.2). Pure functions: a draft-answer string in, tool-output dicts in, a
verdict out. No Gemini client, no Firestore, no network calls anywhere here.
"""
from backend.qa import extract_numbers, verify_numbers

# A realistic tool_results dict, shaped like what _run_turn() would collect
# from calling get_summary (REQUIREMENTS.md's trip-mode worked example).
TOOL_RESULTS = {
    "get_summary": {
        "available": True,
        "mode": "trip",
        "gross_pay": 148.0,
        "platform_deductions": 20.0,
        "net_payout": 128.0,
        "worker_costs": 0.0,
        "net_earnings": 128.0,
        "engaged_hours": 0.6667,
        "net_per_engaged_hour": 192.0,
        "net_per_logged_in_hour": 85.33,
        "net_payout_per_km": 20.0,
        "deduction_share": 0.0588,
        "total_distance_km": 6.4,
        "trip_count": 2,
        "data_quality": [],
    }
}


# ---------------------------------------------------------------------------
# extract_numbers: pure extraction, no comparison against tool results
# ---------------------------------------------------------------------------

def test_extract_plain_numbers():
    nums = extract_numbers("You earned 128 rupees across 2 trips.")
    assert [n.value for n in nums] == [128.0, 2.0]
    assert all(not n.is_percentage for n in nums)


def test_extract_indian_digit_grouping():
    nums = extract_numbers("Your platform showed a total of 1,23,456 this month.")
    assert [n.value for n in nums] == [123456.0]


def test_extract_western_digit_grouping():
    nums = extract_numbers("That adds up to 1,234,567 over the year.")
    assert [n.value for n in nums] == [1234567.0]


def test_extract_percentage():
    nums = extract_numbers("Platform fees were about 5.88% of your gross pay.")
    assert len(nums) == 1
    assert nums[0].value == 5.88
    assert nums[0].is_percentage is True


def test_extract_decimal():
    nums = extract_numbers("Your rate was 85.33 per hour.")
    assert [n.value for n in nums] == [85.33]


def test_extract_range():
    nums = extract_numbers("Your net pay per engaged hour was between 192 and 195.")
    assert [n.value for n in nums] == [192.0, 195.0]


def test_extract_number_inside_word_is_ignored():
    # "trip192" and "24x7" should not yield a spurious 192, 24 or 7.
    nums = extract_numbers("See screen trip192 for details, support is 24x7.")
    assert nums == []


def test_extract_negative_number():
    nums = extract_numbers("Your pay per km dropped by -5.5 compared to last week.")
    assert [n.value for n in nums] == [-5.5]


def test_extract_currency_symbols():
    nums = extract_numbers("You earned ₹192.00 net, or Rs. 85.33 per hour.")
    assert [n.value for n in nums] == [192.00, 85.33]


def test_extract_numbers_written_as_words_are_ignored():
    nums = extract_numbers("You completed ten trips this week.")
    assert nums == []


# ---------------------------------------------------------------------------
# verify_numbers: passing cases
# ---------------------------------------------------------------------------

def test_verify_passes_when_every_number_matches_exactly():
    draft = "You made 2 trips, net earnings of 128, and 20 per km."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is True
    assert result.unverified == []


def test_verify_passes_with_rounding_to_two_decimals():
    # Tool reports net_per_logged_in_hour = 85.33 exactly; a draft that
    # rounds engaged_hours (0.6667) to "0.67" should still verify.
    draft = "You were engaged for about 0.67 hours, earning 85.33 per hour."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is True


def test_verify_passes_with_percentage_form_of_a_ratio():
    # deduction_share is stored as the ratio 0.0588; the draft states it as
    # a percentage -- REQUIREMENTS.md 7.2 explicitly requires this to pass.
    draft = "Platform fees took about 5.88% of your gross pay."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is True


def test_verify_passes_with_indian_digit_grouping_against_a_large_tool_value():
    tool_results = {"get_weekly": {"available": True, "total_credited": 123456.0}}
    draft = "Your total credited this week was 1,23,456."
    result = verify_numbers(draft, tool_results)
    assert result.ok is True


def test_verify_passes_with_a_range_fully_inside_tool_values():
    tool_results = {"get_summary": {"net_per_engaged_hour": 192.0, "net_per_logged_in_hour": 195.0}}
    draft = "Your net pay per hour ranged from 192 to 195 depending on how you count it."
    result = verify_numbers(draft, tool_results)
    assert result.ok is True


def test_verify_ignores_a_number_embedded_in_a_word():
    # "24x7" must not be treated as an unverified "24" or "7".
    draft = "Trip support is available 24x7, and you earned 128 net."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is True


def test_verify_ignores_numbers_written_as_words():
    draft = "You completed two trips and earned 128 net."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is True


def test_verify_passes_with_currency_symbol():
    draft = "You earned ₹128.00 net this period."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is True


def test_verify_passes_with_a_negative_number_matching_a_negative_tool_value():
    tool_results = {"get_changes": {"relative_change": -5.5}}
    draft = "Your pay per km changed by about -5.5%."
    result = verify_numbers(draft, tool_results)
    assert result.ok is True


# ---------------------------------------------------------------------------
# verify_numbers: failing cases
# ---------------------------------------------------------------------------

def test_verify_fails_on_a_number_no_tool_returned():
    draft = "You made 2 trips and earned 500 net."  # 500 is not in TOOL_RESULTS
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is False
    assert 500.0 in result.unverified


def test_verify_fails_when_rounding_is_too_far_off():
    draft = "Your rate was 85.50 per hour."  # tool says 85.33; off by 0.17
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is False
    assert 85.50 in result.unverified


def test_verify_fails_on_a_wrong_percentage():
    draft = "Platform fees were about 12% of your gross pay."  # tool ratio is 0.0588
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is False
    assert 12.0 in result.unverified


def test_verify_fails_when_a_range_endpoint_is_unsupported():
    tool_results = {"get_summary": {"net_per_engaged_hour": 192.0}}
    draft = "Your net pay per hour ranged from 192 to 195."  # 195 unsupported
    result = verify_numbers(draft, tool_results)
    assert result.ok is False
    assert 195.0 in result.unverified
    assert 192.0 not in result.unverified


def test_verify_fails_when_no_tool_was_called():
    # The model answered without calling any tool: nothing can be verified.
    draft = "You earned 128 net this period."
    result = verify_numbers(draft, {})
    assert result.ok is False
    assert 128.0 in result.unverified


def test_verify_fails_on_an_unsupported_negative_number():
    draft = "Your pay dropped by -42 compared to last week."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is False
    assert -42.0 in result.unverified


def test_verify_still_passes_when_unrelated_word_numbers_are_present_alongside_a_bad_number():
    # Confirms word-numbers never mask or get confused with a real failure.
    draft = "You completed ten trips, but somehow earned 999 net."
    result = verify_numbers(draft, TOOL_RESULTS)
    assert result.ok is False
    assert 999.0 in result.unverified
