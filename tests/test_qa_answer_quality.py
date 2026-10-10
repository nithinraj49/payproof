"""Tests for the three answer-quality checks added after reading the Phase 4
grounding eval results: currency enforcement, glossary label discipline, and
refusals that must contain no figures (REQUIREMENTS.md section 7, backend/qa.py).

Pure-function tests need no Gemini client. The end-to-end tests use the same
fake Gemini client as tests/test_qa_ask_question.py -- no network calls.
"""
from types import SimpleNamespace

from backend import qa

# ---------------------------------------------------------------------------
# 1. Currency
# ---------------------------------------------------------------------------

INR_SUMMARY = {"get_summary": {"net_per_engaged_hour": 192.0, "currency": "INR"}}
NO_CURRENCY_TOOLS = {"get_summary": {"net_per_engaged_hour": 192.0}}  # defaults to INR


def test_currency_violation_flags_dollar_sign():
    assert qa._currency_violation("Your net pay was $192.00.", INR_SUMMARY) is not None


def test_currency_violation_allows_rupee_symbol():
    assert qa._currency_violation("Your net pay was ₹192.00.", INR_SUMMARY) is None


def test_currency_violation_defaults_to_inr_when_tool_omits_currency():
    assert qa._currency_violation("Your net pay was $192.00.", NO_CURRENCY_TOOLS) is not None
    assert qa._currency_violation("Your net pay was ₹192.00.", NO_CURRENCY_TOOLS) is None


def test_currency_violation_allows_plain_numbers_with_no_symbol_at_all():
    assert qa._currency_violation("Your net pay was 192.00 per hour.", INR_SUMMARY) is None


def test_verify_numbers_unaffected_by_currency_symbol_choice():
    # The number verifier itself only cares about the numeric value.
    result = qa.verify_numbers("Your net pay was $192.00.", INR_SUMMARY)
    assert result.ok is True  # grounding is fine; _currency_violation is the separate check that catches "$"


# ---------------------------------------------------------------------------
# 2. Label discipline -- modelled on grounding-eval questions #4 and #8
# ---------------------------------------------------------------------------

def test_label_violation_none_when_correct_label_used():
    tools = {"get_summary": {"deduction_share": 0.0588}}
    text = "About 5.88% of your gross pay went to deduction share."
    assert qa._label_violation(text, tools) is None


def test_label_violation_flags_deduction_share_called_net_earnings():
    # Modelled on #4: deduction_share's value stated under a different field's label.
    tools = {"get_summary": {"deduction_share": 0.0588, "net_earnings": 192.0}}
    text = "Your net earnings were 5.88% of your gross pay."
    violation = qa._label_violation(text, tools)
    assert violation is not None
    assert "deduction_share" in violation


def test_label_violation_flags_net_earnings_weekly_called_total_credited():
    # Modelled on #8: net_payout_weekly ("total credited") and net_earnings_weekly
    # ("net earnings") are different figures; using one's label for the other's
    # value is exactly the confusion the grounding eval flagged.
    tools = {"get_weekly": {"net_payout_weekly": 950.0, "net_earnings_weekly": 850.0}}
    text = "Your total credited this week was 850."
    violation = qa._label_violation(text, tools)
    assert violation is not None
    assert "net_earnings_weekly" in violation


def test_label_violation_none_when_total_credited_label_matches_its_own_field():
    tools = {"get_weekly": {"net_payout_weekly": 950.0, "net_earnings_weekly": 850.0}}
    text = "Your total credited this week was 950."
    assert qa._label_violation(text, tools) is None


def test_label_violation_none_with_no_label_words_at_all():
    tools = {"get_summary": {"net_earnings": 192.0}}
    assert qa._label_violation("It was 192.", tools) is None


# ---------------------------------------------------------------------------
# 3. A refusal must contain no figures -- modelled on #17
# ---------------------------------------------------------------------------

def test_refusal_contains_numbers_detects_declined_answer_with_a_figure():
    text = "I cannot advise you on that. Your net pay per engaged hour was 192.00."
    assert qa._refusal_contains_numbers(text) is True


def test_refusal_contains_numbers_false_for_a_clean_refusal():
    assert qa._refusal_contains_numbers("I cannot answer that question.") is False


def test_refusal_contains_numbers_false_for_a_normal_grounded_answer():
    assert qa._refusal_contains_numbers("Your net pay was 192.00 per hour.") is False


def test_strip_numeric_sentences_removes_only_the_sentence_with_a_number():
    text = "I cannot advise you on switching platforms. Your net pay per engaged hour was 192.00."
    stripped = qa._strip_numeric_sentences(text)
    assert "192" not in stripped
    assert "cannot advise" in stripped


