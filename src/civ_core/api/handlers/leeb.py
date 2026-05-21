"""leeb handlers：里氏硬度工具的 RPC 接口。

RPC 方法（注册时前缀 "leeb."）：
  leeb.run(input_xlsx, output_xlsx=None, angle_degrees=0.0)
    -> {batches, components, output, report_table_data}
       output xlsx 仅写「过程数据」sheet（精致版「报告插入表」交给 C# sidecar）。
       report_table_data 给前端串行调 xlsx.write_leeb_report_table 用。
  leeb.preview_excel(path, sheet=None, header_row=1, max_rows=50)
    -> {sheets, sheet, headers, rows, total_rows, shown_rows}
       前端「中间预览」用：用户改 sheet/header_row 时实时拉前 N 行表格。

业务逻辑全部委派给 core.calc_functions + infra_io.leeb_excel + infra_io.standards_db。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from civ_core.core.calc_functions import calc_leeb_hardness_workbook
from civ_core.infra_io.leeb_excel import read_leeb_workbook, write_leeb_results_workbook
from civ_core.infra_io.standards_db import init_standards_db

__all__ = ["run", "preview_excel"]


def run(
    input_xlsx: str,
    output_xlsx: str | None = None,
    angle_degrees: float = 0.0,
) -> dict:
    """读 Excel → 套规范 → 算硬度 → 写「过程数据」sheet。

    output_xlsx=None 时默认 <input 同级>/<stem>_结果.xlsx。
    angle_degrees：全部构件的默认测量角度，沿用 read_leeb_workbook 语义。

    返回里加 report_table_data：前端拿到后串行调 xlsx.write_leeb_report_table（C# sidecar），
    用 ClosedXML 把「报告插入表」sheet 追加到同一文件（合并单元格 / 字体 / 边框等精致格式）。
    """
    from civ_core.infra_io.leeb_excel import _safe_sheet_name

    src = Path(input_xlsx)
    if output_xlsx:
        out = Path(output_xlsx)
    else:
        out = src.parent / f"{src.stem}_结果.xlsx"

    # 读 workbook → 规范库 → 计算 → 写出（不写报告插入表，交给 C#）
    workbook = read_leeb_workbook(src, default_angle_degrees=angle_degrees)
    db, conn = init_standards_db()
    try:
        result = calc_leeb_hardness_workbook(workbook, db=db)
    finally:
        conn.close()
    write_leeb_results_workbook(
        out,
        result,
        angle_degrees=angle_degrees,
        include_report_sheet=False,
    )

    # 组装报告表格数据，前端转交 C# sidecar 写精致版「报告插入表」
    report_table_data = []
    for br in result.batch_results:
        components = []
        for comp_input, comp_result in br.components_with_results:
            components.append({
                "name": comp_input.name,
                "thickness_mm": comp_input.thickness,
                "test_areas_raw": [list(area) for area in comp_input.test_areas_raw],
                "comp_fb_min_avg": comp_result.comp_fb_min_avg,
            })
        report_table_data.append({
            "sheet_name": _safe_sheet_name(f"{br.batch_name}-报告插入表"),
            "components": components,
            "batch_fb_char_avg": br.batch_fb_char_avg,
        })

    return {
        "batches": result.n_batches,
        "components": result.n_components_total,
        "output": str(out),
        "report_table_data": report_table_data,
    }


def preview_excel(
    path: str,
    sheet: str | None = None,
    header_row: int = 1,
    max_rows: int = 50,
) -> dict:
    """读 Excel 前 max_rows 行，给前端「中间预览」展示。

    - sheets 全列表 + 实际用的 sheet 名（让 UI 回显，处理"传了不存在的 sheet"的兜底）
    - 表头用 get_column_headers 单独读（read_rows 返回的 dict key 可能因首行某列空缺而漏列）
    - rows 截前 max_rows 条；total_rows 是没截的总数，UI 显示「X 行已显示 / 共 Y 行」
    """
    from civ_core.infra_io.excel_reader import (
        get_column_headers,
        read_rows,
        read_sheet_names,
    )

    src = Path(path)
    sheets = read_sheet_names(src)
    if not sheets:
        return {
            "sheets": [],
            "sheet": "",
            "headers": [],
            "rows": [],
            "total_rows": 0,
            "shown_rows": 0,
        }
    actual_sheet = sheet if sheet and sheet in sheets else sheets[0]

    headers = get_column_headers(src, actual_sheet, header_row=header_row)
    all_rows = read_rows(src, actual_sheet, header_row=header_row)
    cap = max(1, max_rows)
    preview = all_rows[:cap]
    return {
        "sheets": sheets,
        "sheet": actual_sheet,
        "headers": headers,
        "rows": [_jsonify_row(r) for r in preview],
        "total_rows": len(all_rows),
        "shown_rows": len(preview),
    }


def _jsonify_row(row: dict[str, Any]) -> dict[str, Any]:
    """把 openpyxl 原生值转 JSON-safe（NaN/datetime/Decimal 等）。仅显示用。"""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, (int, str, bool)):
            out[k] = v
        elif isinstance(v, float):
            out[k] = v if v == v and v not in (float("inf"), float("-inf")) else None
        else:
            out[k] = str(v)
    return out
