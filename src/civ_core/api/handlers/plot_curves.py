"""plot_curves handlers：绘曲线图工具的 RPC 接口。

RPC 方法（前缀 "plot_curves."）：
  plot_curves.list_presets()
    -> {presets: [str], default: str | None, details: {name: dict, ...}}
       details 一并返回每个预设的完整 JSON，UI 工具设置 Tab 直接用
  plot_curves.run(excel_path, preset, output_dir=None, sheet=None,
                  header_row=1, preset_override=None)
    -> {written: [str], failed: [...], summary: {...}, output_dir: str}
  plot_curves.preflight(excel_path, preset, sheet=None, header_row=1)
    -> {ok, message}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from civ_core.core.plot_curves import (
    PlotCurvesError,
    get_preset_names,
    load_presets,
    run_plot_curves,
)

__all__ = ["list_presets", "run", "preflight"]


def list_presets() -> dict:
    """列出可用预设 + 每个预设的完整 JSON 详情。

    details 字段让 UI"工具设置"Tab 不必再二次 RPC 拿详情；缺点是返回体大，
    但预设库本身就几个 KB，可接受。
    """
    presets = load_presets()
    names = get_preset_names(presets)
    return {
        "presets": names,
        "default": names[0] if names else None,
        "details": {name: presets[name] for name in names},
    }


def run(
    excel_path: str,
    preset: str,
    output_dir: str | None = None,
    sheet: str | None = None,
    header_row: int = 1,
    preset_override: dict[str, Any] | None = None,
) -> dict:
    """跑一次批量绘图。

    preset_override 给值时完全覆盖预设字典（UI 编辑过的预设 JSON），
    None 时用预设库里的原始预设。
    """
    excel = Path(excel_path)
    out_dir = Path(output_dir) if output_dir else excel.parent / "曲线图"

    result = run_plot_curves(
        excel_path=excel,
        sheet_name=sheet,
        preset_name=preset,
        output_dir=out_dir,
        header_row=header_row,
        preset_override=preset_override,
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
    """跑前预检：读 Excel 表头 + 检查预设列名是否全匹配。"""
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
