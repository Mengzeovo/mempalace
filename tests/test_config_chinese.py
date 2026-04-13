"""Tests for Chinese-related additions to mempalace.config."""

import json
import os
import tempfile

import pytest

from mempalace.config import (
    DEFAULT_EMBEDDING_MODEL,
    MAX_NAME_LENGTH,
    MempalaceConfig,
    sanitize_name,
)


# ── DEFAULT_EMBEDDING_MODEL ─────────────────────────────────────────────


def test_default_embedding_model_is_qwen():
    assert DEFAULT_EMBEDDING_MODEL == "Qwen/Qwen3-Embedding-4B"


# ── sanitize_name — Chinese names ───────────────────────────────────────


def test_sanitize_name_chinese_two_chars():
    assert sanitize_name("测试") == "测试"


def test_sanitize_name_chinese_room_name():
    assert sanitize_name("仿真平台") == "仿真平台"


def test_sanitize_name_chinese_with_spaces():
    assert sanitize_name("前端 组件") == "前端 组件"


def test_sanitize_name_chinese_mixed_english():
    assert sanitize_name("EXata仿真") == "EXata仿真"


def test_sanitize_name_chinese_wing_name():
    assert sanitize_name("记忆宫殿项目") == "记忆宫殿项目"


def test_sanitize_name_single_chinese_char():
    # Single character: matches first-char group with optional trailing group → valid
    result = sanitize_name("测")
    assert result == "测"


def test_sanitize_name_chinese_long_name():
    name = "中" * 64 + "文" * 64  # 128 chars exactly
    assert sanitize_name(name) == name


def test_sanitize_name_chinese_too_long():
    name = "中" * 129
    with pytest.raises(ValueError, match="exceeds maximum length"):
        sanitize_name(name)


# ── sanitize_name — existing English names still pass ────────────────────


def test_sanitize_name_english_still_works():
    assert sanitize_name("my_project") == "my_project"


def test_sanitize_name_english_with_dots():
    assert sanitize_name("v1.2.3") == "v1.2.3"


def test_sanitize_name_english_with_hyphen():
    assert sanitize_name("my-app") == "my-app"


# ── sanitize_name — security: path traversal still blocked ──────────────


def test_sanitize_name_blocks_double_dot():
    with pytest.raises(ValueError, match="invalid path characters"):
        sanitize_name("../etc/passwd")


def test_sanitize_name_blocks_forward_slash():
    with pytest.raises(ValueError, match="invalid path characters"):
        sanitize_name("a/b")


def test_sanitize_name_blocks_backslash():
    with pytest.raises(ValueError, match="invalid path characters"):
        sanitize_name("a\\b")


def test_sanitize_name_blocks_null_byte():
    with pytest.raises(ValueError, match="null bytes"):
        sanitize_name("abc\x00def")


def test_sanitize_name_blocks_empty():
    with pytest.raises(ValueError):
        sanitize_name("")


def test_sanitize_name_blocks_whitespace_only():
    with pytest.raises(ValueError):
        sanitize_name("   ")


# ── MempalaceConfig.llm_config ───────────────────────────────────────────


def test_llm_config_from_file(tmp_path):
    cfg_data = {
        "llm": {
            "api_key": "sk-test",
            "base_url": "https://api.example.com/v1",
            "model": "test-model",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(cfg_data), encoding="utf-8")
    cfg = MempalaceConfig(config_dir=str(tmp_path))
    llm = cfg.llm_config
    assert llm["api_key"] == "sk-test"
    assert llm["base_url"] == "https://api.example.com/v1"
    assert llm["model"] == "test-model"


def test_llm_config_empty_when_not_set(tmp_path):
    cfg = MempalaceConfig(config_dir=str(tmp_path))
    llm = cfg.llm_config
    assert isinstance(llm, dict)
    assert "api_key" not in llm


def test_llm_config_env_override(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"llm": {"api_key": "file-key", "model": "file-model"}}),
        encoding="utf-8",
    )
    os.environ["MEMPALACE_LLM_API_KEY"] = "env-key"
    os.environ["MEMPALACE_LLM_MODEL"] = "env-model"
    try:
        cfg = MempalaceConfig(config_dir=str(tmp_path))
        llm = cfg.llm_config
        assert llm["api_key"] == "env-key"
        assert llm["model"] == "env-model"
    finally:
        del os.environ["MEMPALACE_LLM_API_KEY"]
        del os.environ["MEMPALACE_LLM_MODEL"]


def test_llm_config_env_base_url_override(tmp_path):
    os.environ["MEMPALACE_LLM_BASE_URL"] = "https://env.example.com"
    try:
        cfg = MempalaceConfig(config_dir=str(tmp_path))
        assert cfg.llm_config["base_url"] == "https://env.example.com"
    finally:
        del os.environ["MEMPALACE_LLM_BASE_URL"]


def test_llm_config_does_not_mutate_file_config(tmp_path):
    """Ensure llm_config returns a copy, not a reference to _file_config."""
    cfg_data = {"llm": {"api_key": "original"}}
    (tmp_path / "config.json").write_text(json.dumps(cfg_data), encoding="utf-8")
    cfg = MempalaceConfig(config_dir=str(tmp_path))
    result = cfg.llm_config
    result["api_key"] = "mutated"
    assert cfg.llm_config["api_key"] == "original"
