"""
llm_detector.py — LLM-powered room detection for `mempalace init --llm`.

Two-step flow:
  Call 1: Analyse directory tree → suggest wing name, pick 10-15 key files
  Call 2: Read those files' content snippets → generate rooms with keywords,
          OR return a split suggestion when the directory contains mixed topics.

Multi-wing flow (triggered when Call 2 returns analysis_mode=split):
  1. CLI displays split reason + suggested branches; user confirms or falls back.
  2. Each branch directory is analysed concurrently (bounded thread pool).
  3. Sub-directory mempalace.yaml files are written first; root manifest last.

Only imported when the user passes `--llm` to `mempalace init`.
The mine/search pipeline is never affected.
"""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

import yaml

from .config import MempalaceConfig, sanitize_name
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

_ALLOWED_SPLIT_BOUNDARY_TYPES = {
    "client",
    "knowledge_domain",
    "organization",
    "person",
    "product",
    "project",
    "repository",
    "subproject",
    "team",
    "workspace",
}

_DISALLOWED_SPLIT_BOUNDARY_TYPES = {
    "artifact_type",
    "document_type",
    "functional_area",
    "life_area",
    "material_type",
    "semantic_layer",
    "source_type",
    "theme",
    "topic",
    "workflow_stage",
}

_ROOMISH_BRANCH_NAMES = {
    "admin",
    "assets",
    "backend",
    "calendar",
    "career",
    "code",
    "config",
    "configuration",
    "dashboard",
    "design",
    "diary",
    "docs",
    "documentation",
    "finance",
    "frontend",
    "health",
    "inbox",
    "journal",
    "knowledge",
    "learning",
    "life",
    "log",
    "logs",
    "meeting",
    "meetings",
    "notes",
    "people",
    "planning",
    "projects",
    "reading",
    "reflect",
    "reflection",
    "research",
    "roadmap",
    "schedule",
    "scripts",
    "self",
    "study",
    "tasks",
    "test",
    "tests",
    "thinking",
}

_PERSONAL_ROOT_HINTS = {
    "assistant",
    "brain",
    "diary",
    "journal",
    "life",
    "lifelog",
    "lifelong",
    "memo",
    "memory",
    "notes",
    "personal",
    "pkm",
    "second",
    "self",
    "vault",
}

