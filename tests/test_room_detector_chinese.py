"""Tests for Chinese directory name mappings in room_detector_local."""

from mempalace.room_detector_local import FOLDER_ROOM_MAP, detect_rooms_from_folders


# ── FOLDER_ROOM_MAP — Chinese keys ──────────────────────────────────────


def test_folder_room_map_chinese_frontend():
    assert FOLDER_ROOM_MAP["前端"] == "frontend"


def test_folder_room_map_chinese_backend():
    assert FOLDER_ROOM_MAP["后端"] == "backend"


def test_folder_room_map_chinese_source_code():
    assert FOLDER_ROOM_MAP["源码"] == "backend"
    assert FOLDER_ROOM_MAP["源代码"] == "backend"


def test_folder_room_map_chinese_docs():
    assert FOLDER_ROOM_MAP["文档"] == "documentation"
    assert FOLDER_ROOM_MAP["文件"] == "documentation"


def test_folder_room_map_chinese_testing():
    assert FOLDER_ROOM_MAP["测试"] == "testing"


def test_folder_room_map_chinese_config():
    assert FOLDER_ROOM_MAP["配置"] == "configuration"


def test_folder_room_map_chinese_tools():
    assert FOLDER_ROOM_MAP["工具"] == "scripts"
    assert FOLDER_ROOM_MAP["脚本"] == "scripts"


def test_folder_room_map_chinese_examples():
    assert FOLDER_ROOM_MAP["示例"] == "examples"
    assert FOLDER_ROOM_MAP["例子"] == "examples"


def test_folder_room_map_chinese_design():
    assert FOLDER_ROOM_MAP["设计"] == "design"


def test_folder_room_map_chinese_data():
    assert FOLDER_ROOM_MAP["数据"] == "backend"
    assert FOLDER_ROOM_MAP["数据库"] == "backend"


def test_folder_room_map_chinese_components():
    assert FOLDER_ROOM_MAP["组件"] == "frontend"
    assert FOLDER_ROOM_MAP["页面"] == "frontend"


def test_folder_room_map_chinese_team():
    assert FOLDER_ROOM_MAP["团队"] == "team"


def test_folder_room_map_chinese_costs():
    assert FOLDER_ROOM_MAP["财务"] == "costs"
    assert FOLDER_ROOM_MAP["预算"] == "costs"


def test_folder_room_map_chinese_meetings():
    assert FOLDER_ROOM_MAP["会议"] == "meetings"


def test_folder_room_map_chinese_planning():
    assert FOLDER_ROOM_MAP["规划"] == "planning"
    assert FOLDER_ROOM_MAP["需求"] == "planning"


def test_folder_room_map_chinese_research():
    assert FOLDER_ROOM_MAP["研究"] == "research"


# ── Existing English mappings still intact ──────────────────────────────


def test_folder_room_map_english_not_broken():
    assert FOLDER_ROOM_MAP["frontend"] == "frontend"
    assert FOLDER_ROOM_MAP["backend"] == "backend"
    assert FOLDER_ROOM_MAP["docs"] == "documentation"
    assert FOLDER_ROOM_MAP["tests"] == "testing"
    assert FOLDER_ROOM_MAP["config"] == "configuration"


# ── detect_rooms_from_folders with Chinese directories ───────────────────


def test_detect_rooms_from_folders_chinese_frontend(tmp_path):
    (tmp_path / "前端").mkdir()
    rooms = detect_rooms_from_folders(str(tmp_path))
    room_names = {r["name"] for r in rooms}
    assert "frontend" in room_names


def test_detect_rooms_from_folders_chinese_backend(tmp_path):
    (tmp_path / "后端").mkdir()
    rooms = detect_rooms_from_folders(str(tmp_path))
    room_names = {r["name"] for r in rooms}
    assert "backend" in room_names


def test_detect_rooms_from_folders_chinese_docs(tmp_path):
    (tmp_path / "文档").mkdir()
    rooms = detect_rooms_from_folders(str(tmp_path))
    room_names = {r["name"] for r in rooms}
    assert "documentation" in room_names


def test_detect_rooms_from_folders_chinese_testing(tmp_path):
    (tmp_path / "测试").mkdir()
    rooms = detect_rooms_from_folders(str(tmp_path))
    room_names = {r["name"] for r in rooms}
    assert "testing" in room_names


def test_detect_rooms_from_folders_mixed_chinese_english(tmp_path):
    """Mixed Chinese and English directories should both be detected."""
    (tmp_path / "前端").mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "文档").mkdir()
    rooms = detect_rooms_from_folders(str(tmp_path))
    room_names = {r["name"] for r in rooms}
    assert "frontend" in room_names
    assert "backend" in room_names
    assert "documentation" in room_names


def test_detect_rooms_from_folders_chinese_source_code(tmp_path):
    (tmp_path / "源码").mkdir()
    rooms = detect_rooms_from_folders(str(tmp_path))
    room_names = {r["name"] for r in rooms}
    assert "backend" in room_names


def test_detect_rooms_from_folders_chinese_general_fallback(tmp_path):
    """Empty dir with no Chinese matches still gets 'general'."""
    rooms = detect_rooms_from_folders(str(tmp_path))
    room_names = {r["name"] for r in rooms}
    assert "general" in room_names
