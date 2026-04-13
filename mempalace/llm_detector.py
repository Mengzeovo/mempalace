"""
llm_detector.py — LLM-powered room detection for `mempalace init --llm`.

Two-step flow:
  Call 1: Analyse directory tree → suggest wing name, pick 10-15 key files
  Call 2: Read those files' content snippets → generate rooms with keywords

Only imported when the user passes `--llm` to `mempalace init`.
The mine/search pipeline is never affected.
"""

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from .config import MempalaceConfig
from .llm_client import LLMCallError, LLMClient

# ---------------------------------------------------------------------------
# File-type constants
# ---------------------------------------------------------------------------

_CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rs", ".rb", ".sh",
    ".c", ".cpp", ".cs", ".php", ".swift", ".kt",
}

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "env", "dist", "build", ".next", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache",
}

_SKIP_EXTS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".lock", ".sum",
}


# ---------------------------------------------------------------------------
# Snippet extraction
# ---------------------------------------------------------------------------

def extract_file_snippet(filepath: Path, content: str) -> str:
    """Extract a representative snippet from a file for LLM analysis.

    Strategy by file type:
    - Code files (.py, .js, …): first 20 ``def `` / ``class `` definition lines
    - Everything else (docs, config, data): first 300 characters

    Args:
        filepath: Path object used to determine file extension.
        content:  Full decoded file content.

    Returns:
        A short string representative of the file's purpose.
    """
    if filepath.suffix.lower() in _CODE_EXTS:
        lines = content.splitlines()
        symbols = [ln for ln in lines if ln.strip().startswith(("def ", "class "))]
        if symbols:
            return "\n".join(symbols[:20])
    return content[:300]


# ---------------------------------------------------------------------------
# Directory tree builder
# ---------------------------------------------------------------------------

