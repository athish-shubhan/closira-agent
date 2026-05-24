# Prompt Design — Closira / Bloom Aesthetics Clinic
## Model & API

`gemini-3.5-flash` (Google Gemini) is used in place of OpenAI/Anthropic due to free 
tier availability. The prompt design, chaining logic, and escalation architecture are 
not model-specific and transfer directly to any chat completion API.

## System Prompt (Full)

The system has four distinct system prompts — one per stage. Here they are with commentary inline.

---

### Stage 1 — FAQ Answering

```
You are Aria, a warm and professional customer service assistant for Bloom Aesthetics Clinic.

Your ONLY source of knowledge is the clinic SOP below. Do not use any external knowledge or make up information.

<sop>
{sop_text}
</sop>

For every customer message, respond in this exact JSON format:
{
  "thought": "<reason through: what is the customer asking, is this in the SOP, what does the SOP say>",
  "answer": "<your warm, professional response to the customer>",
  "in_sop": <true if you can answer from the SOP, false otherwise>,
  "confidence": <float 0.0 to 1.0 — how confident you are this answer is grounded in the SOP>,
  "sop_gaps": ["<list any topics the customer asked about that aren't in the SOP>"]
}

Rules:
- If the question is not in the SOP, set in_sop=false and confidence below 0.4
- If in_sop is false, tell the customer you'll get someone from the team to help rather than guessing
- Never invent prices, procedures, medical advice, or policies not stated in the SOP
- Keep responses concise and warm — this is an SMB aesthetics clinic, not a hospital
- Do not output anything outside the JSON block
```

---

### Stage 2 — Lead Qualification

```
You are Aria, a customer service assistant for Bloom Aesthetics Clinic conducting a brief lead qualification.

Your goal is to ask 3 structured questions to better understand the customer. Ask one at a time.

Questions to cover (in order, if not already answered):
1. Which treatment are you most interested in — Botox, Fillers, or would you like to start with a free consultation?
2. Have you had any aesthetic treatments before, or would this be your first time?
3. When are you looking to come in — do you have a rough timeframe in mind?

Current collected data: {collected}
Questions asked so far: {asked}

Respond in JSON:
{
  "response": "<your message to the customer>",
  "collected_data": {key-value pairs collected this turn},
  "questions_asked": <total qualification questions asked including this one>,
  "complete": <true if all 3 answered>
}
```

---

### Stage 3 — Escalation Detection

```
You are a safety classifier for an AI customer service system at Bloom Aesthetics Clinic.

Analyse the latest customer message and conversation context. Determine if escalation to a human agent is needed.

Escalate when:
1. The customer expresses a complaint, frustration, or anger
2. Medical question or health condition mentioned
3. Pricing negotiation or discount request
4. Customer explicitly asks for a human
5. Offensive or distressing content

Respond in JSON:
{
  "should_escalate": true/false,
  "reason": "<brief reason or empty>",
  "severity": "high/medium/low/none",
  "handoff_message": "<warm message if escalating>"
}
```

---

### Stage 4 — Conversation Summary

```
You are producing a structured end-of-session summary for the Bloom Aesthetics Clinic customer support team.

Analyse the full conversation and produce a clean summary in this format:

CUSTOMER INTENT
KEY DETAILS COLLECTED
SOP GAPS IDENTIFIED
ESCALATION STATUS
RECOMMENDED NEXT ACTION
QUALIFICATION SUMMARY
```

---

## Design Decisions

### Why Prompt Chaining as the core pattern

The four stages map naturally to a chain — each stage's output informs the next. The FAQ answer feeds into whether we need to escalate, the qualification data feeds into the summary, and the summary is a synthesis of everything that came before. I went with Prompt Chaining over a single monolithic prompt because single-prompt approaches for multi-intent tasks tend to drift — the model loses track of earlier instructions as context grows (the Agentic Design Patterns book's Chapter 1 calls this "instruction neglect"). Breaking it into stages keeps each prompt laser-focused.

The chain structure:

```
Customer Input
    → Escalation Router (always runs first)
        ↓ no escalation
    → FAQ Stage (SOP-grounded answer)
        ↓ after first answer
    → Qualification Stage (3 structured questions)
        ↓ at session end
    → Summary Stage (Reflection over full history)
```

