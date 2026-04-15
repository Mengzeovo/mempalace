import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import chromadb
import pytest
import yaml

from mempalace.miner import mine, scan_project
from mempalace.palace import file_already_mined


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def scanned_files(project_root: Path, **kwargs):
    files = scan_project(str(project_root), **kwargs)
    return sorted(path.relative_to(project_root).as_posix() for path in files)


def test_project_mining():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()
        os.makedirs(project_root / "backend")

        write_file(
            project_root / "backend" / "app.py", "def main():\n    print('hello world')\n" * 20
        )
        with open(project_root / "mempalace.yaml", "w") as f:
            yaml.dump(
                {
                    "wing": "test_project",
                    "rooms": [
                        {"name": "backend", "description": "Backend code"},
                        {"name": "general", "description": "General"},
                    ],
                },
                f,
            )

        palace_path = project_root / "palace"
        mine(str(project_root), str(palace_path))

        client = chromadb.PersistentClient(path=str(palace_path))
        col = client.get_collection("mempalace_drawers")
        assert col.count() > 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_scan_project_respects_gitignore():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "ignored.py\ngenerated/\n")
        write_file(project_root / "src" / "app.py", "print('hello')\n" * 20)
        write_file(project_root / "ignored.py", "print('ignore me')\n" * 20)
        write_file(project_root / "generated" / "artifact.py", "print('artifact')\n" * 20)

        assert scanned_files(project_root) == ["src/app.py"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_respects_nested_gitignore():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "*.log\n")
        write_file(project_root / "subrepo" / ".gitignore", "tasks/\n")
        write_file(project_root / "subrepo" / "src" / "main.py", "print('main')\n" * 20)
        write_file(project_root / "subrepo" / "tasks" / "task.py", "print('task')\n" * 20)
        write_file(project_root / "subrepo" / "debug.log", "debug\n" * 20)

        assert scanned_files(project_root) == ["subrepo/src/main.py"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_allows_nested_gitignore_override():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "*.csv\n")
        write_file(project_root / "subrepo" / ".gitignore", "!keep.csv\n")
        write_file(project_root / "drop.csv", "a,b,c\n" * 20)
        write_file(project_root / "subrepo" / "keep.csv", "a,b,c\n" * 20)

        assert scanned_files(project_root) == ["subrepo/keep.csv"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_allows_gitignore_negation_when_parent_dir_is_visible():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "generated/*\n!generated/keep.py\n")
        write_file(project_root / "generated" / "drop.py", "print('drop')\n" * 20)
        write_file(project_root / "generated" / "keep.py", "print('keep')\n" * 20)

        assert scanned_files(project_root) == ["generated/keep.py"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_does_not_reinclude_file_from_ignored_directory():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "generated/\n!generated/keep.py\n")
        write_file(project_root / "generated" / "drop.py", "print('drop')\n" * 20)
        write_file(project_root / "generated" / "keep.py", "print('keep')\n" * 20)

        assert scanned_files(project_root) == []
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_can_disable_gitignore():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "data/\n")
        write_file(project_root / "data" / "stuff.csv", "a,b,c\n" * 20)

        assert scanned_files(project_root, respect_gitignore=False) == ["data/stuff.csv"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_can_include_ignored_directory():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "docs/\n")
        write_file(project_root / "docs" / "guide.md", "# Guide\n" * 20)

        assert scanned_files(project_root, include_ignored=["docs"]) == ["docs/guide.md"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_can_include_specific_ignored_file():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "generated/\n")
        write_file(project_root / "generated" / "drop.py", "print('drop')\n" * 20)
        write_file(project_root / "generated" / "keep.py", "print('keep')\n" * 20)

        assert scanned_files(project_root, include_ignored=["generated/keep.py"]) == [
            "generated/keep.py"
        ]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_can_include_exact_file_without_known_extension():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".gitignore", "README\n")
        write_file(project_root / "README", "hello\n" * 20)

        assert scanned_files(project_root, include_ignored=["README"]) == ["README"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_include_override_beats_skip_dirs():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".pytest_cache" / "cache.py", "print('cache')\n" * 20)

        assert scanned_files(
            project_root,
            respect_gitignore=False,
            include_ignored=[".pytest_cache"],
        ) == [".pytest_cache/cache.py"]
    finally:
        shutil.rmtree(tmpdir)


