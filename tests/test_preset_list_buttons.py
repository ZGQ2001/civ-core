"""PresetListPane 的按钮态 + 写入联动测试（T-4 Step 4）。

只测可机器化部分：
  • 三按钮的可用性按当前选中项联动（_update_action_buttons）
  • +新建 → emit new_preset_requested 信号
  • 复制流程：monkeypatch 对话框 exec → 直接调 copy_system_to_user → refresh 后选中新条目
  • 删除流程：monkeypatch 确认对话框 → delete_user_preset → refresh

不测的内容：对话框视觉布局、InfoBar 实际样式（Step 6 手测覆盖）。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.infra_io import preset_manager  # noqa: E402
from civ_core.infra_io.preset_manager import PresetEntry, PresetSource  # noqa: E402
from civ_core.ui.components import preset_list as preset_list_mod  # noqa: E402
from civ_core.ui.components.preset_list import PresetListPane  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def patched_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """把系统/用户预设路径都 monkeypatch 到 tmp_path，避免动真实文件系统。"""
    sys_file = tmp_path / "sys.json"
    user_file = tmp_path / "user.json"
    sys_file.write_text(
        json.dumps(
            {
                "系统A": {"id_column": "A编号", "curves": []},
                "系统B": {"id_column": "B编号", "curves": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    user_file.write_text(
        json.dumps({"我的X": {"id_column": "X编号", "curves": []}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        preset_manager, "get_system_presets_path", lambda tool="plot_curves": sys_file
    )
    monkeypatch.setattr(
        preset_manager, "get_user_presets_path", lambda tool="plot_curves": user_file
    )
    return sys_file, user_file


@pytest.fixture
def pane(
    qapp: QApplication, patched_paths: tuple[Path, Path]
) -> PresetListPane:
    p = PresetListPane()
    yield p
    p.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 按钮态：_update_action_buttons
# ──────────────────────────────────────────────────────────────────
class TestButtonStates:
    def test_no_selection_disables_copy_and_delete(
        self, pane: PresetListPane
    ) -> None:
        pane._update_action_buttons(entry=None)
        assert pane._new_btn.isEnabled() is True
        assert pane._copy_btn.isEnabled() is False
        assert pane._delete_btn.isEnabled() is False

    def test_system_selection_enables_copy_only(
        self, pane: PresetListPane
    ) -> None:
        entry = PresetEntry(name="X", data={}, source=PresetSource.SYSTEM)
        pane._update_action_buttons(entry=entry)
        assert pane._new_btn.isEnabled() is True
        assert pane._copy_btn.isEnabled() is True
        assert pane._delete_btn.isEnabled() is False

    def test_user_selection_enables_copy_and_delete(
        self, pane: PresetListPane
    ) -> None:
        entry = PresetEntry(name="X", data={}, source=PresetSource.USER)
        pane._update_action_buttons(entry=entry)
        assert pane._new_btn.isEnabled() is True
        assert pane._copy_btn.isEnabled() is True
        assert pane._delete_btn.isEnabled() is True

    def test_buttons_track_selection_after_refresh(
        self, pane: PresetListPane
    ) -> None:
        """整张 refresh 后，按钮态应反映"当前选中是系统还是用户"。

        默认 setCurrentRow(0) 选第一项 → 系统A → 删除应禁用。
        """
        pane.refresh()
        assert pane.selected_preset_name() == "系统A"
        assert pane._delete_btn.isEnabled() is False
        assert pane._copy_btn.isEnabled() is True


# ──────────────────────────────────────────────────────────────────
# +新建：信号 + 取消选中
# ──────────────────────────────────────────────────────────────────
class TestNewButton:
    def test_new_emits_signal_and_clears_selection(
        self, pane: PresetListPane
    ) -> None:
        emitted: list[None] = []
        pane.new_preset_requested.connect(lambda: emitted.append(None))

        pane.refresh()
        assert pane.selected_preset_name() is not None  # 默认有选中

        pane._on_new_clicked()

        assert len(emitted) == 1  # 信号发了
        assert pane.selected_preset_name() is None  # 选中被清掉
        # 复制 / 删除按钮也跟着禁用
        assert pane._copy_btn.isEnabled() is False
        assert pane._delete_btn.isEnabled() is False


# ──────────────────────────────────────────────────────────────────
# 复制：monkeypatch 对话框 exec()
# ──────────────────────────────────────────────────────────────────
class TestCopyButton:
    def _patch_dialog(
        self,
        monkeypatch: pytest.MonkeyPatch,
        accepted: bool,
        new_name: str = "",
    ) -> None:
        """让 _NameInputDialog.exec 返回 accepted/取消，并预设 nameEdit 文本。"""
        original_init = preset_list_mod._NameInputDialog.__init__

        def fake_init(self, title, default_name="", parent=None) -> None:  # type: ignore
            original_init(self, title, default_name, parent)
            self.nameEdit.setText(new_name)

        monkeypatch.setattr(
            preset_list_mod._NameInputDialog, "__init__", fake_init
        )
        monkeypatch.setattr(
            preset_list_mod._NameInputDialog,
            "exec",
            lambda self: 1 if accepted else 0,
        )

    def test_copy_system_to_user_writes_and_selects_new(
        self,
        pane: PresetListPane,
        patched_paths: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """复制系统预设 → 用户文件多一条 + 列表选中新副本。"""
        _, user_file = patched_paths
        self._patch_dialog(monkeypatch, accepted=True, new_name="我的复制A")

        pane.refresh()
        # 选中"系统A"
        pane._list.setCurrentRow(0)
        assert pane.selected_preset_name() == "系统A"

        pane._on_copy_clicked()

        # 用户文件里多了"我的复制A"
        raw = json.loads(user_file.read_text(encoding="utf-8"))
        assert "我的复制A" in raw
        assert raw["我的复制A"]["id_column"] == "A编号"

        # 列表已 refresh + 选中新副本
        assert pane.selected_preset_name() == "我的复制A"
        # 选中是用户预设 → 删除按钮启用
        assert pane._delete_btn.isEnabled() is True

    def test_copy_canceled_does_nothing(
        self,
        pane: PresetListPane,
        patched_paths: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, user_file = patched_paths
        original = user_file.read_text(encoding="utf-8")

        self._patch_dialog(monkeypatch, accepted=False)
        pane.refresh()
        pane._list.setCurrentRow(0)
        pane._on_copy_clicked()

        # 用户文件未变
        assert user_file.read_text(encoding="utf-8") == original

    def test_copy_to_existing_user_name_shows_error(
        self,
        pane: PresetListPane,
        patched_paths: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """new_name 已经在用户预设里 → preset_manager 抛 PresetError，UI 应吃掉。

        这里把对话框新名字设为已存在的"我的X"，验证不崩，文件无变化。
        """
        _, user_file = patched_paths
        original = user_file.read_text(encoding="utf-8")
        self._patch_dialog(monkeypatch, accepted=True, new_name="我的X")

        pane.refresh()
        pane._list.setCurrentRow(0)
        pane._on_copy_clicked()  # 不应抛

        assert user_file.read_text(encoding="utf-8") == original


# ──────────────────────────────────────────────────────────────────
# 删除：monkeypatch 确认对话框
# ──────────────────────────────────────────────────────────────────
class TestDeleteButton:
    def _patch_confirm(
        self, monkeypatch: pytest.MonkeyPatch, accepted: bool
    ) -> None:
        # 删除用 MessageBox 弹确认，monkeypatch 它的 exec
        from qfluentwidgets import MessageBox

        monkeypatch.setattr(
            MessageBox, "exec", lambda self: 1 if accepted else 0
        )

    def test_delete_user_preset_removes_and_refreshes(
        self,
        pane: PresetListPane,
        patched_paths: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, user_file = patched_paths
        self._patch_confirm(monkeypatch, accepted=True)

        pane.refresh()
        # 选中用户预设"我的X"
        for row in range(pane._list.count()):
            if pane._list.item(row).data(preset_list_mod._ROLE_PRESET_ENTRY).name == "我的X":
                pane._list.setCurrentRow(row)
                break
        assert pane.selected_preset_name() == "我的X"

        pane._on_delete_clicked()

        # 用户文件里没了"我的X"
        raw = json.loads(user_file.read_text(encoding="utf-8"))
        assert "我的X" not in raw

        # 列表 refresh 后选中第一项（系统A）
        assert pane.selected_preset_name() == "系统A"

    def test_delete_canceled_keeps_entry(
        self,
        pane: PresetListPane,
        patched_paths: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, user_file = patched_paths
        original = user_file.read_text(encoding="utf-8")

        self._patch_confirm(monkeypatch, accepted=False)
        pane.refresh()
        for row in range(pane._list.count()):
            if pane._list.item(row).data(preset_list_mod._ROLE_PRESET_ENTRY).name == "我的X":
                pane._list.setCurrentRow(row)
                break

        pane._on_delete_clicked()

        # 取消 → 文件不动
        assert user_file.read_text(encoding="utf-8") == original

    def test_delete_blocked_for_system_preset(
        self,
        pane: PresetListPane,
        patched_paths: tuple[Path, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """防御性：即使按钮状态滞后，调到 _on_delete_clicked 时检测到系统预设也应拒。

        模拟方式：选中系统预设后直接调 _on_delete_clicked（不经过按钮）。
        """
        _, user_file = patched_paths
        original = user_file.read_text(encoding="utf-8")
        self._patch_confirm(monkeypatch, accepted=True)

        pane.refresh()
        pane._list.setCurrentRow(0)  # 系统A
        assert pane.selected_preset_entry().source is PresetSource.SYSTEM

        pane._on_delete_clicked()

        # 文件未变
        assert user_file.read_text(encoding="utf-8") == original


# ──────────────────────────────────────────────────────────────────
# refresh(select_name=...) 行为
# ──────────────────────────────────────────────────────────────────
class TestRefreshSelectName:
    def test_refresh_default_selects_first(
        self, pane: PresetListPane
    ) -> None:
        pane.refresh()
        assert pane.selected_preset_name() == "系统A"

    def test_refresh_with_select_name_picks_that_entry(
        self, pane: PresetListPane
    ) -> None:
        pane.refresh(select_name="我的X")
        assert pane.selected_preset_name() == "我的X"

    def test_refresh_with_empty_string_clears_selection(
        self, pane: PresetListPane
    ) -> None:
        pane.refresh()
        pane.refresh(select_name="")
        assert pane.selected_preset_name() is None

    def test_refresh_with_unknown_name_falls_back_to_first(
        self, pane: PresetListPane
    ) -> None:
        pane.refresh(select_name="不存在的预设")
        assert pane.selected_preset_name() == "系统A"
