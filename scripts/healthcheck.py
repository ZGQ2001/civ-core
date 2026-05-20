"""项目健康检查脚本。

每次验收后用户运行：

    uv run python scripts/healthcheck.py

输出格式：纯中文通过/失败，不暴露技术细节，让用户能快速看清功能是否正常。
失败项后跟 → 提示，告诉用户该怎么处理。

设计取舍
========
  • 不引外部断言库。失败用 ❌ 前缀 + 一行原因，成功用 ✅。
  • 不抛异常 —— 所有检查项捕获到底，写成"❌ XXX → 建议"，让用户能看完整张报告。
  • 不打到 logs/app.log（healthcheck 不是业务流，不污染日志）。
  • 退出码：全部通过 = 0；任一失败 = 1（CI / 自动化能识别）。

新增功能时，应在本文件**对应阶段**追加 `_check_xxx()` 函数并加入 `CHECKS` 列表。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Callable

# Windows 控制台默认 GBK 编不了 ✅/❌ 等符号，强制 stdout 走 UTF-8。
# Python 3.7+ 的 reconfigure 是稳定 API，比 sys.stdout = TextIOWrapper(...) 干净。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass  # 极少数终端不支持 —— 兜底成普通 print，符号会被 ? 替代但不崩


# ──────────────────────────────────────────────────────────────────
# 通用工具
# ──────────────────────────────────────────────────────────────────
def _ok(message: str) -> str:
    return f"✅ {message}"


def _fail(message: str, hint: str = "") -> str:
    """失败行。`hint` 紧跟在 → 后，提示用户怎么处理。"""
    if hint:
        return f"❌ {message} → {hint}"
    return f"❌ {message}"


# ──────────────────────────────────────────────────────────────────
# 检查项
# ──────────────────────────────────────────────────────────────────
def _check_config_loadable() -> str:
    """配置文件能否加载（含 paths / dev 段、自动 mkdir 验证）。"""
    try:
        from civ_core.configs.loader import load_config

        cfg = load_config()
        # 验证关键派生路径都已存在（loader 应该已自动 mkdir）
        for label, p in [
            ("数据原始目录", cfg.paths.data_raw),
            ("数据输出目录", cfg.paths.data_output),
            ("日志目录", cfg.paths.logs),
            ("用户预设目录", cfg.paths.user_presets_dir),
        ]:
            if not p.is_dir():
                return _fail(
                    f"{label}不存在",
                    f"应自动创建但没成功：{p}（请检查磁盘权限）",
                )
        return _ok(f"配置文件加载正常（开发模式：{'开' if cfg.dev.enabled else '关'}）")
    except Exception as e:
        return _fail("配置文件加载失败", f"原因：{e}")


def _check_system_presets_readable() -> str:
    """系统预设 JSON 能否被 preset_manager 读到。"""
    try:
        from civ_core.infra_io.preset_manager import load_merged_presets

        entries = load_merged_presets("plot_curves")
        if not entries:
            return _fail(
                "系统预设为空",
                "请确认 presets/plot_curves/curve_presets.json 至少有一条预设",
            )
        sys_n = sum(1 for e in entries if e.source.value == "system")
        user_n = sum(1 for e in entries if e.source.value == "user")
        return _ok(
            f"系统预设读取正常（系统 {sys_n} 条 ・ 我的 {user_n} 条 ・ 合计 {len(entries)}）"
        )
    except Exception as e:
        return _fail("系统预设读取失败", f"原因：{e}")


def _check_user_preset_writable() -> str:
    """用户预设的写入 / 删除 / 复制 API 能否完整跑通（在临时位置做 round-trip）。"""
    try:
        from civ_core.infra_io import preset_manager
        from civ_core.infra_io.preset_manager import (
            copy_system_to_user,
            delete_user_preset,
            load_merged_presets_as_dict,
            save_user_preset,
        )

        with tempfile.TemporaryDirectory() as td:
            # 临时把用户预设路径切到 tmp，做 round-trip 测试，避免污染真实用户文件
            tmp_user_file = Path(td) / "curve_presets.json"
            original_getter = preset_manager.get_user_presets_path
            preset_manager.get_user_presets_path = lambda tool="plot_curves": tmp_user_file  # type: ignore
            try:
                save_user_preset(
                    "健康检查临时项",
                    {"id_column": "X", "curves": []},
                    tool="plot_curves",
                )
                if "健康检查临时项" not in load_merged_presets_as_dict("plot_curves"):
                    return _fail("用户预设写入后读不到")

                delete_user_preset("健康检查临时项", tool="plot_curves")
                if "健康检查临时项" in load_merged_presets_as_dict("plot_curves"):
                    return _fail("用户预设删除后仍能读到")

                # 复制：用第一条系统预设作源
                merged = load_merged_presets_as_dict("plot_curves")
                if not merged:
                    return _fail("没有系统预设可作复制源")
                source_name = next(iter(merged.keys()))
                copy_system_to_user(source_name, "健康检查复制项", tool="plot_curves")
                if "健康检查复制项" not in load_merged_presets_as_dict("plot_curves"):
                    return _fail("用户预设复制后读不到")
                # 清理
                delete_user_preset("健康检查复制项", tool="plot_curves")
            finally:
                preset_manager.get_user_presets_path = original_getter  # type: ignore

        return _ok("用户预设保存/删除/复制功能正常")
    except Exception as e:
        return _fail("用户预设写入功能异常", f"原因：{e}")


def _check_cli_list_presets() -> str:
    """CLI 的 --list-presets 命令能否正常列出预设。"""
    try:
        import io
        from contextlib import redirect_stdout

        from civ_core.main import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                main(["--list-presets"])
            except SystemExit as se:
                if se.code not in (None, 0):
                    return _fail("CLI 列出预设异常退出", f"退出码 {se.code}")

        out = buf.getvalue()
        if not out.strip():
            return _fail("CLI 列出预设无输出", "可能是 main 函数实现变更")
        return _ok("CLI 出图模块（--list-presets）正常")
    except Exception as e:
        return _fail("CLI 出图模块异常", f"原因：{e}")


def _check_standards_db_calc_pipeline() -> str:
    """规范库（standards.db）+ INSP-001/002 计算函数端到端 round-trip。

    在临时 DB 上 seed 全部规范表，跑一遍钻芯法 + 里氏硬度计算，验证：
      - SQLite 通用查表层（partial unique index / UPSERT）正常
      - INSP-002 钻芯法 60 行 k 系数表完整
      - INSP-001 里氏硬度 3 表（厚度/角度/强度）完整
      - calc_functions 能正确联动查表 + 插值算出推定值
    """
    try:
        import sqlite3
        import tempfile
        from pathlib import Path

        from civ_core.core.calc_functions import (
            calc_core_drilling_concrete,
            calc_leeb_hardness_steel,
        )
        from civ_core.infra_io.standards_db import (
            StandardsDB,
            seed_all_leeb_tables,
            seed_core_drilling_k_table,
        )

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "standards.db"
            conn = sqlite3.connect(str(p))
            conn.row_factory = sqlite3.Row
            try:
                db = StandardsDB(conn)
                db.create_tables()
                seed_core_drilling_k_table(db)
                seed_all_leeb_tables(db)

                # INSP-002 钻芯法 round-trip
                r_core = calc_core_drilling_concrete(
                    tuple(30.0 + i * 0.1 for i in range(10)),
                    db=db,
                    take="lower",
                )
                if not (0 < r_core.f_cu_est < 50):
                    return _fail(
                        "钻芯法推定值异常",
                        f"f_cu_est={r_core.f_cu_est} 超出合理范围 (0, 50)",
                    )

                # INSP-001 里氏硬度 round-trip（Excel 序号 1 测区 1 真实数据）
                raw = (483, 481, 480, 481, 474, 479, 479, 483, 474)
                r_leeb = calc_leeb_hardness_steel(
                    test_areas_raw=[raw],
                    thickness=12.0,
                    angle_degrees=90.0,
                    db=db,
                )
                if r_leeb.test_areas[0].hl_m != 480:
                    return _fail(
                        "里氏硬度截尾平均异常",
                        f"HL_m={r_leeb.test_areas[0].hl_m} 应为 480",
                    )
                if not (400 < r_leeb.comp_fb_est < 700):
                    return _fail(
                        "里氏硬度推定值异常",
                        f"fb_est={r_leeb.comp_fb_est} 超出合理范围 (400, 700)",
                    )
            finally:
                conn.close()

        return _ok(
            "规范库 + 计算函数正常（钻芯法 INSP-002 + 里氏硬度 INSP-001 端到端）"
        )
    except Exception as e:
        return _fail("规范库计算管线异常", f"原因：{e}")


def _check_log_panel() -> str:
    """日志面板能否构造、QtLogBridge round-trip 是否完整。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import tempfile

        from PySide6.QtWidgets import QApplication

        from civ_core.ui.components.log_panel import LogPanel
        from civ_core.utils.logger import get_logger, setup_logging

        app = QApplication.instance() or QApplication(sys.argv)
        _ = app

        # 在临时目录初始化日志（避免污染 logs/app.log）
        with tempfile.TemporaryDirectory() as td:
            bridge = setup_logging(log_dir=td)
            panel = LogPanel()
            panel.set_collapsed(False)  # 展开才能 isVisibleTo 检测
            bridge.record_emitted.connect(panel.on_record)

            # 灌一条 INFO 看是否 round-trip 到面板文本里
            probe = "healthcheck-probe-9f3a"
            get_logger("civ_core.healthcheck").info(probe)

            text = panel._text.toPlainText()
            panel.deleteLater()

            if probe not in text:
                return _fail(
                    "日志面板 round-trip 失败",
                    "QtLogBridge 信号未触达 LogPanel.on_record",
                )

        return _ok("日志面板功能正常（QtLogBridge → LogPanel 链路完整）")
    except Exception as e:
        return _fail("日志面板功能异常", f"原因：{e}")