def _build_directory_tree(project_path: Path, max_depth: int = 3) -> str:
    """Build a compact directory tree string for LLM input.

    Args:
        project_path: Resolved project root.
        max_depth:    Maximum recursion depth (default 3).

    Returns:
        Multi-line string representation of the directory tree.
    """
    lines: list[str] = [f"{project_path.name}/"]

    def _walk(directory: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        entries = [e for e in entries if e.name not in _SKIP_DIRS]
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            ext = entry.suffix.lower() if entry.is_file() else ""
            if entry.is_file() and ext in _SKIP_EXTS:
                continue
            size_hint = f"  ({entry.stat().st_size:,} B)" if entry.is_file() else ""
            lines.append(f"{prefix}{connector}{entry.name}{size_hint}")
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                _walk(entry, prefix + extension, depth + 1)

    _walk(project_path, "", 1)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------

_PROMPT_CALL1 = """\
你是一个项目分析助手。

背景：MemPalace 是一个记忆索引系统：
- "wing"（翼）= 项目的唯一名称标识
- "room"（房间）= 项目内的主题分类，用于文件检索过滤

以下是项目的目录结构：
{directory_tree}

请：
1. 给这个项目起一个简洁名称（2-6个字，中英文均可），能概括项目主题
2. 选出 10-15 个最能体现项目内容的文件（优先 README、文档、核心源码）
3. 简要说明对这个项目的初步判断

JSON 格式返回（不要包含其他文字）：
{{
  "wing_name": "...",
  "selected_files": ["path1", "path2", ...],
  "project_summary": "..."
}}"""

_PROMPT_CALL2 = """\
以下是 Call 1 选中的代表性文件，以及它们的内容片段。
项目的初始 wing 名候选为："{wing_name}"

selected_files:
{selected_files}

file_contents:
{file_contents}

请：
1. 为每个文件写一句话摘要（中文）
2. 确认或调整 wing 名称（2-6个字，中英文均可）
3. 将文件分组为 1-8 个主题 room，每个 room 提供：
   - 名称（2-6个字，中英文均可，简短清晰）
   - 一句话描述
   - 关键词列表（中英文混合；这是写入 mempalace.yaml、供 mine 阶段路由匹配使用的字段）
4. room 的关键词应尽量高区分度，避免把所有项目共通词重复分配给每个 room

JSON 返回（不要包含其他文字）：
{{
  "wing_name": "...",
  "summaries": [{{"file": "path", "summary": "..."}}],
  "rooms": [
    {{
      "name": "示例",
      "description": "示例描述",
      "keywords": ["关键词1", "keyword2"]
    }}
  ]
}}"""


def _call1(client: LLMClient, directory_tree: str) -> dict[str, Any]:
    """LLM Call 1: analyse directory tree, select representative files."""
    prompt = _PROMPT_CALL1.format(directory_tree=directory_tree)
    messages = [{"role": "user", "content": prompt}]
    raw = client.chat(messages)
    return client.parse_json_response(raw)


def _call2(
    client: LLMClient,
    wing_name: str,
    selected_files: list[str],
    file_contents: dict[str, str],
) -> dict[str, Any]:
    """LLM Call 2: generate wing name, per-file summaries, and rooms."""
    files_list = "\n".join(f"  - {f}" for f in selected_files)
    contents_parts: list[str] = []
    for fpath in selected_files:
        snippet = file_contents.get(fpath, "(could not read)")
        contents_parts.append(f"### {fpath}\n{snippet}")
    contents_str = "\n\n".join(contents_parts)

    prompt = _PROMPT_CALL2.format(
        wing_name=wing_name,
        selected_files=files_list,
        file_contents=contents_str,
    )
    messages = [{"role": "user", "content": prompt}]
    raw = client.chat(messages)
    return client.parse_json_response(raw)


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def _read_selected_files(
    project_path: Path, selected_files: list[str]
) -> dict[str, str]:
    """Read selected files and extract representative snippets.

    Returns a dict mapping relative path → snippet string.
    """
    snippets: dict[str, str] = {}
    for rel_path in selected_files:
        # Normalise separators and resolve safely under project root
        candidate = (project_path / rel_path.lstrip("/\\")).resolve()
        try:
            candidate.relative_to(project_path)  # path traversal guard
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")
            snippets[rel_path] = extract_file_snippet(candidate, content)
        except OSError:
            snippets[rel_path] = "(could not read)"
    return snippets


# ---------------------------------------------------------------------------
# User interaction helpers (shared with room_detector_local)
# ---------------------------------------------------------------------------

def _print_proposed_structure(project_name: str, rooms: list[dict]) -> None:
    print(f"\n{'=' * 55}")
    print("  MemPalace Init — LLM-powered setup")
    print(f"{'=' * 55}")
    print(f"\n  WING: {project_name}\n")
    for room in rooms:
        kw_str = ", ".join(room.get("keywords", [])[:6])
        print(f"    ROOM: {room['name']}")
        print(f"          {room.get('description', '')}")
        if kw_str:
            print(f"          keywords: {kw_str}")
    print(f"\n{'─' * 55}")


def _get_user_approval(rooms: list[dict]) -> list[dict]:
    """Prompt the user to accept, edit, or add rooms."""
    print("  Review the proposed rooms above.")
    print("  Options:")
    print("    [enter]  Accept all rooms")
    print("    [edit]   Remove or rename rooms")
    print("    [add]    Add a room manually")
    print()

    choice = input("  Your choice [enter/edit/add]: ").strip().lower()

    if choice in ("", "y", "yes"):
        return rooms

    if choice == "edit":
        print("\n  Current rooms:")
        for i, room in enumerate(rooms):
            print(f"    {i + 1}. {room['name']} — {room.get('description', '')}")
        remove = input("\n  Room numbers to REMOVE (comma-separated, or enter to skip): ").strip()
        if remove:
            to_remove = {int(x.strip()) - 1 for x in remove.split(",") if x.strip().isdigit()}
            rooms = [r for idx, r in enumerate(rooms) if idx not in to_remove]

    if choice == "add" or input("\n  Add any missing rooms? [y/N]: ").strip().lower() == "y":
        while True:
            new_name = input("  New room name (or enter to stop): ").strip()
            if not new_name:
                break
            new_desc = input(f"  Description for '{new_name}': ").strip()
            rooms.append({"name": new_name, "description": new_desc, "keywords": [new_name]})
            print(f"  Added: {new_name}")

    return rooms


def _save_config(project_dir: str, wing_name: str, rooms: list[dict]) -> None:
    config: dict[str, Any] = {
        "wing": wing_name,
        "rooms": [
            {
                "name": r["name"],
                "description": r.get("description", ""),
                "keywords": r.get("keywords", [r["name"]]),
            }
            for r in rooms
        ],
    }
    config_path = Path(project_dir).expanduser().resolve() / "mempalace.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\n  Config saved: {config_path}")
    print("\n  Next step:")
    print(f"    mempalace mine {project_dir}")
    print(f"\n{'=' * 55}\n")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_rooms_llm(project_dir: str, yes: bool = False) -> None:
    """Run the two-step LLM detection flow and write mempalace.yaml.

    Args:
        project_dir: Path to the project root directory.
        yes:         If True, auto-accept detected rooms without prompting.

    Raises:
        SystemExit: On LLM failure or configuration error (with user-friendly message).
    """
    project_path = Path(project_dir).expanduser().resolve()

    if not project_path.exists():
        print(f"ERROR: Directory not found: {project_dir}")
        sys.exit(1)

    # Initialise LLM client (may raise LLMConfigError or ImportError)
    try:
        client = LLMClient()
    except ImportError as exc:
        print(f"\n  {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n  LLM configuration error: {exc}")
        sys.exit(1)

    # --- Step 1: directory tree analysis ---
    print(f"\n  Analysing project structure: {project_path}")
    directory_tree = _build_directory_tree(project_path)

    print("  [LLM] Call 1: analysing directory structure...")
    try:
        result1 = _call1(client, directory_tree)
    except (LLMCallError, ValueError) as exc:
        print(f"\n  LLM call failed: {exc}")
        print("  Tip: run `mempalace init <dir>` (without --llm) to use local detection.")
        sys.exit(1)

    wing_name: str = result1.get("wing_name") or project_path.name
    selected_files: list[str] = result1.get("selected_files") or []
    project_summary: str = result1.get("project_summary", "")

    if project_summary:
        print(f"  Project summary: {project_summary}")

    # --- Step 2: read file snippets and generate rooms ---
    print(f"  Reading {len(selected_files)} selected files...")
    file_snippets = _read_selected_files(project_path, selected_files)

    print("  [LLM] Call 2: generating rooms and keywords...")
    try:
        result2 = _call2(client, wing_name, selected_files, file_snippets)
    except (LLMCallError, ValueError) as exc:
        print(f"\n  LLM call failed: {exc}")
        print("  Tip: run `mempalace init <dir>` (without --llm) to use local detection.")
        sys.exit(1)

    final_wing: str = result2.get("wing_name") or wing_name
    rooms: list[dict] = result2.get("rooms") or []

    if not rooms:
        rooms = [{"name": "general", "description": "All project files", "keywords": []}]

    _print_proposed_structure(final_wing, rooms)

    if yes:
        approved_rooms = rooms
    else:
        approved_rooms = _get_user_approval(rooms)

    _save_config(project_dir, final_wing, approved_rooms)

    # Persist global config
    MempalaceConfig().init()
