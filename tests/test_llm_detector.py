"""Tests for mempalace.llm_detector — extract_file_snippet, detect_rooms_llm."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from mempalace.llm_detector import (
    _build_directory_tree,
    detect_rooms_llm,
    extract_file_snippet,
)


# ── extract_file_snippet ─────────────────────────────────────────────────


def test_extract_file_snippet_python_returns_defs():
    content = """\
import os

# some module

def foo():
    pass

class Bar:
    def baz(self):
        pass

x = 1
"""
    snippet = extract_file_snippet(Path("module.py"), content)
    assert "def foo" in snippet
    assert "class Bar" in snippet
    assert "import os" not in snippet
    assert "x = 1" not in snippet


def test_extract_file_snippet_python_no_defs_falls_back_to_300():
    content = "x = 1\n" * 200
    snippet = extract_file_snippet(Path("script.py"), content)
    # No defs → falls back to first 300 chars
    assert len(snippet) <= 300


def test_extract_file_snippet_python_caps_at_20_symbols():
    lines = [f"def func_{i}():\n    pass\n" for i in range(30)]
    content = "\n".join(lines)
    snippet = extract_file_snippet(Path("big.py"), content)
    # Should only contain 20 def lines
    assert snippet.count("def func_") == 20


def test_extract_file_snippet_markdown_returns_first_300():
    content = "# Title\n" + "x" * 500
    snippet = extract_file_snippet(Path("README.md"), content)
    assert len(snippet) == 300
    assert snippet.startswith("# Title")


def test_extract_file_snippet_json_returns_first_300():
    content = json.dumps({"key": "value" * 100})
    snippet = extract_file_snippet(Path("config.json"), content)
    assert len(snippet) == 300


def test_extract_file_snippet_yaml_returns_first_300():
    content = "key: value\n" * 100
    snippet = extract_file_snippet(Path("settings.yaml"), content)
    assert len(snippet) == 300


def test_extract_file_snippet_csv_returns_first_300():
    content = "id,name,value\n" + "1,test,100\n" * 100
    snippet = extract_file_snippet(Path("data.csv"), content)
    assert len(snippet) == 300
    assert "id,name,value" in snippet


def test_extract_file_snippet_js_returns_class_defs():
    """JS files: only 'class ' lines are detected (not 'function ').
    This is consistent with the extract_file_snippet design which looks for
    Python-style 'def ' and 'class ' prefixes only.
    """
    content = """\
const x = 1;
function hello() {}
class World {
    method() {}
}
"""
    snippet = extract_file_snippet(Path("app.js"), content)
    # 'class ' is detected; 'function ' is not (not a Python-style def/class prefix)
    assert "class World" in snippet


def test_extract_file_snippet_go_returns_defs():
    content = """\
package main

import "fmt"

func main() {
    fmt.Println("hello")
}

