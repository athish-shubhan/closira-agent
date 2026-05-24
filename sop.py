import json
import os

_pt = os.path.join(os.path.dirname(__file__), "sop_data.json")

with open(_pt) as fl:
    SOP = json.load(fl)

def get_sop_text():
    sv = SOP["services"]
    sc = "\n".join(
        f"  - {it['name']}: {it['price']} — {it['description']}"
        for it in sv
    )

    tx = f"""Business: {SOP['business']}
Hours: {SOP['hours']}
Services:
{sc}
Booking channels: {', '.join(SOP['booking']['channels'])}
Cancellation policy: {SOP['booking']['cancellation_policy']}
Additional info: {SOP['additional_info']}
Escalate to human if: {', '.join(SOP['escalation_conditions'])}"""

    return tx
