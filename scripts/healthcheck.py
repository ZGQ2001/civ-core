"""项目健康检查脚本。

每次验收后用户运行：

    uv run python scripts/healthcheck.py

输出格式：纯中文通过/失败，让用户能快速看清功能是否正常。
失败项后跟 → 提示，告诉用户该怎么处理。

设计取舍：
  • 不引外部断言库；失败用 ❌ + 一行原因，成功用 ✅
  • 不抛异常 —— 检查项内部捕获到底，让用户看完整张报告
  • 不打到 logs/app.log（healthcheck 不是业务流，不污染日志）
  • 退出码：全部通过 = 0；任一失败 = 1（CI / 自动化能识别）

历史：2026-05-20 起 UI 走 Tauri，删了 5 个 Qt UI 检查项；新增 api server
端到端 round-trip 一项，覆盖新前端调用的 JSON-RPC 后端。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Callable

# Windows 控制台默认 GBK 编不了 ✅/❌；强制 stdout 走 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _ok(message: str) -> str:
    return f"✅ {message}"


def _fail(message: str, hint: str = "") -> str:
    if hint:
        return f"❌ {message} → {hint}"
    return f"❌ {message}"


# ──────────────────────────────────────────────────────────────────
def _check_config_loadable() -> str:
    try:
        from civ_core.configs.loader import load_config

        cfg = load_config()
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
    try:
        from civ_core.infra_io import preset_manager
        from civ_core.infra_io.preset_manager import (
            copy_system_to_user,
            delete_user_preset,
            load_merged_presets_as_dict,
            save_user_preset,
        )

        with tempfile.TemporaryDirectory() as td:
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

                merged = load_merged_presets_as_dict("plot_curves")
                if not merged:
                    return _fail("没有系统预设可作复制源")
                source_name = next(iter(merged.keys()))
                copy_system_to_user(source_name, "健康检查复制项", tool="plot_curves")
                if "健康检查复制项" not in load_merged_presets_as_dict("plot_curves"):
                    return _fail("用户预设复制后读不到")
                delete_user_preset("健康检查复制项", tool="plot_curves")
            finally:
                preset_manager.get_user_presets_path = original_getter  # type: ignore

        return _ok("用户预设保存/删除/复制功能正常")
    except Exception as e:
        return _fail("用户预设写入功能异常", f"原因：{e}")


def _check_cli_list_presets() -> str:
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

        if not buf.getvalue().strip():
            return _fail("CLI 列出预设无输出", "可能是 main 函数实现变更")
        return _ok("CLI 出图模块（--list-presets）正常")
    except Exception as e:
        return _fail("CLI 出图模块异常", f"原因：{e}")


def _check_standards_db_calc_pipeline() -> str:
    """规范库（standards.db）+ Python 端计算函数端到端 round-trip。

    INSP-001 里氏硬度已迁 C# sidecar（civ-doc），由 dotnet test 验证；本检查只测
    Python 端保留的 INSP-002 钻芯法 + Python seed 写入规范库正确。
    """
    try:
        import sqlite3

        from civ_core.core.calc_functions import calc_core_drilling_concrete
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
                seed_all_leeb_tables(db)  # 仍 seed —— C# sidecar 读这份数据

                # 钻芯法（Python 端业务，未迁 C#）端到端
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

                # 里氏硬度三表行数（C# 端会读这些；保证 seed 写入正确）
                leeb_rows = db.list_rows("leeb_thickness_correction")
                if len(leeb_rows) != 6:
                    return _fail(
                        "里氏硬度厚度修正表行数异常",
                        f"应 6 行，实际 {len(leeb_rows)}（C# sidecar 会读这份）",
                    )
            finally:
                conn.close()

        return _ok("规范库 + 钻芯法计算正常；里氏硬度三表已 seed (C# sidecar 读)")
    except Exception as e:
        return _fail("规范库计算管线异常", f"原因：{e}")


def _check_api_dispatcher() -> str:
    """api JSON-RPC dispatcher：ping + plot_curves 注册存在性。

    T5.7 后 workspace/files/pdf_tools/word2pdf 全迁 C# sidecar；Python dispatcher
    只剩 plot_curves + ping/version。C# 侧的 round-trip 由 dotnet test 覆盖
    （dotnet/civ-doc.Tests/ 下 ~180 个 xUnit），healthcheck 只验 Python 还活着。
    """
    try:
        import json

        from civ_core.api.__main__ import build_dispatcher

        d = build_dispatcher()

        # ping round-trip 确认 dispatcher 工作
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        resp = json.loads(d.handle_raw(req))
        if resp.get("result") != "pong":
            return _fail("api ping 异常", f"得到 {resp}")

        # plot_curves 关键方法必须注册（Python 端唯一保留的业务域）
        methods = set(d.methods())
        required = {"plot_curves.list_presets", "plot_curves.run"}
        missing = required - methods
        if missing:
            return _fail("plot_curves 方法注册缺失", f"缺：{missing}")

        return _ok("api dispatcher 正常（ping round-trip + plot_curves 注册齐全）")
    except Exception as e:
        return _fail("api dispatcher 异常", f"原因：{e}")


# ──────────────────────────────────────────────────────────────────
CHECKS: list[Callable[[], str]] = [
    _check_config_loadable,
    _check_system_presets_readable,
    _check_user_preset_writable,
    _check_cli_list_presets,
    _check_standards_db_calc_pipeline,
    _check_api_dispatcher,
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
