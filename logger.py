import json
import os
from datetime import datetime

LG_PATH = os.path.join(os.path.dirname(__file__), "logs", "escalations.jsonl")


def log_escalation(rn, ms, hs_len):
    os.makedirs(os.path.dirname(LG_PATH), exist_ok=True)

    en = {
        "timestamp": datetime.now().isoformat(),
        "reason": rn,
        "trigger_message": ms,
        "conversation_turns": hs_len
    }

    with open(LG_PATH, "a") as fl:
        fl.write(json.dumps(en) + "\n")


def get_all_logs():
    if not os.path.exists(LG_PATH):
        return []

    lg = []
    with open(LG_PATH) as fl:
        for ln in fl:
            ln = ln.strip()
            if ln:
                lg.append(json.loads(ln))
    return lg
