import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from agent import WorkflowAgent

TESTS = [
    {
        "name": "Test 1 — In-SOP questions",
        "inputs": [
            "Hi, what does Botox cost?",
            "How do I book an appointment?",
            "What are your opening hours?",
        ],
        "end": True
    },
    {
    "name": "Test 2 — Out-of-scope auto-escalation",
    "inputs": [
        "Do you do HydraFacials?",
        "What about laser hair removal?",
    ],
    "end": False
    },
    {
        "name": "Test 3 — Angry sentiment escalation",
        "inputs": [
            "I came in last week and my treatment looks terrible, I'm really unhappy",
        ],
        "end": False
    },
    {
        "name": "Test 4 — Pricing negotiation escalation",
        "inputs": [
            "Hi, can you do Botox for £150? I've seen cheaper elsewhere",
        ],
        "end": False
    },
    {
        "name": "Test 5 — Full lead qualification",
        "inputs": [
            "Hi I'm interested in getting fillers",
            "Sure go ahead",
            "Cheek fillers mainly",
            "Yes I've had Botox before at another clinic",
            "Probably within the next two weeks",
        ],
        "end": True
    },
    {
        "name": "Test 6 — Full session with SOP gap (main demo)",
        "inputs": [
            "What's the difference between Botox and fillers?",
            "Sure",
            "Free consultation first, I want to understand my options",
            "Never had anything done before",
            "Maybe in a couple of months",
            "Do you do HydraFacials?",
        ],
        "end": True
    },
    {
        "name": "Test 7 — Explicit human request",
        "inputs": [
            "Can I just speak to a real person please?",
        ],
        "end": False
    },
]

DIVIDER = "=" * 60
TURN_SLEEP = 14


def run_all():
    lg = []

    for ts in TESTS:
        print(f"\n{DIVIDER}")
        print(f"  {ts['name']}")
        print(DIVIDER)

        ag = WorkflowAgent()
        tl = {"test": ts["name"], "turns": [], "summary": None}

        for up in ts["inputs"]:
            print(f"\nYou: {up}")
            rs, st = ag.process(up)
            print(f"Aria [{st}]: {rs}")
            tl["turns"].append({"user": up, "aria": rs, "stage": st})
            time.sleep(TURN_SLEEP)

        if ts["end"]:
            print("\n--- SESSION SUMMARY ---")
            sm = ag.generate_summary()
            print(sm)
            tl["summary"] = sm

        lg.append(tl)

    print(f"\n{DIVIDER}")
    print("  All tests complete")
    print(DIVIDER)

    return lg

if __name__ == "__main__":
    run_all()
