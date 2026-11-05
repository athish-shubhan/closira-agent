"""The CLI loop keeps the session alive when an API call fails."""
import builtins

import pytest

import agent as agent_mod
import main


class FlakyAgent:
    def __init__(self):
        self.hs = []
        self.calls = 0

    def process(self, up):
        self.hs.append({"role": "user", "content": up})
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("network down")
        self.hs.append({"role": "assistant", "content": "ok"})
        return "Open 9-7.", "faq"

    discard_last_message = agent_mod.WorkflowAgent.discard_last_message

    def generate_summary(self):
        raise RuntimeError("All API keys exhausted daily quota.")


@pytest.fixture
def run_cli(monkeypatch, capsys):
    def run(inputs, ag):
        it = iter(inputs)
        monkeypatch.setattr(builtins, "input", lambda _prompt="": next(it))
        monkeypatch.setattr(main, "WorkflowAgent", lambda: ag)
        main.run()
        return capsys.readouterr().out

    return run


def test_failed_turn_is_reported_and_session_continues(run_cli):
    ag = FlakyAgent()
    out = run_cli(["hours?", "hours?", "done"], ag)
    assert "[ERROR] Couldn't reach the AI service (network down)" in out
    assert "Aria: Open 9-7." in out
    # The failed message was removed, so history has no duplicate customer turn.
    assert [m["role"] for m in ag.hs] == ["user", "assistant"]


def test_summary_failure_still_ends_cleanly(run_cli):
    out = run_cli(["done"], FlakyAgent())
    assert "[Summary unavailable: All API keys exhausted daily quota.]" in out
    assert "Session ended." in out


def test_missing_key_exits_with_error(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    with pytest.raises(SystemExit) as ex:
        main.run()
    assert ex.value.code == 1
    assert "Set GEMINI_API_KEY" in capsys.readouterr().out
