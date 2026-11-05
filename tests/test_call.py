"""Tests for stages._call: key rotation, rate-limit retries and the request timeout."""
import socket
import threading
import time

import pytest
from google import genai
from google.genai import types

import stages


class RateLimit(Exception):
    def __init__(self, msg):
        super().__init__(msg)
        self.code = 429


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """Mimics genai.Client: client.models.generate_content(...) pops the next scripted outcome."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return FakeResponse(out)


@pytest.fixture
def clients(monkeypatch):
    sleeps = []
    monkeypatch.setattr(stages.time, "sleep", sleeps.append)
    monkeypatch.setattr(stages, "_ki", 0)

    def install(*scripts):
        cl = [FakeClient(sc) for sc in scripts]
        monkeypatch.setattr(stages, "_cp", cl)
        return cl, sleeps

    return install


MSG = [{"role": "user", "content": "hi"}]
PER_DAY = "429 RESOURCE_EXHAUSTED quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
PER_MIN = "429 RESOURCE_EXHAUSTED quotaId: GenerateRequestsPerMinute 'retryDelay': '7s'"


def test_returns_text_on_success(clients):
    cl, sleeps = clients(["hello"])
    assert stages._call("sys", MSG) == "hello"
    assert sleeps == []


def test_no_keys_gives_clear_error(monkeypatch):
    monkeypatch.setattr(stages, "_cp", [])
    with pytest.raises(RuntimeError, match="No Gemini API key"):
        stages._call("sys", MSG)


def test_daily_quota_rotates_to_next_key(clients):
    cl, sleeps = clients([RateLimit(PER_DAY)], ["from key 2"])
    assert stages._call("sys", MSG) == "from key 2"
    assert stages._ki == 1
    assert sleeps == []


def test_all_keys_exhausted_raises(clients):
    clients([RateLimit(PER_DAY)], [RateLimit(PER_DAY)], [RateLimit(PER_DAY)])
    with pytest.raises(RuntimeError, match="All API keys exhausted"):
        stages._call("sys", MSG)


def test_per_minute_limit_waits_retry_delay_then_retries(clients):
    cl, sleeps = clients([RateLimit(PER_MIN), "ok"])
    assert stages._call("sys", MSG) == "ok"
    assert sleeps == [7 + 5]
    assert cl[0].calls == 2


def test_per_minute_limit_without_delay_uses_fallback(clients):
    _, sleeps = clients([RateLimit("429 RESOURCE_EXHAUSTED"), "ok"])
    stages._call("sys", MSG)
    assert sleeps == [stages._RT_FB]


def test_per_minute_limit_gives_up_after_max_attempts(clients):
    cl, sleeps = clients([RateLimit(PER_MIN)] * stages._RT_MAX)
    with pytest.raises(RateLimit):
        stages._call("sys", MSG)
    assert cl[0].calls == stages._RT_MAX
    assert len(sleeps) == stages._RT_MAX - 1


def test_other_errors_are_not_retried(clients):
    cl, sleeps = clients([ValueError("400 INVALID_ARGUMENT")])
    with pytest.raises(ValueError):
        stages._call("sys", MSG)
    assert cl[0].calls == 1 and sleeps == []


def test_history_roles_are_mapped_for_gemini():
    ct, cf = stages._fmt_contents("sys", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
    assert [c["role"] for c in ct] == ["user", "model"]
    assert cf.system_instruction == "sys"


def test_clients_are_built_with_a_timeout():
    assert stages.TIMEOUT_MS > 0


def test_timeout_option_stops_a_hung_request():
    """Real SDK against a local socket that accepts but never answers."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    conns = []
    threading.Thread(target=lambda: conns.append(srv.accept()), daemon=True).start()
    port = srv.getsockname()[1]

    client = genai.Client(
        api_key="test",
        http_options=types.HttpOptions(base_url=f"http://127.0.0.1:{port}", timeout=500),
    )
    start = time.monotonic()
    with pytest.raises(Exception) as ex:  # noqa: B017 - exact timeout class depends on the httpx version
        client.models.generate_content(model=stages.MN, contents="hi")
    assert "Timeout" in type(ex.value).__name__
    assert time.monotonic() - start < 10
    srv.close()
