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
        from civil_auto.configs.loader import load_config

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
        from civil_auto.infra_io.preset_manager import load_merged_presets

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
        from civil_auto.infra_io import preset_manager
        from civil_auto.infra_io.preset_manager import (
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
                copy_system_to_user(
                    source_name, "健康检查复制项", tool="plot_curves"
                )
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

        from civil_auto.main import main

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


def _check_gui_constructible() -> str:
    """GUI 主视图能否被构造（offscreen 平台，不真正显示）。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        from civil_auto.configs.loader import load_config
        from civil_auto.ui.windows.plot_curves_view import PlotCurvesView

        app = QApplication.instance() or QApplication(sys.argv)
        cfg = load_config()
        view = PlotCurvesView(cfg)

        # 验证关键子组件都已就位（防 T-4 重构遗漏）
        missing = []
        if not hasattr(view, "preset_pane"):
            missing.append("预设列表")
        if not hasattr(view, "center_pane"):
            missing.append("中栏 Pivot")
        if not hasattr(view, "settings_pane"):
            missing.append("绘图参数面板")
        if hasattr(view, "center_pane") and not hasattr(
            view.center_pane, "form_panel"
        ):
            missing.append("预设设置表单")

        view.deleteLater()
        del app  # 让 QApplication 实例 ref-count 不被本函数持续持有

        if missing:
            return _fail(
                "GUI 子组件缺失",
                f"未找到：{ '、'.join(missing) }（可能 T-4 接线未完成）",
            )
        return _ok("GUI 启动正常（含 Pivot 双 Tab + 预设设置表单）")
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
    _check_gui_constructible,
]


def main() -> int:
    print("=" * 50)
    print(" Civil Auto Workspace · 健康检查")
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
