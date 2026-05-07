"""preset_manager 单元测试。

覆盖内容：
  • _merge 纯函数：同名覆盖、异名追加、"_" 注释 key 过滤、空输入、保序
  • _read_json_lenient：文件不存在 / JSON 坏 / 非 dict → 兜底返空，不抛
  • _read_json_strict：文件不存在 / JSON 坏 / 非 dict → 抛 PresetError
  • load_merged_presets 集成测试（monkeypatch 路径，避开真实文件系统）
  • DEV_MODE 路径切换：dev.enabled=true 走仓库 fixtures，false 走家目录

测试不动用户家目录：所有 enabled=false 路径用例都通过 monkeypatch Path.home
重定向到 tmp_path 下的伪家目录，避免污染开发机。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from civil_auto.infra_io import preset_manager
from civil_auto.infra_io.preset_manager import (
    PresetError,
    PresetSource,
    _merge,
    _read_json_lenient,
    _read_json_strict,
    load_merged_presets,
    load_merged_presets_as_dict,
)


# ──────────────────────────────────────────────────────────────────
# _merge 纯函数测试（不碰文件系统）
# ──────────────────────────────────────────────────────────────────
class TestMerge:
    """_merge 是合并语义的核心，所有规则都在这里测清楚。"""

    def test_only_system(self) -> None:
        """只有系统预设：全部标 SYSTEM，按文件原序。"""
        sys = {"A": {"x": 1}, "B": {"x": 2}}
        result = _merge(sys, {})
        assert [e.name for e in result] == ["A", "B"]
        assert all(e.source is PresetSource.SYSTEM for e in result)
        assert result[0].data == {"x": 1}

    def test_only_user(self) -> None:
        """只有用户预设：全部标 USER，按文件原序。"""
        user = {"X": {"v": 10}, "Y": {"v": 20}}
        result = _merge({}, user)
        assert [e.name for e in result] == ["X", "Y"]
        assert all(e.source is PresetSource.USER for e in result)

    def test_same_name_user_overrides_at_system_position(self) -> None:
        """同名：用户覆盖系统，**保留在系统的位置上**，source 改为 USER。"""
        sys = {"A": {"v": 1}, "B": {"v": 2}, "C": {"v": 3}}
        user = {"B": {"v": 99}}
        result = _merge(sys, user)

        # 顺序仍是 A B C（B 没换位置）
        assert [e.name for e in result] == ["A", "B", "C"]
        # B 的 data 是用户的，source 是 USER
        b = result[1]
        assert b.source is PresetSource.USER
        assert b.data == {"v": 99}
        # A、C 保持 SYSTEM
        assert result[0].source is PresetSource.SYSTEM
        assert result[2].source is PresetSource.SYSTEM

    def test_different_name_user_appends_to_tail(self) -> None:
        """异名：用户独有的预设按用户文件原序追加到末尾。"""
        sys = {"A": {"v": 1}, "B": {"v": 2}}
        user = {"X": {"v": 10}, "Y": {"v": 20}}
        result = _merge(sys, user)

        assert [e.name for e in result] == ["A", "B", "X", "Y"]
        assert [e.source for e in result] == [
            PresetSource.SYSTEM,
            PresetSource.SYSTEM,
            PresetSource.USER,
            PresetSource.USER,
        ]

    def test_mixed_override_and_append(self) -> None:
        """混合：用户既覆盖了系统某条，又新增了几条。"""
        sys = {"A": {"v": 1}, "B": {"v": 2}, "C": {"v": 3}}
        user = {"B": {"v": 99}, "X": {"v": 10}, "Y": {"v": 20}}
        result = _merge(sys, user)

        assert [e.name for e in result] == ["A", "B", "C", "X", "Y"]
        sources = [e.source for e in result]
        assert sources == [
            PresetSource.SYSTEM,
            PresetSource.USER,  # B 被覆盖
            PresetSource.SYSTEM,
            PresetSource.USER,  # X 追加
            PresetSource.USER,  # Y 追加
        ]
        # B.data 用的是用户值
        assert result[1].data == {"v": 99}

    def test_underscore_keys_filtered_out(self) -> None:
        """以 _ 开头的注释 key（_comment / _field_doc 等）一律不进列表。"""
        sys = {"_comment": "ignore me", "_field_doc": {}, "Real": {"v": 1}}
        user = {"_user_note": "也忽略", "MyPreset": {"v": 2}}
        result = _merge(sys, user)
        assert [e.name for e in result] == ["Real", "MyPreset"]

    def test_empty_inputs(self) -> None:
        """两边都空：返回空 list（不抛）。"""
        assert _merge({}, {}) == []

    def test_does_not_mutate_inputs(self) -> None:
        """合并不能改写入参（防函数式洁癖被破坏）。"""
        sys = {"A": {"v": 1}}
        user = {"A": {"v": 99}}
        sys_snapshot = json.loads(json.dumps(sys))
        user_snapshot = json.loads(json.dumps(user))
        _merge(sys, user)
        assert sys == sys_snapshot
        assert user == user_snapshot


# ──────────────────────────────────────────────────────────────────
# _read_json_lenient 测试（用户预设：失败兜底返空）
# ──────────────────────────────────────────────────────────────────
class TestReadJsonLenient:
    def test_file_missing_returns_empty(self, tmp_path: Path) -> None:
        result = _read_json_lenient(tmp_path / "no_such_file.json")
        assert result == {}

    def test_invalid_json_returns_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        with caplog.at_level("WARNING"):
            result = _read_json_lenient(bad)
        assert result == {}
        # warning 日志应该提到这个文件
        assert any("用户预设 JSON 解析失败" in r.message for r in caplog.records)

    def test_non_dict_root_returns_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 顶层是个 list，不符合预设结构
        weird = tmp_path / "weird.json"
        weird.write_text("[1, 2, 3]", encoding="utf-8")
        with caplog.at_level("WARNING"):
            result = _read_json_lenient(weird)
        assert result == {}

    def test_valid_dict_returned(self, tmp_path: Path) -> None:
        good = tmp_path / "good.json"
        payload = {"My": {"v": 1}}
        good.write_text(json.dumps(payload), encoding="utf-8")
        result = _read_json_lenient(good)
        assert result == payload


# ──────────────────────────────────────────────────────────────────
# _read_json_strict 测试（系统预设：失败抛 PresetError）
# ──────────────────────────────────────────────────────────────────
class TestReadJsonStrict:
    def test_file_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PresetError) as ei:
            _read_json_strict(tmp_path / "missing.json")
        assert "不存在" in str(ei.value)
        assert ei.value.hint  # 必须带 hint

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid", encoding="utf-8")
        with pytest.raises(PresetError) as ei:
            _read_json_strict(bad)
        assert "JSON 解析失败" in str(ei.value)

    def test_non_dict_root_raises(self, tmp_path: Path) -> None:
        weird = tmp_path / "weird.json"
        weird.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(PresetError) as ei:
            _read_json_strict(weird)
        assert "顶层必须是对象" in str(ei.value)

    def test_valid_dict_returned(self, tmp_path: Path) -> None:
        good = tmp_path / "good.json"
        payload = {"Sys": {"v": 1}}
        good.write_text(json.dumps(payload), encoding="utf-8")
        assert _read_json_strict(good) == payload


# ──────────────────────────────────────────────────────────────────
# load_merged_presets 集成测试（monkeypatch 掉路径，避开真实 cfg）
# ──────────────────────────────────────────────────────────────────
class TestLoadMergedPresets:
    """走完整路径：从两个 JSON 文件 → 合并 → 返回 PresetEntry 列表。

    通过 monkeypatch 替换 get_system_presets_path / get_user_presets_path，
    完全避开 load_config，让测试不受真实 config.toml 影响。
    """

    def test_end_to_end_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sys_file = tmp_path / "sys.json"
        sys_file.write_text(
            json.dumps(
                {
                    "_comment": "skip me",
                    "锚杆": {"id_column": "锚杆编号"},
                    "回弹": {"id_column": "构件编号"},
                }
            ),
            encoding="utf-8",
        )
        user_file = tmp_path / "user.json"
        user_file.write_text(
            json.dumps(
                {
                    "锚杆": {"id_column": "我的锚杆编号"},  # 覆盖
                    "我的自定义": {"id_column": "X"},  # 追加
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            preset_manager, "get_system_presets_path", lambda tool="plot_curves": sys_file
        )
        monkeypatch.setattr(
            preset_manager, "get_user_presets_path", lambda tool="plot_curves": user_file
        )

        entries = load_merged_presets("plot_curves")

        assert [e.name for e in entries] == ["锚杆", "回弹", "我的自定义"]
        # 锚杆被用户覆盖
        assert entries[0].source is PresetSource.USER
        assert entries[0].data == {"id_column": "我的锚杆编号"}
        # 回弹保持系统
        assert entries[1].source is PresetSource.SYSTEM
        # 我的自定义是用户独有
        assert entries[2].source is PresetSource.USER

    def test_user_file_missing_falls_back_to_system(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """用户预设文件不存在 → 只返回系统预设，不抛。"""
        sys_file = tmp_path / "sys.json"
        sys_file.write_text(
            json.dumps({"OnlySystem": {"v": 1}}), encoding="utf-8"
        )

        monkeypatch.setattr(
            preset_manager, "get_system_presets_path", lambda tool="plot_curves": sys_file
        )
        monkeypatch.setattr(
            preset_manager,
            "get_user_presets_path",
            lambda tool="plot_curves": tmp_path / "no_such_user_file.json",
        )

        entries = load_merged_presets("plot_curves")
        assert len(entries) == 1
        assert entries[0].name == "OnlySystem"
        assert entries[0].source is PresetSource.SYSTEM

    def test_system_file_missing_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """系统预设文件不存在 → 抛 PresetError。"""
        monkeypatch.setattr(
            preset_manager,
            "get_system_presets_path",
            lambda tool="plot_curves": tmp_path / "no_such_sys.json",
        )
        monkeypatch.setattr(
            preset_manager,
            "get_user_presets_path",
            lambda tool="plot_curves": tmp_path / "no_user.json",
        )
        with pytest.raises(PresetError):
            load_merged_presets("plot_curves")

    def test_load_as_dict_drops_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_merged_presets_as_dict：扁平 {name: data}，丢掉 source 信息。"""
        sys_file = tmp_path / "sys.json"
        sys_file.write_text(json.dumps({"A": {"v": 1}}), encoding="utf-8")
        user_file = tmp_path / "user.json"
        user_file.write_text(json.dumps({"B": {"v": 2}}), encoding="utf-8")
        monkeypatch.setattr(
            preset_manager, "get_system_presets_path", lambda tool="plot_curves": sys_file
        )
        monkeypatch.setattr(
            preset_manager, "get_user_presets_path", lambda tool="plot_curves": user_file
        )
        result = load_merged_presets_as_dict("plot_curves")
        assert result == {"A": {"v": 1}, "B": {"v": 2}}