def test_scan_project_skip_dirs_still_apply_without_override():
    tmpdir = tempfile.mkdtemp()
    try:
        project_root = Path(tmpdir).resolve()

        write_file(project_root / ".pytest_cache" / "cache.py", "print('cache')\n" * 20)
        write_file(project_root / "main.py", "print('main')\n" * 20)

        assert scanned_files(project_root, respect_gitignore=False) == ["main.py"]
    finally:
        shutil.rmtree(tmpdir)


def test_file_already_mined_check_mtime():
    tmpdir = tempfile.mkdtemp()
    try:
        palace_path = os.path.join(tmpdir, "palace")
        os.makedirs(palace_path)
        from mempalace.palace import get_collection
        col = get_collection(palace_path)

        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello world")

        mtime = os.path.getmtime(test_file)

        # Not mined yet
        assert file_already_mined(col, test_file) is False
        assert file_already_mined(col, test_file, check_mtime=True) is False

        # Add it with mtime
        col.add(
            ids=["d1"],
            documents=["hello world"],
            metadatas=[{"source_file": test_file, "source_mtime": str(mtime)}],
        )

        # Already mined (no mtime check)
        assert file_already_mined(col, test_file) is True
        # Already mined (mtime matches)
        assert file_already_mined(col, test_file, check_mtime=True) is True

        # Modify file and force a different mtime (Windows has low mtime resolution)
        with open(test_file, "w") as f:
            f.write("modified content")
        os.utime(test_file, (mtime + 10, mtime + 10))

        # Still mined without mtime check
        assert file_already_mined(col, test_file) is True
        # Needs re-mining with mtime check
        assert file_already_mined(col, test_file, check_mtime=True) is False

        # Record with no mtime stored should return False for check_mtime
        col.add(
            ids=["d2"],
            documents=["other"],
            metadatas=[{"source_file": "/fake/no_mtime.txt"}],
        )
        assert file_already_mined(col, "/fake/no_mtime.txt", check_mtime=True) is False
    finally:
        # Release ChromaDB file handles before cleanup (required on Windows)
        col = None  # noqa: F841
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Multi-wing manifest tests ────────────────────────────────────────────


def _write_single_wing_config(directory: Path, wing: str, rooms=None):
    if rooms is None:
        rooms = [{"name": "general", "description": "General", "keywords": []}]
    with open(directory / "mempalace.yaml", "w") as f:
        yaml.dump({"wing": wing, "rooms": rooms}, f)


def _write_multi_wing_manifest(root: Path, branches: list):
    """branches: list of {"path": rel, "wing": name}"""
    with open(root / "mempalace.yaml", "w") as f:
        yaml.dump({"mode": "multi_wing", "branches": branches}, f)


def test_mine_multi_wing_calls_each_branch(tmp_path):
    """mine() with multi-wing manifest should invoke itself for each branch."""
    sub_a = tmp_path / "proj_a"
    sub_b = tmp_path / "proj_b"
    sub_a.mkdir()
    sub_b.mkdir()
    write_file(sub_a / "app.py", "def foo(): pass\n" * 20)
    write_file(sub_b / "app.py", "def bar(): pass\n" * 20)
    _write_single_wing_config(sub_a, "ProjectA")
    _write_single_wing_config(sub_b, "ProjectB")
    _write_multi_wing_manifest(tmp_path, [
        {"path": "proj_a", "wing": "ProjectA"},
        {"path": "proj_b", "wing": "ProjectB"},
    ])

    palace_path = tmp_path / "palace"
    mine(str(tmp_path), str(palace_path))

    client = chromadb.PersistentClient(path=str(palace_path))
    col = client.get_collection("mempalace_drawers")
    metas = col.get(limit=1000, include=["metadatas"])["metadatas"]
    wings = {m["wing"] for m in metas}
    assert "ProjectA" in wings
    assert "ProjectB" in wings
    del col, client