type Server struct {}
"""
    snippet = extract_file_snippet(Path("main.go"), content)
    assert "func main" in snippet


def test_extract_file_snippet_unknown_ext_returns_first_300():
    content = "some content " * 50
    snippet = extract_file_snippet(Path("notes.xyz"), content)
    assert len(snippet) == 300


def test_extract_file_snippet_short_content_returned_fully():
    content = "tiny"
    snippet = extract_file_snippet(Path("small.txt"), content)
    assert snippet == "tiny"


# ── _build_directory_tree ────────────────────────────────────────────────


def test_build_directory_tree_shows_root(tmp_path):
    tree = _build_directory_tree(tmp_path)
    assert tmp_path.name in tree


def test_build_directory_tree_shows_files(tmp_path):
    (tmp_path / "README.md").write_text("hello")
    (tmp_path / "main.py").write_text("print('hi')")
    tree = _build_directory_tree(tmp_path)
    assert "README.md" in tree
    assert "main.py" in tree


def test_build_directory_tree_shows_subdirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("code")
    tree = _build_directory_tree(tmp_path)
    assert "src" in tree
    assert "app.py" in tree


def test_build_directory_tree_skips_git(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config")
    tree = _build_directory_tree(tmp_path)
    assert ".git" not in tree


def test_build_directory_tree_skips_node_modules(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir()
    tree = _build_directory_tree(tmp_path)
    assert "node_modules" not in tree


def test_build_directory_tree_skips_binary_files(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "script.py").write_text("code")
    tree = _build_directory_tree(tmp_path)
    assert "image.png" not in tree
    assert "script.py" in tree


def test_build_directory_tree_chinese_dirs(tmp_path):
    (tmp_path / "前端").mkdir()
    (tmp_path / "后端").mkdir()
    (tmp_path / "文档").mkdir()
    tree = _build_directory_tree(tmp_path)
    assert "前端" in tree
    assert "后端" in tree
    assert "文档" in tree


# ── detect_rooms_llm ─────────────────────────────────────────────────────

_CALL1_RESPONSE = json.dumps(
    {
        "wing_name": "仿真平台",
        "selected_files": ["README.md", "src/main.py"],
        "project_summary": "EXata 仿真平台项目",
    },
    ensure_ascii=False,
)

_CALL2_RESPONSE = json.dumps(
    {
        "wing_name": "仿真平台",
        "summaries": [
            {"file": "README.md", "summary": "项目说明文档"},
            {"file": "src/main.py", "summary": "主入口"},
        ],
        "rooms": [
            {
                "name": "核心模块",
                "description": "仿真核心代码",
                "keywords": ["仿真", "EXata", "simulation"],
            },
            {
                "name": "文档",
                "description": "项目文档",
                "keywords": ["README", "文档", "说明"],
            },
        ],
    },
    ensure_ascii=False,
)


def _make_mock_client(call1_resp=_CALL1_RESPONSE, call2_resp=_CALL2_RESPONSE):
    mock_client = MagicMock()
    mock_client.chat.side_effect = [call1_resp, call2_resp]
    mock_client.parse_json_response.side_effect = lambda text: json.loads(text)
    return mock_client


def test_detect_rooms_llm_creates_yaml(tmp_path):
    (tmp_path / "README.md").write_text("# 项目说明")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass")

    mock_client = _make_mock_client()

    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    yaml_file = tmp_path / "mempalace.yaml"
    assert yaml_file.exists()
    data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    assert data["wing"] == "仿真平台"
    assert len(data["rooms"]) == 2
    assert data["rooms"][0]["name"] == "核心模块"
    assert "仿真" in data["rooms"][0]["keywords"]


def test_detect_rooms_llm_yaml_has_keywords(tmp_path):
    (tmp_path / "README.md").write_text("# Test")
    mock_client = _make_mock_client()

    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    data = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    for room in data["rooms"]:
        assert "keywords" in room
        assert isinstance(room["keywords"], list)


def test_detect_rooms_llm_nonexistent_dir_exits():
    with pytest.raises(SystemExit):
        detect_rooms_llm("/nonexistent/path/does/not/exist", yes=True)


def test_detect_rooms_llm_llm_config_error_exits(tmp_path):
    from mempalace.llm_client import LLMConfigError

    with patch("mempalace.llm_detector.LLMClient", side_effect=LLMConfigError("no key")):
        with pytest.raises(SystemExit):
            detect_rooms_llm(str(tmp_path), yes=True)


def test_detect_rooms_llm_import_error_exits(tmp_path):
    with patch("mempalace.llm_detector.LLMClient", side_effect=ImportError("no openai")):
        with pytest.raises(SystemExit):
            detect_rooms_llm(str(tmp_path), yes=True)


def test_detect_rooms_llm_call1_failure_exits(tmp_path):
    from mempalace.llm_client import LLMCallError

    mock_client = MagicMock()
    mock_client.chat.side_effect = LLMCallError("network error")

    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        with pytest.raises(SystemExit):
            detect_rooms_llm(str(tmp_path), yes=True)


def test_detect_rooms_llm_call2_failure_exits(tmp_path):
    from mempalace.llm_client import LLMCallError

    mock_client = MagicMock()
    mock_client.chat.side_effect = [_CALL1_RESPONSE, LLMCallError("call2 fail")]
    mock_client.parse_json_response.side_effect = lambda text: json.loads(text)

    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        with pytest.raises(SystemExit):
            detect_rooms_llm(str(tmp_path), yes=True)


def test_detect_rooms_llm_empty_rooms_gets_general(tmp_path):
    """When LLM returns empty rooms list, a 'general' room is added."""
    call2_empty = json.dumps(
        {"wing_name": "test", "summaries": [], "rooms": []}, ensure_ascii=False
    )
    mock_client = MagicMock()
    mock_client.chat.side_effect = [_CALL1_RESPONSE, call2_empty]
    mock_client.parse_json_response.side_effect = lambda text: json.loads(text)

    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    data = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    room_names = [r["name"] for r in data["rooms"]]
    assert "general" in room_names


def test_detect_rooms_llm_yaml_unicode_preserved(tmp_path):
    """Chinese text in wing/room names must survive YAML round-trip."""
    mock_client = _make_mock_client()
    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    raw = (tmp_path / "mempalace.yaml").read_text(encoding="utf-8")
    # Chinese characters should appear literally, not as \uXXXX escapes
    assert "仿真平台" in raw
    assert "核心模块" in raw
