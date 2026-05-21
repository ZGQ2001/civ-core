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

__all__ = ["list_presets", "list_sheets", "run", "preflight", "render_preview"]


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


def list_sheets(excel_path: str) -> dict:
    """列举 Excel 的所有 sheet 名，给前端 dropdown 用。

    返回 {sheets: [str]}；文件不存在/打不开抛 ExcelReadError，由 dispatcher
    包成 RPC error 返前端。
    """
    from civ_core.infra_io.excel_reader import read_sheet_names

    return {"sheets": read_sheet_names(Path(excel_path))}


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


def render_preview(
    preset_dict: dict[str, Any],
    excel_path: str,
    sheet: str | None = None,
    header_row: int = 1,
    row_index: int = 0,
) -> dict:
    """实时预览：用 preset_dict + Excel 第 row_index 行数据渲染单张 PNG。

    返回：
      {png_base64: str, mime: "image/png", row_id: str, title: str, total_rows: int}

    前端用 `<img src="data:image/png;base64,${png_base64}">` 直接显示。
    设计选择：base64 比 binary 大 33%，但 JSON-RPC 协议传字节流要走 hex/array
    更费劲；几十 KB 的 PNG 走 base64 完全可接受。

    没有可绘行（全空 / 全跳过）时抛 PlotCurvesError，前端展示 message。
    """
    import base64
    import tempfile

    from civ_core.core.plot_curves import build_jobs
    from civ_core.infra_io.chart_writer import render_plot_to_bytes
    from civ_core.infra_io.excel_reader import read_rows

    excel = Path(excel_path)
    rows = read_rows(excel, sheet, header_row=header_row)
    if not rows:
        raise PlotCurvesError(
            "Excel 没有可读取的数据行",
            hint="请检查 sheet 名 / 表头位置 / 数据是否填写。",
        )

    # build_jobs 需要 output_dir 拼路径（实际不写）；用临时目录占位即可
    with tempfile.TemporaryDirectory() as td:
        jobs, summary = build_jobs(preset_dict, rows, td)

    if not jobs:
        skipped = len(summary.skipped_empty_id) + len(summary.skipped_bad_data)
        raise PlotCurvesError(
            f"没有可绘的行（共 {len(rows)} 行，全部被跳过 / 缺数据；skipped={skipped}）",
            hint="请检查标识列（id_column）是否有值，以及预设要求的列是否都有数据。",
        )

    # 选 row_index，越界时回退到末尾（前端切换 row 时容错）
    idx = min(max(0, row_index), len(jobs) - 1)
    job = jobs[idx]
    png_bytes = render_plot_to_bytes(job)
    # row_data：当前预览图对应的 Excel 行所有列值（让前端展示数据对照）
    # 注意 jobs 已过滤了空 ID / 缺数据行，所以 idx 不能直接索引 rows；
    # 通过 job.output_path.stem（=id 字符串）反查匹配的 row
    row_id_str = job.output_path.stem
    matched_row = _find_row_by_id(rows, preset_dict.get("id_column", ""), row_id_str)
    return {
        "png_base64": base64.b64encode(png_bytes).decode("ascii"),
        "mime": "image/png",
        "row_id": row_id_str,
        "title": job.title,
        "total_rows": len(jobs),
        "row_data": _jsonify_row(matched_row) if matched_row else {},
    }


def _find_row_by_id(rows: list[dict], id_column: str, target_id: str) -> dict | None:
    """按 build_jobs 里的 id 字符串规则反查 row（None/NaN 跳过；int float 去 .0）。"""
    for row in rows:
        raw = row.get(id_column)
        if raw is None or (isinstance(raw, float) and raw != raw):
            continue
        s = str(int(raw)) if isinstance(raw, float) and raw.is_integer() else str(raw).strip()
        if s == target_id:
            return row
    return None


def _jsonify_row(row: dict) -> dict:
    """把 row 的所有值转 JSON-safe（datetime / NaN / bytes 等）。前端只用于显示。"""
    out: dict = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, (int, str, bool)):
            out[k] = v
        elif isinstance(v, float):
            # NaN / inf 在 JSON 里非法；当成 None 处理（前端显示"—"）
            out[k] = v if v == v and v not in (float("inf"), float("-inf")) else None
        else:
            # datetime / Decimal / 其他：toString 兜底
            out[k] = str(v)
    return out
