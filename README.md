# Closira AI Workflow - Bloom Aesthetics Clinic

A Python CLI that simulates a full customer support session for an SMB aesthetics clinic - FAQ answering, lead qualification, escalation detection, and a structured session summary at the end.

> **API note:** The assignment specifies OpenAI or Anthropic Claude. This implementation uses Google Gemini (`gemini-3.5-flash`) for free-tier access during development. The architecture is fully API-agnostic - all LLM calls go through a single `_call()` function in `stages.py`. Swapping to Claude is a ~5-line change; see [Switching to Claude](#switching-to-claude) below.

---

## Setup

```bash
git clone <repo>
cd closira-agent

pip install -r requirements.txt
```

Set your Gemini API key:

```bash
export GEMINI_API_KEY="your_key_here"
```

If you're on the free tier (20 req/day limit), you can pass multiple keys and the agent will rotate through them automatically:

```bash
export GEMINI_API_KEYS="key_one,key_two,key_three"
```

Then run:

```bash
python main.py
```

To run all automated tests:

```bash
python run_tests.py
```

---

## Usage

Type messages at the prompt. A few things worth knowing:

- Type `done` or `exit` to end the session - this triggers the conversation summary
- Type `status` at any point to see which stage you're in
- The AI is called Aria and operates only from the SOP defined in `sop_data.json`

---

## How It Works

Every message goes through this flow:

```
Customer Message
    → Escalation Classifier  (runs first, every time)
        ↓ not escalated
    → FAQ Stage              (SOP-grounded answer)
        ↓ after first answer
    → Lead Qualification     (3 questions, one at a time)
        ↓ on session end
    → Conversation Summary
```

### Stage 1 — FAQ

Answers from the SOP only. The model returns structured JSON with a `thought` field (chain-of-thought reasoning before committing to an answer), `in_sop` (boolean), `confidence` (0–1 float), and any `sop_gaps` identified. If confidence is below 0.4 or the question isn't in the SOP, Aria tells the customer she'll get someone from the team rather than guessing.

### Stage 2 — Lead Qualification

After the first successful FAQ answer, Aria asks three qualification questions one at a time: treatment interest, prior experience, and rough timeline. Responses are collected into a structured dict and surfaced in the final summary.

### Stage 3 — Escalation Detection

A separate LLM classifier that runs on every message before the FAQ stage. Triggers on: complaint or frustration, medical question, pricing negotiation, explicit request for a human, or 2+ questions the SOP couldn't answer. The classifier uses a different system prompt with no persona — deliberately, so the "warm and helpful" Aria persona can't bleed into a safety classification decision. Every escalation is logged to `logs/escalations.jsonl` with timestamp, trigger message, reason, and turn count.

### Stage 4 — Conversation Summary

Generated at session end. Covers customer intent, key details collected, SOP gaps identified, escalation status, and a recommended next action for the human team.

---

## Project Structure

```
closira-agent/
├── main.py                   # CLI entry point
├── agent.py                  # WorkflowAgent — ties the four stages together
├── stages.py                 # Stage logic: FAQ, escalation, qualification, summary
├── sop.py                    # Loads sop_data.json and formats it for prompts
├── logger.py                 # Writes escalation events to logs/escalations.jsonl
├── sop_data.json             # The SOP — edit this to change the business context
├── prompt_design.md          # System prompts and full design reasoning
├── requirements.txt
├── run_tests.py              # Automated test runner (7 scenarios)
├── logs/
│   └── escalations.jsonl     # Appended at runtime
└── test_transcripts/
    ├── 01_in_sop_question.md
    ├── 02_out_of_scope_escalation.md
    ├── 03_escalation_trigger.md
    ├── 04_lead_qualification.md
    └── 05_conversation_summary.md
```

---

## SOP

The SOP lives in `sop_data.json`. Change the business, services, or policies there and it flows through to all prompts automatically at runtime — no prompt edits required.

Current SOP covers:

- **Business:** Bloom Aesthetics Clinic
- **Services:** Botox (from £200), Fillers (from £250), Free Consultations
- **Hours:** Mon–Sat, 9am–7pm
- **Booking:** WhatsApp or website, 24hr cancellation policy
- **Escalation conditions:** complaints, medical questions, pricing negotiation, 2+ unanswered questions

---

## Switching to Claude

Replace the `_call()` function in `stages.py` with this:

```python
import anthropic

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def _call(system_prompt, messages):
    response = _client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system_prompt,
        messages=messages
    )
    return response.content[0].text
```

The `messages` format (`role` + `content`) is identical between Gemini and Claude, so no other changes are needed.

---

## Tradeoffs and Known Limitations

- **No streaming.** API calls block until the full response returns. Fine for a CLI demo; a production version would stream.
- **JSON parse failures fall back silently.** If the model returns malformed JSON, the agent uses a safe default rather than retrying. A better approach would be to retry with the bad output attached as context so the model can self-correct.
- **Confidence threshold is hardcoded at 0.4.** Works reasonably well for this SOP but should be calibrated against real conversation data.
- **No persistence.** Session state lives in the `WorkflowAgent` instance and is lost when the script exits.
- **Qualification triggers after the first FAQ answer.** Controlled by `QUALIFY_AFTER` in `agent.py` — bump it to allow more back-and-forth before qualification starts.
- **One model for all stages.** A production setup would use a lighter model for the escalation classifier since it runs on every single message.