_INDEPENDENCE_SIGNALS = {
    "client",
    "dedicated workspace",
    "distinct project",
    "independent",
    "independent project",
    "knowledge domain",
    "monorepo package",
    "organization",
    "person",
    "separate owner",
    "separate repo",
    "separate repository",
    "separate workspace",
    "standalone",
    "subproject",
    "workspace",
    "不同客户",
    "不同团队",
    "不同仓库",
    "不同工作区",
    "不同组织",
    "不同人物",
    "不同人",
    "不同项目",
    "不同知识域",
    "子项目",
    "独立人物",
    "独立仓库",
    "独立召回",
    "独立团队",
    "独立工作区",
    "独立检索",
    "独立知识域",
    "独立组织",
    "独立项目",
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
- "wing"（翼）= 一个独立的召回池 / wake-up 单元
- "room"（房间）= wing 内部的稳定主题分区，用于文件检索过滤
- 最终写入配置的 wing id 默认使用目录名（稳定、可预测），不要为了命名而发明抽象标签
- 默认策略：能放在同一个 wing 里的内容，尽量不要拆成多个 wing

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
2. 理解当前目录对应的 wing；无需刻意重命名，重点放在 rooms 的划分质量
3. 判断当前目录是否适合作为单个 wing。请严格遵守以下原则：
   - wing = 独立召回边界；room = 同一 wing 内的稳定主题区
   - 默认优先单 wing。只要内容通常应该一起被召回，就不要拆分
   - “材料类型不同 / 语义层不同 / 功能区不同” 不能单独成为拆分 wing 的理由
   - 对 personal vault / life vault / 同一主体知识库：日记、项目、科研、学习、规划等通常应保留在同一个 wing，并拆成不同 room
   - 只有当目录中存在多个“独立召回边界”时，才允许拆分 multi-wing；例如：多个独立项目、不同人物、不同组织、不同客户、不同工作区、不同知识域
   - 如果这些内容只是同一主体下的不同生活域、主题区或职能区，请使用单 wing + 多个 rooms，而不是 multi-wing

【单 wing 模式】将文件分组为 1-8 个主题 room，每个 room 提供：
   - 名称（2-6个字，中英文均可，简短清晰）
   - 一句话描述
   - 关键词列表（中英文混合；这是写入 mempalace.yaml、供 mine 阶段路由匹配使用的字段）
   - room 应尽量体现稳定主题区，例如：journal / projects / research / learning / planning / docs / backend / frontend
   room 的关键词应尽量高区分度，避免把所有项目共通词重复分配给每个 room

【拆分建议模式】只有在存在“独立召回边界”时才能使用。返回时请给出：
   - analysis_mode: "split"
   - split_reason: 一句话说明为什么需要拆分
   - why_not_rooms: 一句话说明为什么这些内容不能只作为 rooms，而必须独立成 wings
   - branches: 建议的子目录列表，每项包含 path（相对于当前分析目录）、wing_name、boundary_type、reason
   - single_wing_fallback: 若用户拒绝拆分，可直接使用的单 wing 结果（wing_name + rooms）
   - boundary_type 必须是以下之一：project / subproject / person / organization / client / workspace / knowledge_domain / repository / product / team
   - 如果你认为拆分后的类别更像 topic / life_area / functional_area / artifact_type / semantic_layer / source_type，请不要返回 split，而是返回单 wing rooms

JSON 返回（不要包含其他文字）：

单 wing 模式：
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
}}

