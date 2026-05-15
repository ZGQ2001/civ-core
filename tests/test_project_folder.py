"""project_folder 文件夹操作测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from civ_core.infra_io.project_folder import (
    SUBFOLDER_NAMES,
    create_project_folder,
    generate_folder_name,
    open_folder,
    open_project_folder,
)


@pytest.fixture
def tmp_parent() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestGenerateFolderName:
    def test_basic_format(self) -> None:
        name = generate_folder_name("20260515", "P2024001", "小米基地检测")
        assert name.startswith("20260515")
        assert "P2024001" in name
        assert "小米基地检测" in name

    def test_separator_is_hyphen(self) -> None:
        name = generate_folder_name("20260515", "P2024001", "小米基地检测")
        assert name == "20260515-P2024001-小米基地检测"

    def test_date_eight_digits(self) -> None:
        with pytest.raises(ValueError, match="8 位"):
            generate_folder_name("2026-05-15", "P001", "项目")

    def test_project_number_not_empty(self) -> None:
        with pytest.raises(ValueError, match="编号"):
            generate_folder_name("20260515", "", "项目")

    def test_name_not_empty(self) -> None:
        with pytest.raises(ValueError, match="名称"):
            generate_folder_name("20260515", "P001", "   ")


class TestSubfolderNames:
    def test_is_tuple_of_strings(self) -> None:
        assert isinstance(SUBFOLDER_NAMES, tuple)
        assert len(SUBFOLDER_NAMES) == 4
        for name in SUBFOLDER_NAMES:
            assert isinstance(name, str)
            assert len(name) > 0

    def test_expected_names(self) -> None:
        assert SUBFOLDER_NAMES == ("委托方提供资料", "图纸", "报告", "数据")


class TestCreateProjectFolder:
    def test_creates_directory_structure(self, tmp_parent: Path) -> None:
        result = create_project_folder(tmp_parent, "20260515", "P2024001", "小米基地检测")
        assert result.exists()
        assert result.is_dir()
        for sub in SUBFOLDER_NAMES:
            sub_path = result / sub
            assert sub_path.exists(), f"缺少子文件夹: {sub}"
            assert sub_path.is_dir()

    def test_folder_name_format(self, tmp_parent: Path) -> None:
        result = create_project_folder(tmp_parent, "20260515", "P2024001", "小米基地检测")
        assert result.name == "20260515-P2024001-小米基地检测"

    def test_parent_is_created_if_missing(self, tmp_parent: Path) -> None:
        nested = tmp_parent / "子目录" / "更深"
        result = create_project_folder(nested, "20260515", "P001", "测试项目")
        assert result.exists()
        assert nested.exists()

    def test_idempotent_creates_subfolders_if_missing(self, tmp_parent: Path) -> None:
        import shutil
        result = create_project_folder(tmp_parent, "20260515", "P001", "测试")
        shutil.rmtree(result / "图纸")
        result2 = create_project_folder(tmp_parent, "20260515", "P001", "测试")
        assert (result2 / "图纸").exists()


class TestOpenFolder:
    @patch("subprocess.run")
    def test_calls_explorer_with_path(self, mock_run, tmp_path: Path) -> None:
        p = tmp_path / "20260515-P001-测试项目"
        p.mkdir()
        open_folder(p)
        mock_run.assert_called_once_with(["explorer", str(p)], check=False)

    def test_raises_when_path_not_exist(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "不存在的文件夹"
        with pytest.raises(FileNotFoundError):
            open_folder(nonexistent)


class TestOpenProjectFolder:
    def test_returns_none_when_path_is_none(self) -> None:
        assert open_project_folder(None) is None

    @patch("subprocess.run")
    def test_calls_open_folder_with_path(self, mock_run, tmp_path: Path) -> None:
        p = tmp_path / "项目"
        p.mkdir()
        result = open_project_folder(p)
        mock_run.assert_called_once()
        assert result is True

    def test_raises_when_path_not_exist(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "不存在"
        with pytest.raises(FileNotFoundError):
            open_project_folder(nonexistent)