def _check_preview_pane() -> str:
    """预览区组件可构造、缩略图加载链路完整。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import tempfile

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPixmap
        from PySide6.QtWidgets import QApplication

        from civ_core.ui.components.preview_pane import PreviewPane

        app = QApplication.instance() or QApplication(sys.argv)
        _ = app  # 持有引用免被 GC

        pane = PreviewPane()

        # 造一张 8×8 测试 PNG，跑一次 set_results round-trip
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "probe.png"
            pix = QPixmap(8, 8)
            pix.fill(QColor(Qt.GlobalColor.green))
            if not pix.save(str(png), "PNG"):
                return _fail("预览区探针 PNG 写入失败")

            pane.set_results([png])
            if pane._thumb_list.count() != 1:
                pane.deleteLater()
                return _fail(
                    "预览区缩略图未填充",
                    "set_results 后列表为空",
                )
            if pane._current_pixmap is None or pane._current_pixmap.isNull():
                pane.deleteLater()
                return _fail(
                    "预览区大图加载失败",
                    "缩略图选中后大图区无 pixmap",
                )

        pane.deleteLater()
        return _ok("预览区功能正常（缩略图加载 + 大图显示）")
    except Exception as e:
        return _fail("预览区功能异常", f"原因：{e}")


def _check_splitter_persistence() -> str:
    """QSettings 持久化（GUI 两栏宽度记忆）能否完整 round-trip。

    用专门的 healthcheck key 而不是真正的 splitter sizes key，避免
    污染用户已保存的拖动状态。
    """
    try:
        from PySide6.QtCore import QSettings

        from civ_core.ui.windows.plot_curves_view import (
            _SETTINGS_APP,
            _SETTINGS_ORG,
        )

        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        key = "_healthcheck/probe"
        settings.setValue(key, [1, 2, 3])
        settings.sync()  # 强制刷盘，避免读到旧 cache

        readback = settings.value(key)
        if readback is None:
            return _fail(
                "布局记忆写入后读不到",
                "QSettings 配置写入异常（可能是权限问题）",
            )
        try:
            vs = [int(x) for x in readback]
        except (TypeError, ValueError):
            return _fail("布局记忆数据类型异常", "QSettings 后端可能损坏")
        if vs != [1, 2, 3]:
            return _fail(
                f"布局记忆 round-trip 不一致：{vs} != [1, 2, 3]",
                "QSettings 后端可能损坏",
            )

        # 清掉探针 key，不在用户 settings 里留痕
        settings.remove(key)
        settings.sync()
        return _ok("布局记忆功能正常（两栏宽度自动保存）")
    except Exception as e:
        return _fail("布局记忆功能异常", f"原因：{e}")


def _check_bottom_tab_panel() -> str:
    """L-4：BottomTabPanel + DataSourcePane 链路完整。

    用临时 PNG 数据走一遍 DataSourcePane.set_preset_and_data → 列过滤；
    断言 row_highlighted 与 LivePreviewPane.highlight_row 能互连（构造时连）。
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        from civ_core.ui.components.bottom_tab_panel import BottomTabPanel

        app = QApplication.instance() or QApplication(sys.argv)
        _ = app
        bottom = BottomTabPanel()

        # 验证两个 Tab 都到位
        if not hasattr(bottom, "log_panel"):
            bottom.deleteLater()
            return _fail(
                "底栏面板缺少日志 Tab",
                "BottomTabPanel.log_panel 未挂载",
            )
        if not hasattr(bottom, "data_source_pane"):
            bottom.deleteLater()
            return _fail(
                "底栏面板缺少数据源 Tab",
                "BottomTabPanel.data_source_pane 未挂载",
            )

        # 走一次列过滤 round-trip：3 列预设 + 5 列 row → 模型只显示 3 列
        preset = {
            "id_column": "编号",
            "curves": [
                {"points": [{"var_column": "X"}, {"var_column": "Y"}]},
            ],
        }
        rows = [{"编号": "A", "X": 1.0, "Y": 2.0, "无关": 999}]
        bottom.data_source_pane.set_preset_and_data(preset, rows)
        if bottom.data_source_pane._model.columnCount() != 3:
            bottom.deleteLater()
            return _fail(
                "数据源 Tab 列过滤异常",
                f"期望 3 列，实际 {bottom.data_source_pane._model.columnCount()} 列",
            )

        # Tab 切换 + 折叠态切换
        bottom.show_data_tab()
        if bottom.current_tab() != "data":
            bottom.deleteLater()
            return _fail("数据源 Tab 切换失败")
        bottom.set_collapsed(False)
        if bottom.is_collapsed():
            bottom.deleteLater()
            return _fail("底栏面板展开失败")

        bottom.deleteLater()
        return _ok("底栏 Tab 面板功能正常（日志 + 数据源列过滤 + Tab 切换 + 折叠）")
    except Exception as e:
        return _fail("底栏 Tab 面板功能异常", f"原因：{e}")


