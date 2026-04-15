"""Tests for mempalace.llm_detector — extract_file_snippet, detect_rooms_llm."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from mempalace.llm_detector import (
    _analyze_branches_concurrent,
    _analyze_scope,
    _build_directory_tree,
    _confirm_split,
    _save_branch_configs,
    _save_root_manifest,
    _validate_branches,
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


def _expected_wing(path: Path) -> str:
    return path.name.lower().replace(" ", "_").replace("-", "_")


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
    assert data["wing"] == _expected_wing(tmp_path)
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
    # Chinese room names should appear literally, not as \uXXXX escapes
    assert "核心模块" in raw


# ── _validate_branches ───────────────────────────────────────────────────


def test_validate_branches_valid(tmp_path):
    sub_a = tmp_path / "proj_a"
    sub_b = tmp_path / "proj_b"
    sub_a.mkdir()
    sub_b.mkdir()

    branches = [
        {"path": "proj_a", "wing_name": "A", "reason": "r"},
        {"path": "proj_b", "wing_name": "B", "reason": "r"},
    ]
    result = _validate_branches(branches, tmp_path)
    assert len(result) == 2
    assert result[0]["abs_path"] == sub_a
    assert result[1]["abs_path"] == sub_b


def test_validate_branches_missing_dir_raises(tmp_path):
    branches = [{"path": "nonexistent", "wing_name": "X", "reason": "r"}]
    with pytest.raises(ValueError, match="not a directory"):
        _validate_branches(branches, tmp_path)


def test_validate_branches_root_self_raises(tmp_path):
    branches = [{"path": ".", "wing_name": "X", "reason": "r"}]
    with pytest.raises(ValueError, match="root"):
        _validate_branches(branches, tmp_path)


def test_validate_branches_path_traversal_raises(tmp_path):
    branches = [{"path": "../outside", "wing_name": "X", "reason": "r"}]
    with pytest.raises(ValueError, match="escapes root"):
        _validate_branches(branches, tmp_path)


def test_validate_branches_overlap_raises(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    branches = [
        {"path": "parent", "wing_name": "P", "reason": "r"},
        {"path": "parent/child", "wing_name": "C", "reason": "r"},
    ]
    with pytest.raises(ValueError, match="overlap"):
        _validate_branches(branches, tmp_path)


def test_validate_branches_empty_path_raises(tmp_path):
    branches = [{"path": "", "wing_name": "X", "reason": "r"}]
    with pytest.raises(ValueError, match="empty path"):
        _validate_branches(branches, tmp_path)


# ── _confirm_split ───────────────────────────────────────────────────────


def test_confirm_split_multi_choice(tmp_path, capsys):
    branches = [{"path": "a", "wing_name": "A", "reason": "reason A"}]
    with patch("builtins.input", return_value="m"):
        result = _confirm_split(tmp_path, "Mixed content", branches)
    assert result is True


def test_confirm_split_single_choice(tmp_path):
    branches = [{"path": "a", "wing_name": "A", "reason": "r"}]
    with patch("builtins.input", return_value="s"):
        result = _confirm_split(tmp_path, "Mixed", branches)
    assert result is False


def test_confirm_split_invalid_then_valid(tmp_path):
    branches = [{"path": "a", "wing_name": "A", "reason": "r"}]
    with patch("builtins.input", side_effect=["bad", "m"]):
        result = _confirm_split(tmp_path, "Mixed", branches)
    assert result is True


# ── _analyze_scope ───────────────────────────────────────────────────────


def test_analyze_scope_returns_single_wing(tmp_path):
    (tmp_path / "README.md").write_text("# Test")
    mock_client = _make_mock_client()
    result = _analyze_scope(mock_client, tmp_path)
    assert "wing_name" in result
    assert "rooms" in result


def test_analyze_scope_returns_split(tmp_path):
    (tmp_path / "README.md").write_text("# Mixed")
    call2_split = json.dumps(
        {
            "analysis_mode": "split",
            "split_reason": "Two distinct projects",
            "why_not_rooms": "These branches should not share the same recall pool",
            "branches": [
                {"path": "a", "wing_name": "A", "boundary_type": "project", "reason": "r"},
                {"path": "b", "wing_name": "B", "boundary_type": "project", "reason": "r"},
            ],
            "single_wing_fallback": {
                "wing_name": "combined",
                "rooms": [{"name": "general", "description": "all", "keywords": []}],
            },
        },
        ensure_ascii=False,
    )
    mock_client = _make_mock_client(call2_resp=call2_split)
    result = _analyze_scope(mock_client, tmp_path)
    assert result.get("analysis_mode") == "split"
    assert len(result["branches"]) == 2
    assert "single_wing_fallback" in result


# ── _analyze_branches_concurrent ─────────────────────────────────────────


def test_analyze_branches_concurrent_success(tmp_path):
    sub_a = tmp_path / "proj_a"
    sub_b = tmp_path / "proj_b"
    sub_a.mkdir()
    sub_b.mkdir()
    (sub_a / "main.py").write_text("def foo(): pass")
    (sub_b / "main.py").write_text("def bar(): pass")

    mock_client = MagicMock()
    mock_client.chat.return_value = _CALL2_RESPONSE
    mock_client.parse_json_response.side_effect = lambda t: json.loads(t)

    branches = [
        {"path": "proj_a", "wing_name": "A", "reason": "r", "abs_path": sub_a},
        {"path": "proj_b", "wing_name": "B", "reason": "r", "abs_path": sub_b},
    ]
    results = _analyze_branches_concurrent(mock_client, branches, max_workers=2)
    assert len(results) == 2
    # Order preserved
    assert results[0]["branch"]["path"] == "proj_a"
    assert results[1]["branch"]["path"] == "proj_b"


def test_analyze_branches_concurrent_failure_raises(tmp_path):
    from mempalace.llm_client import LLMCallError

    sub_a = tmp_path / "proj_a"
    sub_a.mkdir()

    mock_client = MagicMock()
    mock_client.chat.side_effect = LLMCallError("network error")
    mock_client.parse_json_response.side_effect = lambda t: json.loads(t)

    branches = [
        {"path": "proj_a", "wing_name": "A", "reason": "r", "abs_path": sub_a},
    ]
    with pytest.raises(RuntimeError, match="failed"):
        _analyze_branches_concurrent(mock_client, branches)


# ── _save_branch_configs and _save_root_manifest ──────────────────────────


def test_save_branch_configs_writes_yaml(tmp_path):
    sub_a = tmp_path / "proj_a"
    sub_a.mkdir()

    branch_results = [
        {
            "branch": {"path": "proj_a", "abs_path": sub_a},
            "result": {
                "wing_name": "ProjectA",
                "rooms": [{"name": "core", "description": "core", "keywords": ["core"]}],
            },
        }
    ]
    _save_branch_configs(branch_results)
    config = yaml.safe_load((sub_a / "mempalace.yaml").read_text(encoding="utf-8"))
    assert config["wing"] == _expected_wing(sub_a)
    assert config["rooms"][0]["name"] == "core"


def test_save_root_manifest_writes_yaml(tmp_path):
    sub_a = tmp_path / "proj_a"
    sub_b = tmp_path / "proj_b"
    sub_a.mkdir()
    sub_b.mkdir()

    branch_results = [
        {
            "branch": {"path": "proj_a", "abs_path": sub_a},
            "result": {"wing_name": "A", "rooms": []},
        },
        {
            "branch": {"path": "proj_b", "abs_path": sub_b},
            "result": {"wing_name": "B", "rooms": []},
        },
    ]
    _save_root_manifest(str(tmp_path), branch_results)
    manifest = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    assert manifest["mode"] == "multi_wing"
    assert len(manifest["branches"]) == 2
    paths = [b["path"] for b in manifest["branches"]]
    assert "proj_a" in paths
    assert "proj_b" in paths


def test_save_branch_configs_before_root_manifest_ordering(tmp_path):
    """Branch configs must exist before root manifest is written."""
    sub_a = tmp_path / "proj_a"
    sub_a.mkdir()

    branch_results = [
        {
            "branch": {"path": "proj_a", "abs_path": sub_a},
            "result": {
                "wing_name": "A",
                "rooms": [{"name": "g", "description": "d", "keywords": []}],
            },
        }
    ]

    write_order = []
    original_open = open

    def tracking_open(path, mode="r", **kwargs):
        if "w" in mode:
            write_order.append(str(path))
        return original_open(path, mode, **kwargs)

    with patch("builtins.open", side_effect=tracking_open):
        _save_branch_configs(branch_results)
        _save_root_manifest(str(tmp_path), branch_results)

    # Branch config path should appear before root manifest path
    sub_yaml = str(sub_a / "mempalace.yaml")
    root_yaml = str(tmp_path / "mempalace.yaml")
    assert write_order.index(sub_yaml) < write_order.index(root_yaml)


# ── detect_rooms_llm — split path ────────────────────────────────────────

_CALL2_SPLIT_RESPONSE = json.dumps(
    {
        "analysis_mode": "split",
        "split_reason": "Two distinct projects in one directory",
        "why_not_rooms": "Each branch should be recalled independently as its own project",
        "branches": [
            {
                "path": "proj_a",
                "wing_name": "项目A",
                "boundary_type": "project",
                "reason": "独立项目A",
            },
            {
                "path": "proj_b",
                "wing_name": "项目B",
                "boundary_type": "project",
                "reason": "独立项目B",
            },
        ],
        "single_wing_fallback": {
            "wing_name": "混合目录",
            "rooms": [{"name": "general", "description": "all files", "keywords": []}],
        },
    },
    ensure_ascii=False,
)


def _make_mock_client_split():
    """Client: root Call1 + root Call2(split) + two branch Call1s + two branch Call2s."""
    mock_client = MagicMock()
    branch_call2 = json.dumps(
        {
            "wing_name": "分支Wing",
            "summaries": [],
            "rooms": [{"name": "core", "description": "d", "keywords": ["k"]}],
        },
        ensure_ascii=False,
    )
    mock_client.chat.side_effect = [
        _CALL1_RESPONSE,       # root Call1
        _CALL2_SPLIT_RESPONSE, # root Call2 → split
        _CALL1_RESPONSE,       # branch A Call1
        branch_call2,          # branch A Call2
        _CALL1_RESPONSE,       # branch B Call1
        branch_call2,          # branch B Call2
    ]
    mock_client.parse_json_response.side_effect = lambda t: json.loads(t)
    return mock_client


def test_detect_rooms_llm_split_creates_root_manifest(tmp_path):
    sub_a = tmp_path / "proj_a"
    sub_b = tmp_path / "proj_b"
    sub_a.mkdir()
    sub_b.mkdir()
    (sub_a / "README.md").write_text("# A")
    (sub_b / "README.md").write_text("# B")

    mock_client = _make_mock_client_split()
    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    manifest = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    assert manifest["mode"] == "multi_wing"
    assert len(manifest["branches"]) == 2


def test_detect_rooms_llm_split_creates_sub_yamls(tmp_path):
    sub_a = tmp_path / "proj_a"
    sub_b = tmp_path / "proj_b"
    sub_a.mkdir()
    sub_b.mkdir()
    (sub_a / "README.md").write_text("# A")
    (sub_b / "README.md").write_text("# B")

    mock_client = _make_mock_client_split()
    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    assert (sub_a / "mempalace.yaml").exists()
    assert (sub_b / "mempalace.yaml").exists()
    cfg_a = yaml.safe_load((sub_a / "mempalace.yaml").read_text(encoding="utf-8"))
    assert "wing" in cfg_a
    assert "rooms" in cfg_a


def test_detect_rooms_llm_split_decline_falls_back_to_single(tmp_path):
    """User declines split → single-wing fallback mempalace.yaml is written."""
    sub_a = tmp_path / "proj_a"
    sub_b = tmp_path / "proj_b"
    sub_a.mkdir()
    sub_b.mkdir()

    mock_client = MagicMock()
    mock_client.chat.side_effect = [_CALL1_RESPONSE, _CALL2_SPLIT_RESPONSE]
    mock_client.parse_json_response.side_effect = lambda t: json.loads(t)

    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
        patch("builtins.input", return_value="s"),  # decline split
    ):
        detect_rooms_llm(str(tmp_path), yes=False)

    cfg = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    # Should be single-wing fallback, not multi_wing manifest
    assert cfg.get("mode") != "multi_wing"
    assert "wing" in cfg


def test_detect_rooms_llm_split_invalid_branches_falls_back(tmp_path):
    """Invalid branch paths → fallback to single-wing without error exit."""
    # Branches point to non-existent directories
    mock_client = MagicMock()
    mock_client.chat.side_effect = [_CALL1_RESPONSE, _CALL2_SPLIT_RESPONSE]
    mock_client.parse_json_response.side_effect = lambda t: json.loads(t)

    # No sub-directories created — branches will fail validation
    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
        patch("builtins.input", return_value="y"),
    ):
        detect_rooms_llm(str(tmp_path), yes=False)

    cfg = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    assert cfg.get("mode") != "multi_wing"
    assert "wing" in cfg


def test_detect_rooms_llm_root_no_multi_wing_for_single(tmp_path):
    """Normal single-wing path: root mempalace.yaml must NOT have mode=multi_wing."""
    (tmp_path / "README.md").write_text("# Test")
    mock_client = _make_mock_client()
    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    cfg = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    assert cfg.get("mode") != "multi_wing"
    assert "wing" in cfg


def test_detect_rooms_llm_roomish_split_falls_back_to_single(tmp_path):
    """Life-area buckets should stay as rooms, even if the LLM suggests split."""
    (tmp_path / "journal").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "research").mkdir()

    roomish_split = json.dumps(
        {
            "analysis_mode": "split",
            "split_reason": "This personal vault spans journaling, projects, and research",
            "why_not_rooms": "These are different life areas",
            "branches": [
                {
                    "path": "journal",
                    "wing_name": "日记",
                    "boundary_type": "life_area",
                    "reason": "个人日记",
                },
                {
                    "path": "projects",
                    "wing_name": "项目",
                    "boundary_type": "life_area",
                    "reason": "项目执行",
                },
                {
                    "path": "research",
                    "wing_name": "科研",
                    "boundary_type": "life_area",
                    "reason": "科研进展",
                },
            ],
            "single_wing_fallback": {
                "wing_name": "个人库",
                "rooms": [
                    {"name": "journal", "description": "日记", "keywords": ["journal"]},
                    {"name": "projects", "description": "项目", "keywords": ["projects"]},
                    {"name": "research", "description": "科研", "keywords": ["research"]},
                ],
            },
        },
        ensure_ascii=False,
    )

    mock_client = MagicMock()
    mock_client.chat.side_effect = [_CALL1_RESPONSE, roomish_split]
    mock_client.parse_json_response.side_effect = lambda t: json.loads(t)

    with (
        patch("mempalace.llm_detector.LLMClient", return_value=mock_client),
        patch("mempalace.llm_detector.MempalaceConfig"),
    ):
        detect_rooms_llm(str(tmp_path), yes=True)

    cfg = yaml.safe_load((tmp_path / "mempalace.yaml").read_text(encoding="utf-8"))
    assert cfg.get("mode") != "multi_wing"
    assert cfg["wing"] == _expected_wing(tmp_path)
    assert not (tmp_path / "journal" / "mempalace.yaml").exists()