# ──────────────────────────────────────────────────────────────────
# DEV_MODE 路径切换（loader 联动行为，最关键的双路径开关）
# ──────────────────────────────────────────────────────────────────
class TestDevModeRouting:
    """验证 dev.enabled 切换确实改变了 cfg.paths.user_presets_dir。

    用 tmp_path 写自定义 config.toml 喂给 load_config；
    Path.home() 用 monkeypatch 重定向到 tmp_path 下的伪家目录，
    避免在开发机真实家目录里乱建 .civil_auto_workspace。
    """

    @staticmethod
    def _write_config(cfg_path: Path, dev_enabled: bool) -> None:
        # 路径都用绝对/项目内已有的，避免 mkdir 跑到奇怪地方
        # （loader 会对 templates / data_raw / data_output / logs / user_presets_dir 自动 mkdir）
        cfg_path.write_text(
            f"""
[paths]
templates = "./templates"
curve_presets = "./presets/plot_curves/curve_presets.json"
data_raw = "./data/raw"
data_output = "./data/output"
logs = "./logs"

[dev]
enabled = {str(dev_enabled).lower()}
user_presets_dir = "tests/fixtures/presets"
""",
            encoding="utf-8",
        )

    def test_dev_enabled_routes_to_repo_fixtures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_path = tmp_path / "config.toml"
        self._write_config(cfg_path, dev_enabled=True)

        from civil_auto.configs.loader import load_config

        # 清缓存（@lru_cache）确保读到我们的临时配置
        load_config.cache_clear()
        try:
            cfg = load_config(cfg_path)
            assert cfg.dev.enabled is True
            # 应该指向项目内 tests/fixtures/presets（绝对化后）
            assert cfg.paths.user_presets_dir.name == "presets"
            assert "fixtures" in cfg.paths.user_presets_dir.parts
            assert "tests" in cfg.paths.user_presets_dir.parts
        finally:
            load_config.cache_clear()

    def test_dev_disabled_routes_to_user_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 把 Path.home() 重定向到 tmp_path 下的伪家目录，避免污染真实家目录
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        cfg_path = tmp_path / "config.toml"
        self._write_config(cfg_path, dev_enabled=False)

        from civil_auto.configs.loader import load_config

        load_config.cache_clear()
        try:
            cfg = load_config(cfg_path)
            assert cfg.dev.enabled is False
            expected = (fake_home / ".civil_auto_workspace" / "presets").resolve()
            assert cfg.paths.user_presets_dir == expected
            # loader 对 user_presets_dir 自动 mkdir：跑完应该已存在
            assert cfg.paths.user_presets_dir.is_dir()
        finally:
            load_config.cache_clear()


# ──────────────────────────────────────────────────────────────────
# get_user_presets_path / get_system_presets_path 边界
# ──────────────────────────────────────────────────────────────────
class TestPathGetters:
    def test_unknown_tool_raises(self) -> None:
        with pytest.raises(PresetError):
            preset_manager.get_user_presets_path("not_a_tool")
        with pytest.raises(PresetError):
            preset_manager.get_system_presets_path("not_a_tool")
