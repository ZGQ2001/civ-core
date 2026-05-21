"""plot_curves handlers：绘曲线图工具的 RPC 接口。

RPC 方法（注册时前缀 "plot_curves."）：
  plot_curves.list_presets() -> {presets: [str], default: str | None}
  plot_curves.run(excel_path, preset, output_dir=None, sheet=None, header_row=1)
    -> {written: [str], failed: [{path,error}], summary: {...}, output_dir: str}

第一版同步阻塞跑完返回，无流式进度（见 PROGRESS T5 决策）。
所有业务逻辑委派给 core.plot_curves，本模块只做"参数 dict ↔ 业务对象"映射。
"""

from __future__ import annotations

from pathlib import Path

from civ_core.core.plot_curves import (
    PlotCurvesError,
    get_preset_names,
    load_presets,
    run_plot_curves,
)

# RPC 白名单（详见 server.register_module 的注释）
__all__ = ["list_presets", "run", "preflight"]


def list_presets() -> dict:
    """列出可用预设名（系统 + 用户合并后）。

    返回：
      presets: 预设名列表（过滤掉 _ 开头的注释字段）
      default: 第一个预设名（用作 UI dropdown 默认选中）；空时为 null
    """
    presets = load_presets()
    names = get_preset_names(presets)
    return {
        "presets": names,
        "default": names[0] if names else None,
    }


def run(
    excel_path: str,
    preset: str,
    output_dir: str | None = None,
    sheet: str | None = None,
    header_row: int = 1,
) -> dict:
    """跑一次批量绘图。output_dir=None 时默认 <excel 同级>/曲线图/。

    抛 PlotCurvesError / ExcelReadError 等业务异常会被 dispatcher 包成
    JSON-RPC error 返给前端，前端展示 message 即可（hint 暂未单独透出）。
    """
    excel = Path(excel_path)
    out_dir = Path(output_dir) if output_dir else excel.parent / "曲线图"

    result = run_plot_curves(
        excel_path=excel,
        sheet_name=sheet,
        preset_name=preset,
        output_dir=out_dir,
        header_row=header_row,
    )

    return {
        "written": [str(p) for p in result.written],
        "failed": [
            {"path": str(job.output_path), "error": f"{type(e).__name__}: {e}"}
            for job, e in result.failed
        ],
        "summary": {
            "total": len(result.written) + len(result.failed),
            "written_count": len(result.written),
            "failed_count": len(result.failed),
            "skipped_empty_id": len(result.summary.skipped_empty_id),
            "skipped_bad_data": len(result.summary.skipped_bad_data),
        },
        "output_dir": str(out_dir),
    }


def preflight(
    excel_path: str,
    preset: str,
    sheet: str | None = None,
    header_row: int = 1,
) -> dict:
    """跑前预检：读 Excel 表头 + 检查预设列名是否全匹配。

    返回 {ok, message}；UI 可以在按"跑"之前先调一次给用户提示。
    缺列时 ok=False，message 列出具体缺失的列名。
    """
    from civ_core.core.plot_curves import preflight_check
    from civ_core.infra_io.excel_reader import get_column_headers

    excel = Path(excel_path)
    presets = load_presets()
    if preset not in presets:
        raise PlotCurvesError(
            f"预设 {preset!r} 不存在",
            hint=f"可用预设：{get_preset_names(presets)}",
        )

    cols = get_column_headers(excel, sheet, header_row=header_row)
    ok, message = preflight_check(presets[preset], cols)
    return {"ok": ok, "message": message}
