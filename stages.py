import json
import os
import re
import time

from google import genai
from google.genai import types

from sop import get_sop_text

# Per-request timeout for Gemini calls; without one a stalled connection hangs the CLI.
TIMEOUT_MS = int(os.environ.get("GEMINI_TIMEOUT_MS", "30000"))

_rw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
_kl = [k.strip() for k in _rw.split(",") if k.strip()]
_cp = [genai.Client(api_key=k, http_options=types.HttpOptions(timeout=TIMEOUT_MS)) for k in _kl]
_ki = 0
MN = "gemini-3.5-flash"

# FAQ answers below this self-reported confidence are not shown to the customer.
CONFIDENCE_THRESHOLD = 0.4
LOW_CONFIDENCE_ANSWER = (
    "I'm not completely sure about that one, so rather than guess "
    "I'll get someone from our team to help."
)

FAQ_SYS = """You are Aria, a warm and professional customer service assistant for Bloom Aesthetics Clinic.

Your ONLY source of knowledge is the clinic SOP below. Do not use any external knowledge or make up information.

<sop>
{sop}
</sop>

For every customer message, respond in this exact JSON format:
{{
  "thought": "<reason through: what is the customer asking, is this in the SOP, what does the SOP say>",
  "answer": "<your warm, professional response to the customer>",
  "in_sop": <true if you can answer from the SOP, false otherwise>,
  "confidence": <float 0.0 to 1.0 — how confident you are this answer is grounded in the SOP>,
  "sop_gaps": ["<list any topics the customer asked about that aren't in the SOP>"]
}}

Rules:
- If the question is not in the SOP, set in_sop=false and confidence below 0.4
- If in_sop is false, tell the customer you'll get someone from the team to help rather than guessing
- Never invent prices, procedures, medical advice, or policies not stated in the SOP
- Keep responses concise and warm — this is an SMB aesthetics clinic, not a hospital
- Do not output anything outside the JSON block"""

ESCALATION_SYS = """You are a safety classifier for an AI customer service system at Bloom Aesthetics Clinic.

Analyse the latest customer message and conversation context. Determine if escalation to a human agent is needed.

Escalation is required when:
1. The customer expresses a complaint, frustration, or anger
2. The customer asks a medical question or mentions a health condition
3. The customer is trying to negotiate prices or ask for discounts
4. The customer explicitly asks to speak to a human
5. The message contains offensive or distressing content

Respond in this exact JSON format:
{{
  "should_escalate": <true or false>,
  "reason": "<brief reason if escalating, empty string if not>",
  "severity": "<high, medium, low, or none>",
  "handoff_message": "<if escalating: warm message to give the customer explaining handoff>"
}}

Be conservative — only escalate when clearly warranted. Do not output anything outside the JSON block."""

QUALIFY_SYS = """You are Aria, a customer service assistant for Bloom Aesthetics Clinic conducting a brief lead qualification.

Your goal is to ask 3 structured questions to better understand the customer. Ask one at a time.

Your ONLY source of clinic facts is the SOP below. Never invent prices, hours, or policies.

<sop>
{sop}
</sop>

Questions to cover (in order, if not already answered by a direct response to that specific question):
1. Which treatment are you most interested in — Botox, Fillers, or would you like to start with a free consultation?
2. Have you had any aesthetic treatments before, or would this be your first time?
3. When are you looking to come in — do you have a rough timeframe in mind?

Important: Do not mark a question as already answered based on a passing mention in the customer's opening message. Only skip a question if the customer answered it directly in response to being asked. If unsure whether an answer covered a question, ask it anyway to avoid ambiguity.

If the customer asks a factual question about the clinic (hours, prices, booking, services), answer it accurately using the SOP above, then continue with the current unanswered qualification question in the same message.
Only increment questions_asked if you asked a qualification question in this response. If you only answered a factual question, keep questions_asked at its current value ({asked}).

Set sop_gap to true only when the customer asked a factual question about the clinic that you could not answer from the SOP (e.g. a service not listed, a policy not covered). Set it to false for all other turns, including normal qualification answers.

Current collected data:
{collected}

Questions asked so far: {asked}

Respond in this exact JSON format:
{{
  "response": "<your message to the customer>",
  "collected_data": {{<key-value pairs of data you collected in this turn>}},
  "questions_asked": <total qualification questions asked so far — do not increment unless you asked one in this response>,
  "complete": <true if all 3 questions answered, false otherwise>,
  "sop_gap": <true if the customer asked a factual clinic question you could not answer from the SOP, false otherwise>
}}

Do not output anything outside the JSON block."""

SUMMARY_SYS = """You are producing a structured end-of-session summary for the Bloom Aesthetics Clinic customer support team.

Analyse the full conversation and produce a clean summary in this exact format (plain text, not JSON):

CUSTOMER INTENT
[What the customer was trying to achieve or find out]

KEY DETAILS COLLECTED
[Bullet list of important customer info gathered]

SOP GAPS IDENTIFIED
[Any questions the customer asked that the SOP couldn't answer]

ESCALATION STATUS
[Whether the conversation was escalated, and if so, why]

RECOMMENDED NEXT ACTION
[What the team should do next]

QUALIFICATION SUMMARY
[Lead quality assessment based on responses]"""


def _fmt_contents(sy, ms):
    cf = types.GenerateContentConfig(system_instruction=sy)
    ct = []
    for it in ms:
        ro = "user" if it["role"] == "user" else "model"
        ct.append({"role": ro, "parts": [{"text": it["content"]}]})
    return ct, cf


