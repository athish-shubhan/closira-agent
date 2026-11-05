import sys

from agent import WorkflowAgent

HEADER = """
╔══════════════════════════════════════════════╗
║     Bloom Aesthetics Clinic — Aria AI        ║
║     Powered by Closira Customer Platform     ║
╚══════════════════════════════════════════════╝

Type your message and press Enter.
Type 'done' or 'exit' to end the session and see the summary.
Type 'status' to see the current stage.
─────────────────────────────────────────────
"""

STAGE_LABELS = {
    "faq":       "FAQ Mode",
    "qualify":   "Lead Qualification",
    "escalated": "Escalated to Human"
}


def run():
    print(HEADER)

    try:
        ag = WorkflowAgent()
    except ValueError as er:
        print(f"[ERROR] {er}")
        sys.exit(1)

    cs = "faq"

    while True:
        try:
            up = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            up = "exit"

        if not up:
            continue

        if up.lower() in ("exit", "done", "bye", "goodbye", "quit"):
            print("\n─────────────────────────────────────────────")
            print("Generating session summary...\n")
            try:
                sm = ag.generate_summary()
            except Exception as er:  # noqa: BLE001 - keep the CLI alive on any API failure
                sm = f"[Summary unavailable: {er}]"
            print("SESSION SUMMARY")
            print("─────────────────────────────────────────────")
            print(sm)
            print("─────────────────────────────────────────────")
            print("Session ended. Thank you.\n")
            break

        if up.lower() == "status":
            print(f"[Stage: {STAGE_LABELS.get(cs, cs)}]\n")
            continue

        try:
            rs, cs = ag.process(up)
        except Exception as er:  # noqa: BLE001 - one failed API call should not end the session
            ag.discard_last_message()
            print(f"\n[ERROR] Couldn't reach the AI service ({er}). Please try that message again.\n")
            continue
        print(f"\nAria: {rs}\n")

        if cs == "escalated":
            print("[System: Escalation logged. Session handed to human team.]\n")


if __name__ == "__main__":
    run()
