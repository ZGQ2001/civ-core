"""workspace_scaffold：标准项目骨架生成（幂等 + 不动用户文件 + root 类型校验）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from civ_core.infra_io.workspace_scaffold import (
    APP_DOTFOLDER,
    APP_SUBFOLDERS,
    STANDARD_SUBFOLDERS,
    create_standard_structure,
)


def test_create_in_empty_dir(tmp_path: Path) -> None:
    """空目录下应建出全部业务子目录 + 应用专属隐藏目录。"""
    root = tmp_path / "新项目"
    create_standard_structure(root)
    assert root.is_dir()
    for name in STANDARD_SUBFOLDERS:
        assert (root / name).is_dir(), f"缺业务子目录 {name}"
    assert (root / APP_DOTFOLDER).is_dir()
    for sub in APP_SUBFOLDERS:
        assert (root / APP_DOTFOLDER / sub).is_dir(), f"缺应用子目录 {sub}"


def test_idempotent_preserves_user_files(tmp_path: Path) -> None:
    """已有项目目录二次调用：不报错，不动用户已经放进去的文件。"""
    root = tmp_path / "已有项目"
    root.mkdir()
    (root / "委托方提供资料").mkdir()
    user_file = root / "委托方提供资料" / "委托单.pdf"
    user_file.write_bytes(b"PDF-DATA")

    create_standard_structure(root)  # 不应报错
    create_standard_structure(root)  # 二次调用同样应幂等

    assert user_file.read_bytes() == b"PDF-DATA", "用户文件被覆盖"
    for name in STANDARD_SUBFOLDERS:
        assert (root / name).is_dir()


def test_root_is_existing_file_raises(tmp_path: Path) -> None:
    """root 路径指向一个已存在的文件 → mkdir 应抛 OSError（不静默吞）。"""
    f = tmp_path / "not_a_dir.txt"
    f.write_text("not a dir")
    with pytest.raises(OSError):
        create_standard_structure(f)


def test_returns_root(tmp_path: Path) -> None:
    """返回值应是 root，便于链式调用。"""
    root = tmp_path / "ret_test"
    out = create_standard_structure(root)
    assert out == root
