"""End-to-end tests for backend/qa.py's ask_question() against a fake Gemini
client (REQUIREMENTS.md section 7, CLAUDE.md "tests use mocked Gemini
output"). No network calls; the fake client's generate_content() just pops
canned responses off a queue, shaped like the real google-genai SDK objects
that backend/qa.py's _run_turn() reads from (response.candidates[0].content
.parts for function_call detection, response.text, response.usage_metadata).

Confirms the live smoke test's four behaviours (eval/qa_smoke_test.py,
REQUIREMENTS.md section 7.3) are enforced by our own code -- not just
something the model happened to do once -- plus the policy backstop for an
accusation/advice draft that contains no numbers at all (so the number
verifier alone would have nothing to catch).
"""
from types import SimpleNamespace

from backend import qa


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
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


SUMMARY_TOOLS = {"get_summary": lambda: {"net_per_engaged_hour": 192.0}}


def test_grounded_answer_with_one_tool_call_turn(settings=None):
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_summary"),
        _text_response("Your net pay was 192.0 per engaged hour."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "What is my rate?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is True
    assert result.raw_calls == 2
    assert "192" in result.text


def test_direct_answer_with_no_tool_call_when_nothing_to_look_up():
    from backend.config import get_settings
    client = FakeClient([_text_response("I can't answer that without your confirmed costs.")])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "off-topic?", tool_registry={})
    assert result.verified is True  # no numbers claimed, nothing to verify
    assert result.raw_calls == 1


def test_unverified_number_triggers_retry_then_succeeds():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_summary"),
        _text_response("Your net pay was 500 per engaged hour."),  # wrong: tool says 192.0
        _tool_call_response("get_summary"),
        _text_response("Your net pay was 192.0 per engaged hour."),  # corrected
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "What is my rate?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is True
    assert result.raw_calls == 4
    assert "192" in result.text
    assert "500" not in result.text


def test_unverified_number_still_wrong_after_retry_is_refused():
    from backend.config import get_settings
    client = FakeClient([
        _tool_call_response("get_summary"),
        _text_response("Your net pay was 500 per engaged hour."),
        _tool_call_response("get_summary"),
        _text_response("Your net pay was 777 per engaged hour."),  # still wrong
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "What is my rate?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is False
    assert "777" in result.text
    assert "500" not in result.text  # the first (discarded) draft is never shown


def test_accusation_with_no_numbers_triggers_retry_even_though_nothing_to_verify():
    # The number verifier alone has nothing to flag here (no digits at all);
    # the content-policy backstop must still force a retry.
    from backend.config import get_settings
    client = FakeClient([
        _text_response("This platform is committing fraud against you."),
        _text_response("I can't say whether a platform has done anything wrong."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "Is my platform cheating me?", tool_registry={})
    assert result.verified is True
    assert "fraud" not in result.text.lower()


def test_accusation_surviving_retry_is_replaced_with_the_safe_refusal():
    from backend.config import get_settings
    client = FakeClient([
        _text_response("This looks like fraud."),
        _text_response("I'm confident this is fraud, you earned 192.0 per hour."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "Is my platform cheating me?", tool_registry=SUMMARY_TOOLS)
    assert result.verified is False
    assert result.text == qa._SAFE_POLICY_REFUSAL
    assert "fraud" not in result.text.lower()


def test_financial_advice_with_no_numbers_triggers_retry():
    from backend.config import get_settings
    client = FakeClient([
        _text_response("You should get financial advice and invest your tips."),
        _text_response("I can only explain your own pay numbers."),
    ])
    result = qa.ask_question(client, get_settings(), "gemini-3.1-flash-lite", "uid1", "What should I do with my tips?", tool_registry={})
    assert result.verified is True
    assert "advice" not in result.text.lower()


# ---------------------------------------------------------------------------
# _content_policy_violation: pure function, direct tests
# ---------------------------------------------------------------------------

def test_content_policy_flags_accusation_word():
    assert qa._content_policy_violation("This platform is committing fraud.") is not None


def test_content_policy_flags_advice_phrase():
    assert qa._content_policy_violation("You should get financial advice.") is not None


def test_content_policy_allows_clean_grounded_text():
    assert qa._content_policy_violation("Your net pay was 192.0 per engaged hour.") is None