def test_mine_multi_wing_root_files_not_indexed(tmp_path):
    """Root-level files must not be indexed in multi-wing mode."""
    sub_a = tmp_path / "proj_a"
    sub_a.mkdir()
    write_file(sub_a / "app.py", "def foo(): pass\n" * 20)
    _write_single_wing_config(sub_a, "ProjectA")

    # Root-level file that should be ignored
    write_file(tmp_path / "root_readme.md", "# Root readme\n" * 20)

    _write_multi_wing_manifest(tmp_path, [{"path": "proj_a", "wing": "ProjectA"}])

    palace_path = tmp_path / "palace"
    mine(str(tmp_path), str(palace_path))

    client = chromadb.PersistentClient(path=str(palace_path))
    col = client.get_collection("mempalace_drawers")
    metas = col.get(limit=1000, include=["metadatas"])["metadatas"]
    source_files = [m["source_file"] for m in metas]
    assert not any("root_readme" in sf for sf in source_files)
    del col, client


def test_mine_multi_wing_with_wing_override_exits(tmp_path):
    """--wing must be rejected when root config is a multi-wing manifest."""
    sub_a = tmp_path / "proj_a"
    sub_a.mkdir()
    _write_single_wing_config(sub_a, "ProjectA")
    _write_multi_wing_manifest(tmp_path, [{"path": "proj_a", "wing": "ProjectA"}])

    with pytest.raises(SystemExit):
        mine(str(tmp_path), str(tmp_path / "palace"), wing_override="override_wing")


def test_mine_multi_wing_missing_branch_dir_exits(tmp_path):
    """mine() must exit if a declared branch directory does not exist."""
    _write_multi_wing_manifest(tmp_path, [{"path": "nonexistent", "wing": "X"}])

    with pytest.raises(SystemExit):
        mine(str(tmp_path), str(tmp_path / "palace"))


def test_mine_multi_wing_empty_branches_exits(tmp_path):
    """mine() must exit when multi_wing manifest has no branches."""
    with open(tmp_path / "mempalace.yaml", "w") as f:
        yaml.dump({"mode": "multi_wing", "branches": []}, f)

    with pytest.raises(SystemExit):
        mine(str(tmp_path), str(tmp_path / "palace"))


def test_mine_multi_wing_overlapping_branches_exits(tmp_path):
    """mine() must exit when branch paths overlap (ancestor–descendant)."""
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    _write_single_wing_config(parent, "Parent")
    _write_single_wing_config(child, "Child")
    _write_multi_wing_manifest(tmp_path, [
        {"path": "parent", "wing": "Parent"},
        {"path": "parent/child", "wing": "Child"},
    ])

    with pytest.raises(SystemExit):
        mine(str(tmp_path), str(tmp_path / "palace"))


def test_mine_single_wing_unchanged(tmp_path):
    """Existing single-wing behaviour must be completely unaffected."""
    write_file(tmp_path / "src" / "app.py", "def main(): pass\n" * 20)
    _write_single_wing_config(tmp_path, "MyProject")

    palace_path = tmp_path / "palace"
    mine(str(tmp_path), str(palace_path))

    client = chromadb.PersistentClient(path=str(palace_path))
    col = client.get_collection("mempalace_drawers")
    assert col.count() > 0
    metas = col.get(limit=100, include=["metadatas"])["metadatas"]
    assert all(m["wing"] == "MyProject" for m in metas)
    del col, client
