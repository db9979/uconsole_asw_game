"""The optional language-model client: non-blocking, bounded, key-safe."""

import os
import stat

import pytest

from src.llm import client, keystore
from src.llm.client import LlmConfig, LlmService
from tests.llm_fake import FakeLlmServer


def _service(url, **kw):
    return LlmService(LlmConfig(enabled=True, base_url=url, model="m", **kw), timeout_s=5)


def test_off_by_default_submits_nothing():
    service = LlmService()
    assert not service.active
    assert service.submit("x", [{"role": "user", "content": "hi"}]) is None


def test_answer_is_cleaned_and_bounded():
    reply = "<think>secret plan</think>**Hallo** `Welt`\n\n\n\n## Ende\x07"
    with FakeLlmServer(reply) as server:
        service = _service(server.url, api_key="sk-test-123456")
        request = service.submit("radio", [{"role": "user", "content": "hi"}])
        assert request is not None and request.wait(5)
        assert request.ok
        assert request.text == "Hallo Welt\n\nEnde"
        assert server.requests[0]["model"] == "m"
        assert server.headers[0]["Authorization"] == "Bearer sk-test-123456"
        assert service.answered == 1 and service.last_error is None


def test_thinking_is_switched_off_and_a_refusal_drops_the_switch():
    with FakeLlmServer(lambda body: 400 if "chat_template_kwargs" in body else "OK") as server:
        service = _service(server.url)
        for _ in range(2):
            request = service.submit("p", [{"role": "user", "content": "q"}])
            assert request.wait(5) and request.ok and request.text == "OK"
        assert server.requests[0]["chat_template_kwargs"] == {"enable_thinking": False}
        # Refused once, then the server is asked without the switch.
        assert ["chat_template_kwargs" in body for body in server.requests] == [True, False, False]


def test_content_parts_and_reasoning_only_answers():
    parts = {"role": "assistant", "content": [{"type": "text", "text": "Ver"},
                                              {"type": "text", "text": "standen"}]}
    with FakeLlmServer(parts) as server:
        request = _service(server.url).submit("p", [{"role": "user", "content": "q"}])
        assert request.wait(5) and request.text == "Verstanden"
    for message in ({"role": "assistant", "content": None, "reasoning_content": "Hmm, let me"},
                    {"role": "assistant", "content": "<think>Hmm, the user wants"}):
        with FakeLlmServer(message) as server:
            request = _service(server.url).submit("p", [{"role": "user", "content": "q"}])
            request.wait(5)
            assert request.status == "failed" and request.error == "thinking"


def test_errors_are_categories_never_raw_text():
    with FakeLlmServer("x", status=401) as server:
        request = _service(server.url).submit("p", [{"role": "user", "content": "q"}])
        request.wait(5)
        assert request.status == "failed" and request.error == "auth"
    service = _service("http://127.0.0.1:9/v1")
    request = service.submit("p", [{"role": "user", "content": "q"}])
    request.wait(10)
    assert request.error in ("network", "timeout")


def test_queue_is_bounded():
    with FakeLlmServer("ok", delay_s=0.5) as server:
        service = LlmService(LlmConfig(True, server.url, "m"), queue_max=2)
        made = [service.submit("p", [{"role": "user", "content": str(i)}]) for i in range(8)]
        assert any(r is None for r in made)
        service.close()


def test_config_repr_hides_key():
    assert "sk-secret" not in repr(LlmConfig(True, "http://h/v1", "m", "sk-secret"))


@pytest.mark.parametrize("url,ok", [
    ("http://localhost:11434/v1", True), ("https://api.example.com/v1", True),
    ("ftp://x/v1", False), ("http://user:pw@h/v1", False), ("http://h/v1?x=1", False),
    ("", False), (" http://h/v1", False), ("http://h:99999/v1", False),
])
def test_url_validation(url, ok):
    assert client.valid_url(url) is ok


def test_parse_json_object_tolerates_wrapping():
    assert client.parse_json_object('Hier: ```json\n{"a": 1}\n```') == {"a": 1}
    assert client.parse_json_object("kein json") is None


def test_key_file_is_private(isolated_saves, monkeypatch):
    monkeypatch.delenv(keystore.ENV_NAME, raising=False)
    assert keystore.load_key() == ""
    assert keystore.save_key("  sk-abc123456789 ")
    assert keystore.load_key() == "sk-abc123456789"
    mode = stat.S_IMODE(os.stat(keystore.key_path()).st_mode)
    assert mode == 0o600
    monkeypatch.setenv(keystore.ENV_NAME, "env-key-value")
    assert keystore.load_key() == "env-key-value"
    monkeypatch.delenv(keystore.ENV_NAME)
    assert keystore.save_key("")
    assert not keystore.key_path().exists()
    assert keystore.mask("sk-abc123456789") == "...6789"