_RT_MAX = 3
_RT_FB = 35


def _is_rate_limit(ex):
    return getattr(ex, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(ex)


def _call(sy, ms):
    """Send one request to Gemini and return the reply text.

    Rate limits are handled here: a daily-quota error rotates to the next API key,
    a per-minute error sleeps for the server's retryDelay and retries (up to
    _RT_MAX attempts). Any other error is raised to the caller.
    """
    global _ki
    if not _cp:
        raise RuntimeError("No Gemini API key configured (set GEMINI_API_KEY or GEMINI_API_KEYS).")
    ct, cf = _fmt_contents(sy, ms)
    pt = 0
    rk = 0
    while True:
        try:
            rs = _cp[_ki].models.generate_content(model=MN, contents=ct, config=cf)
            return rs.text
        except Exception as ex:
            xs = str(ex)
            if not _is_rate_limit(ex):
                raise
            if "PerDay" in xs:
                if rk >= len(_cp) - 1:
                    raise RuntimeError("All API keys exhausted daily quota.") from ex
                _ki = (_ki + 1) % len(_cp)
                rk += 1
                continue
            pt += 1
            if pt >= _RT_MAX:
                raise
            mt = re.search(r"retryDelay.*?(\d+)", xs)
            wt = int(mt.group(1)) + 5 if mt else _RT_FB
            time.sleep(wt)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse(tx):
    """Extract the JSON object from a model reply.

    Handles bare JSON, ```json fenced blocks and JSON wrapped in stray prose.
    Raises ValueError if no JSON object can be found.
    """
    if not isinstance(tx, str):
        raise ValueError("model returned no text")
    tx = tx.strip()
    mt = _FENCE.search(tx)
    if mt:
        tx = mt.group(1).strip()
    if not tx.startswith("{"):
        st, en = tx.find("{"), tx.rfind("}")
        if st == -1 or en <= st:
            raise ValueError("no JSON object in model reply")
        tx = tx[st:en + 1]
    rt = json.loads(tx)
    if not isinstance(rt, dict):
        raise ValueError("model reply is not a JSON object")
    return rt


def _with_defaults(tx, df):
    """Parse a reply and fill any missing keys from df; fall back to df entirely on parse failure."""
    try:
        rt = _parse(tx)
    except ValueError:
        return dict(df)
    return {**df, **rt}


def _as_float(vl, df=0.0):
    try:
        return float(vl)
    except (TypeError, ValueError):
        return df


def _as_int(vl, df):
    try:
        return int(vl)
    except (TypeError, ValueError):
        return df


def run_faq(hs):
    sy = FAQ_SYS.format(sop=get_sop_text())
    tx = _call(sy, hs)

    rt = _with_defaults(tx, {
        "thought": "Parse error",
        "answer": "I'm sorry, I had a technical issue. Let me connect you with our team.",
        "in_sop": False,
        "confidence": 0.0,
        "sop_gaps": []
    })
    rt["in_sop"] = rt["in_sop"] is True
    rt["confidence"] = _as_float(rt["confidence"])

    # Low-confidence answers are treated as out-of-SOP so Aria hands off instead of guessing.
    if rt["in_sop"] and rt["confidence"] < CONFIDENCE_THRESHOLD:
        rt["in_sop"] = False
        rt["answer"] = LOW_CONFIDENCE_ANSWER

    return rt


def run_escalation_check(up, hs):
    ms = [
        {
            "role": "user",
            "content": f"Latest message: \"{up}\"\n\nFull conversation so far:\n{_fmt_history(hs)}"
        }
    ]

    tx = _call(ESCALATION_SYS, ms)

    rt = _with_defaults(tx, {
        "should_escalate": False,
        "reason": "",
        "severity": "none",
        "handoff_message": ""
    })
    rt["should_escalate"] = rt["should_escalate"] is True
    return rt


def run_qualification(hs, qd, qa):
    sy = QUALIFY_SYS.format(
        sop=get_sop_text(),
        collected=json.dumps(qd, indent=2) if qd else "{}",
        asked=qa
    )

    tx = _call(sy, hs)

    rt = _with_defaults(tx, {
        "response": "Could you tell me a bit more about what you're looking for?",
        "collected_data": {},
        "questions_asked": qa,
        "complete": False,
        "sop_gap": False
    })
    if not isinstance(rt["collected_data"], dict):
        rt["collected_data"] = {}
    rt["questions_asked"] = _as_int(rt["questions_asked"], qa)
    rt["complete"] = rt["complete"] is True
    rt["sop_gap"] = rt["sop_gap"] is True
    return rt


def run_summary(hs, qd, es_flag, es_reason):
    cn = _fmt_history(hs)
    qd_tx = json.dumps(qd, indent=2) if qd else "None collected"

    ms = [
        {
            "role": "user",
            "content": f"""Full conversation:
{cn}

Qualification data collected:
{qd_tx}

Escalated: {es_flag}
Escalation reason: {es_reason if es_reason else 'N/A'}

Please produce the session summary."""
        }
    ]

    return _call(SUMMARY_SYS, ms) or "Summary unavailable: the model returned an empty response."


def _fmt_history(hs):
    ln = []
    for it in hs:
        ro = "Customer" if it["role"] == "user" else "Aria"
        ln.append(f"{ro}: {it['content']}")
    return "\n".join(ln)