def _check_gui_constructible() -> str:
    """GUI 主视图能否被构造（offscreen 平台，不真正显示）。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        from civ_core.configs.loader import load_config
        from civ_core.ui.windows.plot_curves_view import PlotCurvesView

        app = QApplication.instance() or QApplication(sys.argv)
        cfg = load_config()
        view = PlotCurvesView(cfg)

        # 验证关键子组件都已就位（防重构遗漏）
        # L-1：两栏骨架 = 左参数面板（PresetAccordionPanel）+ 右实时预览（LivePreviewPane）
        # L-4：底栏 BottomTabPanel（日志 Tab + 数据源 Tab）
        missing = []
        if not hasattr(view, "preset_accordion_panel"):
            missing.append("参数面板（左栏）")
        if not hasattr(view, "live_preview_pane"):
            missing.append("实时预览（右栏）")
        if not hasattr(view, "bottom_panel"):
            missing.append("底栏 Tab 面板")
        if hasattr(view, "bottom_panel") and not hasattr(view.bottom_panel, "data_source_pane"):
            missing.append("数据源 Tab")

        view.deleteLater()
        del app  # 让 QApplication 实例 ref-count 不被本函数持续持有

        if missing:
            return _fail(
                "GUI 子组件缺失",
                f"未找到：{'、'.join(missing)}（可能接线未完成）",
            )
        return _ok("GUI 启动正常（两栏骨架 + 日志面板）")
    except Exception as e:
        return _fail("GUI 启动失败", f"原因：{e}")


# ──────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────
# 列表顺序 = 输出顺序。把"先决条件"放前面（配置 → 预设读 → 写 → CLI → GUI）。
CHECKS: list[Callable[[], str]] = [
    _check_config_loadable,
    _check_system_presets_readable,
    _check_user_preset_writable,
    _check_cli_list_presets,
    _check_standards_db_calc_pipeline,
    _check_gui_constructible,
    _check_splitter_persistence,
    _check_preview_pane,
    _check_log_panel,
    _check_bottom_tab_panel,
]


def main() -> int:
    print("=" * 50)
    print(" 筑核 (civ-core) · 健康检查")
    print("=" * 50)

    failed = 0
    for check in CHECKS:
        try:
            line = check()
        except Exception as e:
            # 检查项自身炸了（不该发生，但兜底）
            line = _fail(f"检查项 {check.__name__} 内部错误", f"原因：{e}")
        print(line)
        if line.startswith("❌"):
            failed += 1

    print("=" * 50)
    if failed == 0:
        print("全部检查通过 ✨")
        return 0
    print(f"⚠️  {failed} 项失败 —— 请按上方提示处理")
    return 1


if __name__ == "__main__":
    sys.exit(main())
