import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logger  # noqa: E402
import stages  # noqa: E402


class FakeLLM:
    """Stands in for stages._call: returns queued replies keyed by which system prompt was used."""

    def __init__(self):
        self.queues = {"faq": [], "escalation": [], "qualify": [], "summary": []}
        self.calls = []

    def push(self, stage, reply):
        self.queues[stage].append(reply if isinstance(reply, str) else json.dumps(reply))

    def __call__(self, sy, ms):
        if sy == stages.ESCALATION_SYS:
            stage = "escalation"
        elif sy == stages.SUMMARY_SYS:
            stage = "summary"
        elif sy.startswith("You are Aria, a customer service assistant"):
            stage = "qualify"
        else:
            stage = "faq"
        self.calls.append((stage, ms))
        queue = self.queues[stage]
        if stage == "escalation" and not queue:
            return json.dumps({"should_escalate": False, "reason": "", "severity": "none", "handoff_message": ""})
        assert queue, f"unexpected {stage} call"
        return queue.pop(0)


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(stages, "_call", fake)
    return fake


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "logs" / "escalations.jsonl"
    monkeypatch.setattr(logger, "LG_PATH", str(path))
    return path


@pytest.fixture
def agent(monkeypatch, llm, log_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from agent import WorkflowAgent

    return WorkflowAgent()
