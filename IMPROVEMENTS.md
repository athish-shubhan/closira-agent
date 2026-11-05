# Improvements log

## Round 1 — 2026-11-05

### What changed
1. **Offline unit tests (`tests/`, 36 tests).** The Gemini call (`stages._call`) is swapped for a scripted fake, so the suite runs without an API key or network. It covers JSON parsing and fallbacks, the confidence threshold, the 2-unanswered escalation counter (FAQ and qualification stages), the qualification flow, escalation logging, and SOP formatting. Before this, the only tests were `run_tests.py`, which needs a live API key and asserts nothing.
2. **Bug: qualification started after an out-of-SOP answer.** `agent.py` counted every FAQ reply as an "answer", so a handoff reply ("let me get one of our team members...") got "do you mind if I ask a couple of quick questions?" appended to it. `test_transcripts/02_out_of_scope_escalation.md` shows this happening. Qualification now starts only after the first in-SOP answer, which is what the README says.
3. **Bug: the 0.4 confidence threshold wasn't enforced.** The README says low-confidence answers are not shown, but the code only checked `in_sop`. `run_faq` now treats `confidence < CONFIDENCE_THRESHOLD` (0.4) as out-of-SOP and swaps in a handoff reply.
4. **More robust JSON handling.** `_parse` now accepts JSON wrapped in prose or in a fence without a language tag, and rejects non-objects. Missing keys are filled with safe defaults and bad types are normalised, so a partial model reply can no longer raise `KeyError` in `agent.py`. An empty summary reply now returns a message instead of `None`.
5. **CI and hygiene.** A GitHub Actions workflow runs `ruff check .` and `pytest` on Python 3.10 and 3.12. Added `pyproject.toml` (ruff + pytest config), `requirements-dev.txt` and `.gitignore`. Stopped tracking `__pycache__/*.pyc` and `.DS_Store`. Repeated escalation code is now one `_escalate_unanswered` helper.
6. **README.** Replaced `git clone <repo>` with the real URL. Added a Testing section that separates the offline unit tests from the live scenario runner.

### Why it matters
The agent's own logic (routing, counters, fallbacks) can now be checked on every PR without spending API quota. The two bugs were cases where the code did something different from what the README described.

### How it was verified
```
$ pytest -q                      # Python 3.13, this branch
36 passed in 0.06s
$ ruff check .
All checks passed!
$ pytest -q                      # Python 3.10 venv
36 passed in 0.17s
$ git stash; pytest -q tests     # new tests against the original code
16 failed, 20 passed in 0.15s
```
I also checked the Quick start from a clean clone of this branch: a new venv, `pip install -r requirements.txt -r requirements-dev.txt`, then `pytest -q` (36 passed) and `ruff check .` (passed). Without a key, `python main.py` prints `[ERROR] Set GEMINI_API_KEY or GEMINI_API_KEYS ...` and exits.

**Not verified:** `python run_tests.py` and `python main.py` against the real Gemini API. No API key was available in this environment, so live model behaviour and the transcripts in `test_transcripts/` / `test_output.log` were not re-run. Those recordings predate fix 2, so transcript 02 still shows the old behaviour. The model name `gemini-3.5-flash` and the "20 req/day" free-tier limit in the README were left as they are.

### Files touched
`agent.py`, `stages.py`, `main.py`, `run_tests.py`, `README.md`, `tests/` (new), `.github/workflows/ci.yml` (new), `pyproject.toml` (new), `requirements-dev.txt` (new), `.gitignore` (new), `IMPROVEMENTS.md` (new); removed `__pycache__/*.pyc` and `.DS_Store` from git.