拆分建议模式：
{{
  "analysis_mode": "split",
  "split_reason": "该目录包含多个主题差异明显的独立项目...",
  "why_not_rooms": "这些子目录彼此通常不应被一起召回，且每一支都能独立形成 wake-up 上下文",
  "branches": [
    {{"path": "subdir_a", "wing_name": "项目A名称", "boundary_type": "project", "reason": "..."}},
    {{"path": "subdir_b", "wing_name": "项目B名称", "boundary_type": "project", "reason": "..."}}
  ],
  "single_wing_fallback": {{
    "wing_name": "...",
    "rooms": [
      {{
        "name": "示例",
        "description": "示例描述",
        "keywords": ["关键词1", "keyword2"]
      }}
    ]
  }}
}}"""


def _normalize_label(value: str) -> str:
    """Normalize free-form labels for conservative split heuristics."""
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _default_wing_name(scope_path: Path, root_path: Optional[Path] = None) -> str:
    """Generate a stable wing id from the directory path.

    Single-wing mode follows the original behavior: use the directory name,
    lowercase it, and replace spaces/hyphens with underscores.

    For nested multi-wing branches, use the relative path to avoid collisions
    between siblings that share the same leaf directory name.
    """
    if root_path is not None:
        try:
            relative = scope_path.relative_to(root_path).as_posix()
        except ValueError:
            relative = scope_path.name
    else:
        relative = scope_path.name

    normalized = (
        str(relative).strip().lower().replace("-", "_").replace(" ", "_").replace("/", "__")
    )
    return sanitize_name(normalized or scope_path.name, "wing")


def _branch_leaf_name(branch: dict[str, Any]) -> str:
    """Return the normalized leaf directory name from a split branch path."""
    raw_path = str(branch.get("path", "")).strip().strip("/\\")
    if not raw_path:
        return ""
    return _normalize_label(Path(raw_path).name)


def _looks_like_room_bucket(name: str) -> bool:
    """Heuristic: common life/work buckets are room-like, not wing-like."""
    normalized = _normalize_label(name)
    return normalized in _ROOMISH_BRANCH_NAMES


def _looks_like_personal_root(root_path: Path) -> bool:
    """Detect vault-style roots where single-wing should be the default."""
    normalized = _normalize_label(root_path.name)
    return any(hint in normalized for hint in _PERSONAL_ROOT_HINTS)


def _has_independence_signal(text: str) -> bool:
    """Check whether free-text reasoning mentions true split boundaries."""
    normalized = _normalize_label(text)
    return any(_normalize_label(signal) in normalized for signal in _INDEPENDENCE_SIGNALS)


def _should_accept_split(result: dict[str, Any], root_path: Path) -> tuple[bool, str]:
    """Conservatively approve multi-wing only for independent recall boundaries."""
    branches = result.get("branches") or []
    if len(branches) < 2:
        return False, "multi-wing needs at least two branch directories"

    roomish_branch_count = 0
    for branch in branches:
        branch_name = _branch_leaf_name(branch)
        if branch_name and _looks_like_room_bucket(branch_name):
            roomish_branch_count += 1

        boundary_type = _normalize_label(branch.get("boundary_type"))
        if boundary_type in _DISALLOWED_SPLIT_BOUNDARY_TYPES:
            return (
                False,
                f"branch '{branch.get('path', '?')}' is labeled as '{boundary_type}', which should stay as a room",
            )
        if (
            boundary_type
            and boundary_type not in _ALLOWED_SPLIT_BOUNDARY_TYPES
            and boundary_type not in _DISALLOWED_SPLIT_BOUNDARY_TYPES
        ):
            return (
                False,
                f"branch '{branch.get('path', '?')}' uses unsupported boundary_type '{boundary_type}'",
            )

    reasoning_text = " ".join(
        filter(
            None,
            [
                str(result.get("split_reason", "")),
                str(result.get("why_not_rooms", "")),
                *[str(branch.get("reason", "")) for branch in branches],
            ],
        )
    )
    has_independent_reason = _has_independence_signal(reasoning_text)
    all_roomish = roomish_branch_count == len(branches)
    mostly_roomish = roomish_branch_count >= max(2, len(branches) - 1)

    if all_roomish and not has_independent_reason:
        return False, "suggested branches look like room buckets rather than independent wings"

    if _looks_like_personal_root(root_path) and mostly_roomish and not has_independent_reason:
        return False, "personal vault roots should stay single-wing unless branches are truly independent recall pools"

    return True, ""


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
# Scope analyser — atomic Step1 + Step2 unit (used for root and each branch)
# ---------------------------------------------------------------------------

def _analyze_scope(
    client: LLMClient,
    scope_path: Path,
    print_lock: Optional[threading.Lock] = None,
) -> dict[str, Any]:
    """Run Step1 + Step2 for a single directory scope.

    Returns the raw Call 2 result dict, which is either:
    - Single-wing result: {"wing_name": ..., "summaries": ..., "rooms": [...]}
    - Split suggestion:   {"analysis_mode": "split", "split_reason": ...,
                           "branches": [...], "single_wing_fallback": {...}}

    Args:
        client:      Initialised LLMClient.
        scope_path:  Resolved absolute path of the directory to analyse.
        print_lock:  Optional threading.Lock for thread-safe console output.
                     Pass None when running single-threaded.

    Raises:
        LLMCallError: On LLM network / API failure.
        ValueError:   On JSON parse failure.
    """

    def _print(msg: str) -> None:
        if print_lock:
            with print_lock:
                print(msg)
        else:
            print(msg)

    _print(f"  Analysing scope: {scope_path}")
    directory_tree = _build_directory_tree(scope_path)

    _print("  [LLM] Call 1: analysing directory structure...")
    result1 = _call1(client, directory_tree)

    wing_name: str = _default_wing_name(scope_path)
    selected_files: list[str] = result1.get("selected_files") or []
    project_summary: str = result1.get("project_summary", "")

    if project_summary:
        _print(f"  Summary: {project_summary}")

    _print(f"  Reading {len(selected_files)} selected files...")
    file_snippets = _read_selected_files(scope_path, selected_files)

    _print("  [LLM] Call 2: generating rooms / split suggestion...")
    result2 = _call2(client, wing_name, selected_files, file_snippets)

    return result2


# ---------------------------------------------------------------------------
# Branch path validation
# ---------------------------------------------------------------------------

def _validate_branches(
    branches: list[dict],
    root_path: Path,
) -> list[dict]:
    """Validate and normalise branch paths returned by LLM.

    Rules:
    - path must resolve to a real subdirectory under root_path
    - paths must not be root_path itself
    - paths must not overlap (no ancestor–descendant pairs)

    Returns cleaned branch list with resolved absolute ``abs_path`` added.

    Raises:
        ValueError: If any branch fails validation.
    """
    resolved: list[tuple[Path, dict]] = []
    for branch in branches:
        raw_path = branch.get("path", "").strip().lstrip("/\\")
        if not raw_path:
            raise ValueError(f"Branch has empty path: {branch}")
        candidate = (root_path / raw_path).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError:
            raise ValueError(
                f"Branch path escapes root: {raw_path!r} → {candidate}"
            )
        if candidate == root_path:
            raise ValueError(
                f"Branch path points to root directory: {raw_path!r}"
            )
        if not candidate.is_dir():
            raise ValueError(
                f"Branch path is not a directory: {candidate}"
            )
        resolved.append((candidate, branch))

    # Check for overlapping paths (ancestor–descendant)
    paths = [p for p, _ in resolved]
    for i, p1 in enumerate(paths):
        for j, p2 in enumerate(paths):
            if i != j:
                is_sub = False
                try:
                    p2.relative_to(p1)
                    is_sub = True
                except ValueError:
                    pass
                if is_sub:
                    raise ValueError(
                        f"Branch paths overlap: {p1} contains {p2}"
                    )

    result = []
    for abs_path, branch in resolved:
        b = dict(branch)
        b["abs_path"] = abs_path
        result.append(b)
    return result


# ---------------------------------------------------------------------------
# User interaction helpers (shared with room_detector_local)
# ---------------------------------------------------------------------------

def _confirm_split(
    root_path: Path,
    split_reason: str,
    branches: list[dict],
) -> bool:
    """Display split suggestion and ask the user to confirm or fall back.

    Prints a fixed-format summary to the terminal showing:
    - Current directory
    - LLM's split reason
    - Suggested branches (path + wing_name + reason)
    - Risk of continuing as single-wing

    Returns:
        True  → user chose multi-wing (proceed with split)
        False → user chose single-wing (use single_wing_fallback)
    """
    print(f"\n{'=' * 55}")
    print("  MemPalace Init — Multi-Wing Split Suggestion")
    print(f"{'=' * 55}")
    print(f"\n  Directory : {root_path}")
    print(f"\n  Reason    : {split_reason}")
    print(f"\n  Suggested branches ({len(branches)}):")
    for b in branches:
        branch_path = b.get("abs_path")
        if branch_path is None:
            branch_path = (root_path / str(b.get("path", "")).strip().lstrip("/\\")).resolve()
        branch_wing = _default_wing_name(branch_path, root_path)
        print(f"\n    PATH  : {b.get('path', '?')}")
        print(f"    WING  : {branch_wing}")
        print(f"    WHY   : {b.get('reason', '?')}")
    print(
        "\n  Risk of single-wing: only a problem when these branches should not be recalled together."
    )
    print(f"\n{'─' * 55}")
    print("  Options:")
    print("    [m] / [multi]   Enter multi-wing mode (only if these are truly separate recall pools)")
    print("    [s] / [single]  Continue as single-wing")
    print()

    while True:
        choice = input("  Your choice [m/s]: ").strip().lower()
        if choice in ("m", "multi", "y", "yes"):
            return True
        if choice in ("s", "single", "n", "no"):
            return False
        print("  Please enter 'm' for multi-wing or 's' for single-wing.")


def _analyze_branches_concurrent(
    client: LLMClient,
    branches: list[dict],
    max_workers: int = 4,
) -> list[dict]:
    """Analyse each validated branch directory concurrently.

    Uses a bounded ThreadPoolExecutor. Output is collected per-branch and
    printed after all futures complete to avoid interleaved log lines.

    Args:
        client:      Shared LLMClient instance (thread-safe read-only usage).
        branches:    Validated branch dicts with ``abs_path`` set.
        max_workers: Maximum concurrent LLM calls (default 4, capped to
                     number of branches).

    Returns:
        List of result dicts, one per branch, each containing:
        {"branch": <original branch dict>, "result": <_analyze_scope return>}

    Raises:
        RuntimeError: If any branch analysis fails (contains error details).
    """
    workers = min(len(branches), max_workers)
    print_lock = threading.Lock()
    errors: list[str] = []
    raw_results: list[tuple[int, dict]] = []

    print(f"\n  Analysing {len(branches)} branches (up to {workers} concurrent)...")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(
                _analyze_scope, client, b["abs_path"], print_lock
            ): i
            for i, b in enumerate(branches)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            branch = branches[idx]
            try:
                result = future.result()
                raw_results.append((idx, {"branch": branch, "result": result}))
            except (LLMCallError, ValueError) as exc:
                errors.append(
                    f"Branch '{branch.get('path', '?')}' failed: {exc}"
                )

    if errors:
        raise RuntimeError(
            "One or more branch analyses failed:\n" + "\n".join(errors)
        )

    # Restore original branch order
    raw_results.sort(key=lambda t: t[0])
    return [r for _, r in raw_results]


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
    """Write a single-wing mempalace.yaml to project_dir."""
    stable_wing = _default_wing_name(Path(project_dir).expanduser().resolve())
    config: dict[str, Any] = {
        "wing": stable_wing,
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


def _save_branch_configs(branch_results: list[dict]) -> None:
    """Write mempalace.yaml into each branch sub-directory.

    Called before _save_root_manifest to ensure atomic ordering: if writing
    any sub-directory config fails, the root manifest is never created, so
    ``mine`` cannot accidentally consume a partial multi-wing setup.

    Args:
        branch_results: List returned by _analyze_branches_concurrent, each
                        item is {"branch": {..., "abs_path": Path},
                                 "result": {call2 result dict}}.
    """
    for item in branch_results:
        branch = item["branch"]
        result = item["result"]
        abs_path: Path = branch["abs_path"]

        wing_name = _default_wing_name(abs_path)
        rooms: list[dict] = result.get("rooms") or []
        if not rooms:
            rooms = [{"name": "general", "description": "All project files", "keywords": []}]

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
        config_path = abs_path / "mempalace.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print(f"  Branch config saved: {config_path}")


def _save_root_manifest(root_dir: str, branch_results: list[dict]) -> None:
    """Write the multi-wing root manifest to root_dir/mempalace.yaml.

    Must be called AFTER _save_branch_configs to preserve atomic ordering.

    Args:
        root_dir:       The project root directory path (str).
        branch_results: List returned by _analyze_branches_concurrent.
    """
    root_path = Path(root_dir).expanduser().resolve()
    branches_data = []
    for item in branch_results:
        branch = item["branch"]
        abs_path: Path = branch["abs_path"]
        wing_name = _default_wing_name(abs_path, root_path)
        rel_path = abs_path.relative_to(root_path).as_posix()
        branches_data.append({"path": rel_path, "wing": wing_name})

    manifest: dict[str, Any] = {
        "mode": "multi_wing",
        "branches": branches_data,
    }
    manifest_path = root_path / "mempalace.yaml"
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"\n  Root manifest saved: {manifest_path}")


def _print_multi_wing_summary(branch_results: list[dict]) -> None:
    """Print a summary of all analysed branches before final confirmation."""
    print(f"\n{'=' * 55}")
    print("  MemPalace Init — Multi-Wing Summary")
    print(f"{'=' * 55}")
    for item in branch_results:
        branch = item["branch"]
        result = item["result"]
        wing_name = _default_wing_name(branch["abs_path"])
        rooms = result.get("rooms") or []
        print(f"\n  BRANCH : {branch.get('path', '?')}")
        print(f"  WING   : {wing_name}")
        for room in rooms:
            kw_str = ", ".join(room.get("keywords", [])[:5])
            print(f"    ROOM: {room['name']} — {room.get('description', '')}")
            if kw_str:
                print(f"          keywords: {kw_str}")
    print(f"\n{'─' * 55}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_rooms_llm(project_dir: str, yes: bool = False) -> None:
    """Run the two-step LLM detection flow and write mempalace.yaml.

    Handles both single-wing and multi-wing (split) scenarios:
    - Single-wing: writes one mempalace.yaml in project_dir (existing behaviour).
    - Multi-wing:  writes sub-directory configs first, then root manifest.

    Args:
        project_dir: Path to the project root directory.
        yes:         If True, auto-accept all suggestions without prompting.

    Raises:
        SystemExit: On LLM failure, configuration error, or branch validation
                    failure (with user-friendly message).
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

    # --- Root scope analysis (Step 1 + Step 2) ---
    print(f"\n  Analysing project structure: {project_path}")
    try:
        result2 = _analyze_scope(client, project_path)
    except (LLMCallError, ValueError) as exc:
        print(f"\n  LLM call failed: {exc}")
        print("  Tip: run `mempalace init <dir>` (without --llm) to use local detection.")
        sys.exit(1)

    # --- Determine path: single-wing or split ---
    if result2.get("analysis_mode") == "split":
        split_reason: str = result2.get("split_reason", "Mixed project topics detected.")
        raw_branches: list[dict] = result2.get("branches") or []
        fallback: dict = result2.get("single_wing_fallback") or {}

        split_ok, split_guard_reason = _should_accept_split(result2, project_path)
        if not split_ok:
            print(f"\n  Split suggestion downgraded to single-wing: {split_guard_reason}")
            raw_branches = []

        # Validate branch paths before asking the user
        try:
            validated_branches = _validate_branches(raw_branches, project_path)
        except ValueError as exc:
            print(f"\n  Branch validation failed: {exc}")
            print("  Falling back to single-wing mode.")
            validated_branches = []

        if not validated_branches:
            # No valid branches → force single-wing fallback
            go_multi = False
        elif yes:
            go_multi = True
        else:
            go_multi = _confirm_split(project_path, split_reason, validated_branches)

        if go_multi:
            # --- Multi-wing path ---
            try:
                branch_results = _analyze_branches_concurrent(client, validated_branches)
            except (LLMCallError, ValueError, RuntimeError) as exc:
                print(f"\n  Branch analysis failed: {exc}")
                print("  Falling back to single-wing mode.")
                go_multi = False

        if go_multi:
            _print_multi_wing_summary(branch_results)

            if not yes:
                confirm = input(
                    "\n  Confirm multi-wing setup? [Y/n]: "
                ).strip().lower()
                if confirm in ("n", "no"):
                    print("  Cancelled. No files written.")
                    sys.exit(0)

            # Atomic write: sub-directories first, root manifest last
            try:
                _save_branch_configs(branch_results)
                _save_root_manifest(project_dir, branch_results)
            except OSError as exc:
                print(f"\n  ERROR: Failed to write config files: {exc}")
                sys.exit(1)

            print("\n  Next step:")
            print(f"    mempalace mine {project_dir}")
            print(f"\n{'=' * 55}\n")
            MempalaceConfig().init()
            return

        # --- Single-wing fallback after declined/failed split ---
        final_wing = _default_wing_name(project_path)
        rooms: list[dict] = fallback.get("rooms") or []

    else:
        # Normal single-wing result
        final_wing = _default_wing_name(project_path)
        rooms = result2.get("rooms") or []

    # --- Single-wing path (original behaviour) ---
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
