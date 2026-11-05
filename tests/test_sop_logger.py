import json

import logger
import sop


def test_sop_text_includes_every_service_and_policy():
    tx = sop.get_sop_text()
    for sv in sop.SOP["services"]:
        assert sv["name"] in tx
        assert sv["price"] in tx
    assert sop.SOP["hours"] in tx
    assert sop.SOP["booking"]["cancellation_policy"] in tx


def test_logger_round_trip(log_path):
    assert logger.get_all_logs() == []
    logger.log_escalation("medical question", "Is it safe while pregnant?", 3)
    logger.log_escalation("complaint", "Bad result", 1)
    logs = logger.get_all_logs()
    assert [lg["reason"] for lg in logs] == ["medical question", "complaint"]
    assert logs[0]["conversation_turns"] == 3
    assert json.loads(log_path.read_text().splitlines()[1])["trigger_message"] == "Bad result"
