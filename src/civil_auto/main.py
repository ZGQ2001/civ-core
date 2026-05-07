"""程序唯一入口点：双轨 dispatcher。

调用方式：
  • 不带参数         → 启动 PySide6 主窗口（第二阶段才完整可用）
  • --tool plot_curves → 走轻量 CLI，跑批量绘图（第一阶段最终验收）
  • --list-templates  → 列出可用曲线模板后退出

为什么把 CLI 和 UI 合一个 main：
  • 与 pyproject.toml [project.scripts] 入口 `civil-auto` 一致，避免双入口
  • CLAUDE.md v2.3 第一阶段验收命令固定形如：
        uv run python -m civil_auto.main --tool plot_curves --input ...
  • UI 模块（PySide6 / qfluentwidgets）懒导入，CLI 子分支不会拖动 GUI 依赖
    （也避免 UI 文件还没建好时整个 main 都 import 失败）

退出码约定：
  0  全部成功
  1  部分失败（有 PNG 没写出来，但流程跑完）
  2  整体失败 / 参数错误（异常路径）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 把 src/ 加入 path，确保 civil_auto 包可被子进程 / `python script.py` 形式找到
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ──────────────────────────────────────────────────────────────────
# 参数解析
# ──────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="civil-auto",
        description="土木检测内业自动化工作台。无参数启动 GUI；带 --tool 走 CLI。",
    )
    p.add_argument(
        "--tool",
        choices=["plot_curves"],
        default=None,
        help="指定要跑的工具；省略则启动 GUI（GUI 第二阶段才完整可用）",
    )
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="输入 Excel 路径（plot_curves 必填）",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出目录；省略则用 <input 所在目录>/曲线图/",
    )
    p.add_argument(
        "--sheet",
        default=None,
        help="Sheet 名；省略则用第一个 sheet",
    )
    p.add_argument(
        "--template",
        default=None,
        help="曲线模板名；省略则用模板库里的第一个，并在 stderr 提示",
    )
    p.add_argument(
        "--templates-path",
        type=Path,
        default=None,
        help="自定义模板库 JSON 路径；省略则读 config.toml 的 paths.curve_templates",
    )
    p.add_argument(
        "--header-row",
        type=int,
        default=1,
        help="表头所在行（1-based），默认 1",
    )
    p.add_argument(
        "--list-templates",
        action="store_true",
        help="列出模板库里所有可用模板名后退出",
    )
    return p


# ──────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    """主入口。argv=None 时从 sys.argv 取（pytest 调用时可显式传）。"""
    args = _build_parser().parse_args(argv)

    # CLI 分支：列模板 / 跑工具
    if args.list_templates or args.tool is not None:
        return _run_cli(args)

    # 默认分支：启动 GUI（第二阶段任务，未就绪时给清晰提示）
    return _launch_gui()


# ──────────────────────────────────────────────────────────────────
# GUI 分支（懒导入）
# ──────────────────────────────────────────────────────────────────
def _launch_gui() -> int:
    """启动 PySide6 主窗口。装配细节全部在 app.bootstrap 里。"""
    try:
        from civil_auto.apps.bootstrap import run as run_gui
    except ImportError as e:
        # 这里走到说明 PySide6 / qfluentwidgets 没装。提示用户切 CLI 跑工具。
        sys.stderr.write(
            f"GUI 启动失败：{e}\n"
            "请确认 PySide6 / qfluentwidgets 已安装，或改用 CLI 跑工具：\n"
            "  python -m civil_auto.main --list-templates\n"
            "  python -m civil_auto.main --tool plot_curves --input <xlsx>\n"
        )
        return 2

    return run_gui(sys.argv)


# ──────────────────────────────────────────────────────────────────
# CLI 分支
# ──────────────────────────────────────────────────────────────────
def _run_cli(args: argparse.Namespace) -> int:
    """统一的 CLI 入口：先把日志和审计架起来，再分发到具体工具。"""
    # 启动日志：让控制台看到 INFO 级进度，并保证审计 logger 写到 logs/audit.jsonl
    try:
        from civil_auto.configs.loader import ConfigError, load_config
        from civil_auto.utils.logger import setup_from_config

        cfg = load_config()
        setup_from_config(cfg.logging, cfg.paths.logs)
    except ConfigError as e:
        sys.stderr.write(f"❌ 配置加载失败：{e}\n")
        return 2

    if args.list_templates:
        return _cmd_list_templates(args)

    if args.tool == "plot_curves":
        return _cmd_plot_curves(args)

    # argparse 已限定 choices，理论到不了这里
    sys.stderr.write(f"❌ 未识别的 --tool {args.tool!r}\n")
    return 2


def _cmd_list_templates(args: argparse.Namespace) -> int:
    """列出曲线模板库里的所有模板名（一行一个，便于 shell 管道）。"""
    from civil_auto.core.plot_curves import (
        PlotCurvesError,
        get_template_names,
        load_templates,
    )

    try:
        tpls = load_templates(args.templates_path)
    except PlotCurvesError as e:
        sys.stderr.write(f"❌ 模板库加载失败：{e}\n")
        if e.hint:
            sys.stderr.write(f"建议：{e.hint}\n")
        return 2

    names = get_template_names(tpls)
    if not names:
        sys.stderr.write(
            "⚠️ 模板库为空。请先在 templates/plot_curves/curve_templates.json 添加模板。\n"
        )
        return 0
    for n in names:
        # 走 stdout，便于 `... | head -n 1` 之类的脚本组合
        print(n)
    return 0


def _cmd_plot_curves(args: argparse.Namespace) -> int:
    """plot_curves 子命令：读 Excel → 套模板 → 批量出 PNG。"""
    if args.input is None:
        sys.stderr.write("❌ --tool plot_curves 必须配合 --input <xlsx 路径>\n")
        return 2

    from civil_auto.core.plot_curves import (
        PlotCurvesError,
        get_template_names,
        load_templates,
        run_plot_curves,
    )
    from civil_auto.infra_io.excel_reader import ExcelReadError
    from civil_auto.infra_io.file_manager import FileBusyError, FileWriteError

    # 模板默认值：模板库的第一个
    template_name = args.template
    if template_name is None:
        try:
            tpls = load_templates(args.templates_path)
        except PlotCurvesError as e:
            sys.stderr.write(f"❌ 模板库加载失败：{e}\n")
            if e.hint:
                sys.stderr.write(f"建议：{e.hint}\n")
            return 2
        names = get_template_names(tpls)
        if not names:
            sys.stderr.write("❌ 模板库为空，无法选默认模板。\n")
            return 2
        template_name = names[0]
        sys.stderr.write(f"ℹ️ 未指定 --template，默认使用：{template_name}\n")

    # 输出目录默认值：input 同级 / 曲线图/
    output_dir = args.output if args.output is not None else args.input.parent / "曲线图"

    try:
        result = run_plot_curves(
            excel_path=args.input,
            sheet_name=args.sheet,
            template_name=template_name,
            output_dir=output_dir,
            templates_path=args.templates_path,
            header_row=args.header_row,
        )
    except (PlotCurvesError, ExcelReadError, FileBusyError, FileWriteError) as e:
        # 三段式提示：定位（异常类型）→ 原因（消息）→ 建议（hint）
        sys.stderr.write(f"\n❌ {type(e).__name__}: {e}\n")
        hint = getattr(e, "hint", "") or ""
        if hint:
            sys.stderr.write(f"\n建议：\n{hint}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("\n⚠️ 用户中断。\n")
        return 2

    # 总结（走 stdout，便于脚本捕获；详细进度已经在 logger INFO 里输出）
    print()
    print(f"✅ 成功 {len(result.written)} 张 / 失败 {len(result.failed)} 张")
    print(f"   输出目录：{output_dir}")
    print("   审计日志：logs/audit.jsonl")

    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
