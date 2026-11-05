import stages


def test_faq_in_sop_answer_passes_through(llm):
    llm.push("faq", {"thought": "", "answer": "Botox is from £200.", "in_sop": True, "confidence": 0.9, "sop_gaps": []})
    rt = stages.run_faq([{"role": "user", "content": "How much is Botox?"}])
    assert rt["in_sop"] is True
    assert rt["answer"] == "Botox is from £200."


def test_faq_low_confidence_is_treated_as_out_of_sop(llm):
    llm.push("faq", {"answer": "Probably £50?", "in_sop": True, "confidence": 0.2})
    rt = stages.run_faq([{"role": "user", "content": "How much is a peel?"}])
    assert rt["in_sop"] is False
    assert rt["answer"] == stages.LOW_CONFIDENCE_ANSWER


def test_faq_confidence_at_threshold_is_accepted(llm):
    llm.push("faq", {"answer": "ok", "in_sop": True, "confidence": stages.CONFIDENCE_THRESHOLD})
    assert stages.run_faq([])["in_sop"] is True


def test_faq_missing_keys_get_safe_defaults(llm):
    llm.push("faq", {"answer": "hello"})
    rt = stages.run_faq([])
    assert rt["in_sop"] is False
    assert rt["confidence"] == 0.0
    assert rt["sop_gaps"] == []


def test_faq_non_numeric_confidence_does_not_crash(llm):
    llm.push("faq", {"answer": "hello", "in_sop": True, "confidence": "high"})
    rt = stages.run_faq([])
    assert rt["in_sop"] is False


def test_faq_parse_error_returns_handoff(llm):
    llm.push("faq", "I am not JSON")
    rt = stages.run_faq([])
    assert rt["in_sop"] is False
    assert "connect you" in rt["answer"]


def test_escalation_check_requires_real_boolean(llm):
    llm.push("escalation", {"should_escalate": "false"})
    rt = stages.run_escalation_check("hi", [])
    assert rt["should_escalate"] is False
    assert rt["reason"] == ""


def test_escalation_check_includes_latest_message(llm):
    llm.push("escalation", {"should_escalate": True, "reason": "complaint"})
    rt = stages.run_escalation_check("this is awful", [{"role": "user", "content": "this is awful"}])
    assert rt["should_escalate"] is True
    _, ms = llm.calls[-1]
    assert 'Latest message: "this is awful"' in ms[0]["content"]


def test_qualification_bad_types_are_normalised(llm):
    llm.push("qualify", {"response": "Q2?", "collected_data": "botox", "questions_asked": "two"})
    rt = stages.run_qualification([], {}, 1)
    assert rt["collected_data"] == {}
    assert rt["questions_asked"] == 1
    assert rt["complete"] is False
    assert rt["sop_gap"] is False


def test_summary_empty_reply_has_fallback(llm):
    llm.push("summary", "")
    assert stages.run_summary([], {}, False, "").startswith("Summary unavailable")


def test_fmt_history_labels_roles():
    hs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert stages._fmt_history(hs) == "Customer: hi\nAria: hello"
