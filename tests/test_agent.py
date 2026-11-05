import json

import pytest

import agent as agent_mod


def faq(answer="ok", in_sop=True, confidence=0.9):
    return {"thought": "", "answer": answer, "in_sop": in_sop, "confidence": confidence, "sop_gaps": []}


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    with pytest.raises(ValueError):
        agent_mod.WorkflowAgent()


def test_first_faq_answer_starts_qualification(agent, llm):
    llm.push("faq", faq("Botox is from £200."))
    rs, st = agent.process("How much is Botox?")
    assert st == "faq"
    assert rs.startswith("Botox is from £200.")
    assert "quick questions" in rs
    assert agent.st == "qualify"


def test_escalation_classifier_hands_off_and_logs(agent, llm, log_path):
    llm.push("escalation", {"should_escalate": True, "reason": "complaint", "handoff_message": "Passing you over."})
    rs, st = agent.process("My treatment looks terrible")
    assert (rs, st) == ("Passing you over.", "escalated")
    entry = json.loads(log_path.read_text().splitlines()[0])
    assert entry["reason"] == "complaint"
    assert entry["trigger_message"] == "My treatment looks terrible"

    # Once escalated, no more LLM calls are made.
    calls_before = len(llm.calls)
    rs, st = agent.process("Hello?")
    assert st == "escalated"
    assert len(llm.calls) == calls_before


def test_two_out_of_sop_questions_escalate(agent, llm, log_path):
    llm.push("faq", faq("I'll get someone to help.", in_sop=False, confidence=0.1))
    llm.push("faq", faq("I'll get someone to help.", in_sop=False, confidence=0.1))
    assert agent.process("Do you do HydraFacials?")[1] == "faq"
    rs, st = agent.process("What about laser hair removal?")
    assert st == "escalated"
    assert rs == agent_mod.UNANSWERED_HANDOFF
    assert agent.er == "Multiple out-of-SOP questions"
    assert len(log_path.read_text().splitlines()) == 1


def test_low_confidence_answers_count_towards_escalation(agent, llm):
    llm.push("faq", faq("Maybe?", in_sop=True, confidence=0.1))
    llm.push("faq", faq("Maybe?", in_sop=True, confidence=0.1))
    agent.process("q1")
    assert agent.process("q2")[1] == "escalated"


def test_sop_gap_during_qualification_counts(agent, llm):
    llm.push("faq", faq(in_sop=False, confidence=0.1))
    agent.process("Do you do HydraFacials?")
    agent.st = "qualify"
    llm.push("qualify", {"response": "Not sure", "collected_data": {}, "questions_asked": 0, "sop_gap": True})
    assert agent.process("Do you do peels?")[1] == "escalated"


def test_full_qualification_collects_data_and_returns_to_faq(agent, llm):
    llm.push("faq", faq("Fillers are from £250."))
    agent.process("I'm interested in fillers")
    replies = [
        {"response": "Which treatment?", "collected_data": {}, "questions_asked": 1, "complete": False},
        {"response": "Had treatments before?", "collected_data": {"treatment": "fillers"}, "questions_asked": 2},
        {"response": "When?", "collected_data": {"experience": "botox before"}, "questions_asked": 3},
        {"response": "Thanks!", "collected_data": {"timeline": "2 weeks"}, "questions_asked": 3, "complete": True},
    ]
    for rp in replies:
        llm.push("qualify", rp)
        assert agent.process("answer")[1] == "qualify"
    assert agent.qd == {"treatment": "fillers", "experience": "botox before", "timeline": "2 weeks"}
    assert agent.qa == 3
    assert agent.st == "faq"


def test_malformed_classifier_reply_does_not_crash(agent, llm):
    llm.push("escalation", "garbage")
    llm.push("faq", faq("Open 9-7."))
    assert agent.process("Hours?")[1] == "faq"


def test_summary_without_history(agent):
    assert agent.generate_summary() == "No conversation to summarise."


def test_summary_passes_state_to_model(agent, llm):
    llm.push("faq", faq("Open 9-7."))
    agent.process("Hours?")
    llm.push("summary", "CUSTOMER INTENT\nHours")
    assert agent.generate_summary() == "CUSTOMER INTENT\nHours"
    _, ms = llm.calls[-1]
    assert "Customer: Hours?" in ms[0]["content"]
    assert "Escalated: False" in ms[0]["content"]


def test_out_of_sop_answer_does_not_start_qualification(agent, llm):
    llm.push("faq", faq("We don't offer that, let me get the team.", in_sop=False, confidence=0.1))
    rs, st = agent.process("Do you do HydraFacials?")
    assert st == "faq"
    assert "quick questions" not in rs
    assert agent.st == "faq"

    # The next in-SOP answer is the first successful one, so qualification starts then.
    llm.push("faq", faq("We're open 9-7."))
    rs, _ = agent.process("What are your hours?")
    assert "quick questions" in rs
    assert agent.st == "qualify"