# ---------------------------------------------------------------------------
# End-to-end through ask_question() with a fake Gemini client
# ---------------------------------------------------------------------------

def _usage(prompt=50, output=10, thinking=0):
    return SimpleNamespace(prompt_token_count=prompt, candidates_token_count=output, thoughts_token_count=thinking)


def _text_response(text):
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))], text=text, usage_metadata=_usage())


def _tool_call_response(tool_name):
    fc = SimpleNamespace(name=tool_name, args={})
    part = SimpleNamespace(function_call=fc)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))], text="", usage_metadata=_usage())


class FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)

    def generate_content(self, model, contents, config):
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


SUMMARY_TOOLS = {"get_summary": lambda: {"net_per_engaged_hour": 192.0, "currency": "INR"}}
WEEKLY_TOOLS = {"get_weekly": lambda: {"net_payout_weekly": 950.0, "net_earnings_weekly": 850.0, "currency": "INR"}}


def test_ask_question_retries_on_wrong_currency_then_succeeds():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_summary"),
        _text_response("Your net pay was $192.00 per engaged hour."),
        _tool_call_response("get_summary"),
        _text_response("Your net pay was ₹192.00 per engaged hour."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "rate?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is True
    assert "$" not in result.text
    assert "₹192" in result.text


def test_ask_question_wrong_currency_surviving_retry_is_refused():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_summary"),
        _text_response("Your net pay was $192.00 per engaged hour."),
        _tool_call_response("get_summary"),
        _text_response("Your net pay was $192.00 per engaged hour."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "rate?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is False
    assert result.text == qa._SAFE_CURRENCY_REFUSAL
    assert "$" not in result.text


def test_ask_question_retries_on_wrong_label_then_succeeds():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_weekly"),
        _text_response("Your total credited this week was 850."),  # wrong: 850 is net_earnings_weekly
        _tool_call_response("get_weekly"),
        _text_response("Your net earnings this week were 850."),  # corrected
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "total credited?", tool_registry=WEEKLY_TOOLS)
    assert result.verified is True
    assert "850" in result.text


def test_ask_question_wrong_label_surviving_retry_is_refused():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_weekly"),
        _text_response("Your total credited this week was 850."),
        _tool_call_response("get_weekly"),
        _text_response("Your total credited this week was 850."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "total credited?", tool_registry=WEEKLY_TOOLS)
    assert result.verified is False
    assert result.text == qa._SAFE_LABEL_REFUSAL


def test_ask_question_strips_numbers_from_a_refusal_that_survives_retry():
    # Modelled on #17: declines, then volunteers real, grounded numbers both times.
    client = SimpleSettingsClient = None
    from backend.config import get_settings
    client = FakeClient([
        _text_response("I cannot advise you on switching platforms."),
        _tool_call_response("get_summary"),
        _text_response("I cannot advise you on switching platforms. Your net pay per engaged hour was 192.00."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "should I switch?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is True
    assert "192" not in result.text
    assert "cannot advise" in result.text


def test_ask_question_clean_refusal_with_no_numbers_passes_immediately():
    from backend.config import get_settings
    client = FakeClient([_text_response("I cannot answer that question.")])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "what's the weather?", tool_registry={})
    assert result.verified is True
    assert result.text == "I cannot answer that question."


# ---------------------------------------------------------------------------
# Empty answer -- found in the Phase 4 revision-2 grounding eval (#14): a
# turn can end with a second function_call instead of final text, leaving
# response.text empty. An empty string trivially "verifies" (nothing to
# check), so this must be caught as its own violation, not silently accepted.
# ---------------------------------------------------------------------------

def test_answer_violations_flags_empty_text():
    assert qa._answer_violations("", {}) == [("empty", "empty answer")]
    assert qa._answer_violations("   ", {}) == [("empty", "empty answer")]


def test_ask_question_retries_on_empty_draft_then_succeeds():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_summary"),  # draft: tool called, but the final turn comes back with no text
        _text_response(""),
        _tool_call_response("get_summary"),  # retry: a normal, complete turn
        _text_response("Your net pay was ₹192.00 per engaged hour."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "rate?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is True
    assert "192" in result.text


def test_ask_question_empty_answer_surviving_retry_is_refused():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_summary"),
        _text_response(""),
        _tool_call_response("get_summary"),
        _text_response(""),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "rate?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is False
    assert result.text == qa._SAFE_EMPTY_REFUSAL
