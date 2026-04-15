"""Tests for mempalace.llm_client — LLMClient class."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from mempalace.llm_client import LLMCallError, LLMClient, LLMConfigError


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_client(api_key="sk-test", base_url="https://api.example.com/v1", model="test-model"):
    """Build an LLMClient from a mock MempalaceConfig."""
    mock_cfg = MagicMock()
    mock_cfg.llm_config = {"api_key": api_key, "base_url": base_url, "model": model}
    return LLMClient(config=mock_cfg)


def _make_openai_response(content: str):
    """Build a minimal fake openai ChatCompletion response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── LLMConfigError ────────────────────────────────────────────────────────


def test_llm_client_raises_config_error_when_no_api_key():
    mock_cfg = MagicMock()
    mock_cfg.llm_config = {}
    with pytest.raises(LLMConfigError, match="API key"):
        LLMClient(config=mock_cfg)


def test_llm_client_raises_config_error_empty_api_key():
    mock_cfg = MagicMock()
    mock_cfg.llm_config = {"api_key": "", "model": "m"}
    with pytest.raises(LLMConfigError):
        LLMClient(config=mock_cfg)


# ── ImportError when openai not installed ────────────────────────────────


def test_llm_client_chat_raises_import_error_when_openai_missing():
    client = _make_client()
    with patch.dict(sys.modules, {"openai": None}):
        with pytest.raises(ImportError, match="pip install mempalace\\[llm\\]"):
            client.chat([{"role": "user", "content": "hello"}])


# ── chat() — normal success ──────────────────────────────────────────────


def test_llm_client_chat_returns_content():
    client = _make_client()
    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value.chat.completions.create.return_value = (
        _make_openai_response('{"result": "ok"}')
    )
    with patch.dict(sys.modules, {"openai": mock_openai}):
        result = client.chat([{"role": "user", "content": "test"}])
    assert result == '{"result": "ok"}'


def test_llm_client_chat_passes_model_and_messages():
    client = _make_client(model="my-model")
    mock_openai = MagicMock()
    mock_create = mock_openai.OpenAI.return_value.chat.completions.create
    mock_create.return_value = _make_openai_response("response text")
    messages = [{"role": "user", "content": "hello"}]
    with patch.dict(sys.modules, {"openai": mock_openai}):
        client.chat(messages)
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["model"] == "my-model"
    assert call_kwargs.kwargs["messages"] == messages


# ── chat() — retry logic ─────────────────────────────────────────────────


def test_llm_client_chat_retries_on_exception():
    client = _make_client()
    mock_openai = MagicMock()
    mock_create = mock_openai.OpenAI.return_value.chat.completions.create
    # Fail twice, succeed on third attempt
    mock_create.side_effect = [
        Exception("timeout"),
        Exception("timeout"),
        _make_openai_response("final"),
    ]
    with patch.dict(sys.modules, {"openai": mock_openai}):
        with patch("mempalace.llm_client.time.sleep"):  # don't actually sleep
            result = client.chat([{"role": "user", "content": "hi"}])
    assert result == "final"
    assert mock_create.call_count == 3


def test_llm_client_chat_raises_llm_call_error_after_all_retries():
    client = _make_client()
    mock_openai = MagicMock()
    mock_create = mock_openai.OpenAI.return_value.chat.completions.create
    mock_create.side_effect = Exception("persistent error")
    with patch.dict(sys.modules, {"openai": mock_openai}):
        with patch("mempalace.llm_client.time.sleep"):
            with pytest.raises(LLMCallError, match="persistent error"):
                client.chat([{"role": "user", "content": "hi"}])
    # 3 attempts: 1 original + 2 retries
    assert mock_create.call_count == 3


# ── parse_json_response() ────────────────────────────────────────────────


def test_parse_json_response_plain_json():
    client = _make_client()
    data = client.parse_json_response('{"wing_name": "项目", "rooms": []}')
    assert data["wing_name"] == "项目"
    assert data["rooms"] == []


def test_parse_json_response_with_surrounding_text():
    client = _make_client()
    text = 'Sure, here is the result:\n{"key": "value"}\nThat\'s all.'
    data = client.parse_json_response(text)
    assert data["key"] == "value"


def test_parse_json_response_markdown_code_fence():
    client = _make_client()
    text = '```json\n{"wing_name": "测试项目", "rooms": []}\n```'
    data = client.parse_json_response(text)
    assert data["wing_name"] == "测试项目"


def test_parse_json_response_chinese_content():
    client = _make_client()
    payload = {
        "wing_name": "仿真平台",
        "rooms": [
            {"name": "核心模块", "description": "仿真核心", "keywords": ["仿真", "EXata"]}
        ],
    }
    data = client.parse_json_response(json.dumps(payload, ensure_ascii=False))
    assert data["wing_name"] == "仿真平台"
    assert data["rooms"][0]["name"] == "核心模块"


def test_parse_json_response_raises_on_garbage():
    client = _make_client()
    with pytest.raises(ValueError, match="Could not extract valid JSON"):
        client.parse_json_response("this is not json at all!!!")


def test_parse_json_response_raises_on_empty():
    client = _make_client()
    with pytest.raises(ValueError):
        client.parse_json_response("")


def test_parse_json_response_nested_braces():
    """Ensure nested objects are correctly parsed via direct json.loads."""
    client = _make_client()
    text = '{"a": {"b": {"c": 1}}}'
    data = client.parse_json_response(text)
    assert data["a"]["b"]["c"] == 1


def test_parse_json_response_strips_think_block_deepseek():
    """DeepSeek R1 style: <think ...>reasoning</think) before JSON."""
    client = _make_client()
    text = '<think\n让我分析一下目录结构...\n这是一个项目。\n</think)\n\n{"wing_name": "测试", "rooms": []}'
    data = client.parse_json_response(text)
    assert data["wing_name"] == "测试"
    assert data["rooms"] == []


def test_parse_json_response_strips_think_block_chatml():
    """ChatML style: <|im_start|>think...<|im_end|> before JSON."""
    client = _make_client()
    text = '<|im_start|>think\nreasoning here\n<|im_end|>\n{"key": "value"}'
    data = client.parse_json_response(text)
    assert data["key"] == "value"


def test_parse_json_response_think_block_with_braces():
    """Thinking block containing curly braces should not break JSON extraction."""
    client = _make_client()
    text = '<think\nI think the structure is {a: 1, b: 2}\n</think)\n{"wing_name": "项目", "rooms": []}'
    data = client.parse_json_response(text)
    assert data["wing_name"] == "项目"


def test_parse_json_response_no_think_block_unchanged():
    """Normal responses without think blocks should work as before."""
    client = _make_client()
    text = '{"wing_name": "项目", "rooms": []}'
    data = client.parse_json_response(text)
    assert data["wing_name"] == "项目"
