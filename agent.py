import os

from logger import log_escalation
from stages import run_escalation_check, run_faq, run_qualification, run_summary

QUALIFY_AFTER = 1
MAX_UNANSWERED = 2
UNANSWERED_HANDOFF = "There are a few things I'm not sure about — let me get someone from our team to help you properly."


class WorkflowAgent:
    def __init__(self):
        if not (os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY")):
            raise ValueError("Set GEMINI_API_KEY or GEMINI_API_KEYS (comma-separated) environment variable")

        self.hs = []
        self.qd = {}
        self.qa = 0
        self.uc = 0
        self.st = "faq"
        self.es = False
        self.er = ""
        self.ac = 0

    def _escalate_unanswered(self, up):
        """Hand off after MAX_UNANSWERED questions the SOP could not answer."""
        self.es = True
        self.er = "Multiple out-of-SOP questions"
        log_escalation(self.er, up, len(self.hs))
        self.hs.append({"role": "assistant", "content": UNANSWERED_HANDOFF})
        return UNANSWERED_HANDOFF, "escalated"

    def process(self, up):
        """Handle one customer message; returns (reply, stage) where stage is faq, qualify or escalated."""
        self.hs.append({"role": "user", "content": up})

        if self.es:
            rs = "You're connected with our team — they'll be with you shortly."
            self.hs.append({"role": "assistant", "content": rs})
            return rs, "escalated"

        ec = run_escalation_check(up, self.hs)

        if ec["should_escalate"]:
            self.es = True
            self.er = ec["reason"]
            log_escalation(ec["reason"], up, len(self.hs))
            rs = ec.get("handoff_message") or "Let me connect you with one of our team members who can help you better."
            self.hs.append({"role": "assistant", "content": rs})
            return rs, "escalated"

        if self.st == "qualify":
            rt = run_qualification(self.hs, self.qd, self.qa)
            self.qa = rt["questions_asked"]
            self.qd.update(rt.get("collected_data") or {})
            rs = rt["response"]

            if rt.get("sop_gap"):
                self.uc += 1

            if self.uc >= MAX_UNANSWERED:
                return self._escalate_unanswered(up)

            if rt.get("complete"):
                self.st = "faq"

            self.hs.append({"role": "assistant", "content": rs})
            return rs, "qualify"

        rt = run_faq(self.hs)

        if not rt["in_sop"]:
            self.uc += 1

        if self.uc >= MAX_UNANSWERED:
            return self._escalate_unanswered(up)

        ar = rt["answer"]
        # Only answers grounded in the SOP count towards starting qualification;
        # appending "can I ask you a few questions?" to a handoff message reads badly.
        if rt["in_sop"]:
            self.ac += 1

        if rt["in_sop"] and self.ac == QUALIFY_AFTER and self.st == "faq":
            self.st = "qualify"
            ar += "\n\nWhile I have you here — do you mind if I ask a couple of quick questions so we can help you better?"

        self.hs.append({"role": "assistant", "content": ar})
        return ar, "faq"

    def discard_last_message(self):
        """Drop a trailing customer message that never got a reply (e.g. the API call failed)."""
        if self.hs and self.hs[-1]["role"] == "user":
            self.hs.pop()

    def generate_summary(self):
        if not self.hs:
            return "No conversation to summarise."
        return run_summary(self.hs, self.qd, self.es, self.er)