---

### Why LLM-based Routing for escalation (not rule-based)

I could've just done keyword matching ("angry", "complaint", "refund") but that's brittle and misses a lot — something like "this is just not good enough" reads as frustrated but contains none of the keywords. An LLM router can pick up on tone and context. This is the Routing pattern from Chapter 2 of the design patterns book — using the model itself as the decision-maker about which path to take.

The escalation classifier runs on every message before anything else, so it can catch issues even mid-qualification. It's a separate system prompt from the FAQ stage, which means it doesn't inherit any of the "be warm and helpful" persona — its job is just classification, and keeping it separate makes it cleaner.

---

### Hallucination Prevention

A few things working together here:

**SOP injection into system prompt**: The full SOP text is passed into the system prompt via an XML `<sop>` tag. This is Context Engineering — rather than relying on the model's training data, we explicitly build the informational environment before the model generates anything. XML tags help the model clearly delineate "this is my source of truth" from its instructions.

**Structured JSON output with `thought` field**: The ReAct-style `thought` field forces the model to explicitly reason about whether the question is in the SOP before committing to an answer. This is a lightweight form of chain-of-thought — the model checks its own reasoning before surfacing it to the user. Without this, models tend to answer confidently even when they're extrapolating.

**`in_sop` + `confidence` fields**: These are machine-readable signals. If `in_sop` is false or confidence drops below 0.4, the workflow knows to track it as an unanswered question. Two consecutive unanswered questions trigger escalation automatically — so even if the escalation classifier misses something, the SOP-miss counter catches it.

**Explicit "never invent" rules**: "Never invent prices, procedures, medical advice, or policies not stated in the SOP" is in the system prompt. Negative rules like this are generally less reliable than positive constraints, but they help as a belt-and-suspenders thing when combined with the above.

---

### Confidence-based Escalation

There are actually two escalation paths:

1. **Sentiment/tone-based**: The dedicated escalation classifier runs first on every message. It catches complaints, anger, medical questions, pricing negotiation.

2. **SOP-coverage-based**: If the FAQ stage returns `in_sop=false` twice in a row, the system escalates automatically with reason "Multiple out-of-SOP questions". This directly implements the SOP rule: *"Escalate if: > 2 unanswered questions"*.

The escalation classifier uses a separate API call rather than bundling it into the FAQ prompt. This is intentional — the FAQ prompt is in "be helpful" mode with an SMB persona, and I don't want that persona bleeding into a safety classification decision. The classifier has no persona, just a job.

All escalations get logged to `logs/escalations.jsonl` with timestamp, trigger message, reason, and conversation length. This gives the team visibility into what's falling through the cracks.

---

### Tone and Persona

The FAQ and Qualification prompts establish Aria as "warm and professional" — which is the right register for an SMB aesthetics clinic. Not clinical, not overly casual. The prompt explicitly says "this is an SMB aesthetics clinic, not a hospital" partly as a reminder to avoid medical-speak but also to help the model calibrate formality level.

The qualification questions are phrased conversationally ("do you have a rough timeframe in mind?") rather than like a form ("please specify your desired appointment date"). That matters for response rate — customers are more likely to answer casual questions than form-fill prompts.

The escalation handoff message is always warm: "Let me connect you with one of our team members who can help you better" rather than anything that sounds like a rejection or failure. The customer should feel cared for even when we can't help them directly.

---

### The Summary as Reflection

The summary stage is essentially the Reflection pattern (Chapter 4, Agentic Design Patterns). Rather than a Generator-Critic model (two separate agents), it's a single pass over the full conversation history with a structured output format. The model is explicitly asked to surface SOP gaps and qualification quality — it's evaluating the conversation rather than just transcribing it.

The structured format (fixed section headers) is deliberate: the output should be readable by a human team member in 30 seconds, and it should be consistent enough to be parsed programmatically if needed later.

---

### What I'd add with more time

- Actual few-shot examples in the FAQ prompt (3-5 examples of in-SOP vs out-of-SOP questions with correct JSON)
- A retry loop on JSON parse failures (right now it falls back to a safe default, but retrying with the malformed output as context would be cleaner)
- Confidence threshold tuning — 0.4 is a guess, it should be calibrated against real conversation data
- Streaming output so responses don't block on long API calls
