"""leeb handlers：里氏硬度工具的 RPC 接口。

RPC 方法（注册时前缀 "leeb."）：
  leeb.run(input_xlsx, output_xlsx=None, angle_degrees=0.0)
    -> {batches, components, output, report_table_data}
       Python 端只算数据返 report_table_data；不写任何 xlsx 文件 —— 输出文件
       由前端串行调 xlsx.write_leeb_report_table（C# sidecar / ClosedXML）创建，
       每批 1 个「报告插入表」sheet。
  leeb.preview_excel(path, sheet=None, header_row=1, max_rows=50)
    -> {sheets, sheet, headers, rows, total_rows, shown_rows}
       前端「中间预览」用：用户改 sheet/header_row 时实时拉前 N 行表格。

业务逻辑全部委派给 core.calc_functions + infra_io.leeb_excel + infra_io.standards_db。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from civ_core.core.calc_functions import calc_leeb_hardness_workbook
from civ_core.infra_io.leeb_excel import read_leeb_workbook
from civ_core.infra_io.standards_db import init_standards_db

__all__ = ["run", "preview_excel"]


_CALC_TYPE_SUFFIX = "里氏"  # 输出文件名里检测类型段；未来加钻芯/回弹时用 calcType 入参推断


def run(
    input_xlsx: str,
    output_xlsx: str | None = None,
    angle_degrees: float = 0.0,
) -> dict:
    """读 Excel → 套规范 → 算硬度 → 返回结构化报告数据（不写文件）。

    output_xlsx=None 时默认 `<input 同级>/<stem>_里氏_结果.xlsx`（带检测类型段防覆盖：
    未来跑钻芯用同一份原始数据时输出文件名不冲突）。
    angle_degrees：全部构件的默认测量角度，沿用 read_leeb_workbook 语义。

    Python 端只算数据；输出 xlsx 完全交给 C# sidecar 的 xlsx.write_leeb_report_table
    创建（用 ClosedXML 写精致格式：合并单元格 / 字体 / 边框）。前端串行调用：
      1. leeb.run → 拿到 report_table_data + 承诺的 output 路径
      2. xlsx.write_leeb_report_table(output_path, report_table_data) → C# 写文件
    """
    from civ_core.infra_io.leeb_excel import _safe_sheet_name

    src = Path(input_xlsx)
    if output_xlsx:
        out = Path(output_xlsx)
    else:
        out = src.parent / f"{src.stem}_{_CALC_TYPE_SUFFIX}_结果.xlsx"

    # 读 workbook → 规范库 → 计算（不写任何 xlsx）
    workbook = read_leeb_workbook(src, default_angle_degrees=angle_degrees)
    db, conn = init_standards_db()
    try:
        result = calc_leeb_hardness_workbook(workbook, db=db)
    finally:
        conn.close()

    # 组装报告表格数据，前端转交 C# 写精致 xlsx
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
        # sheet 名直接 = 批名（没「过程数据」sheet 对照后，"-报告插入表" 后缀失去意义）
        report_table_data.append({
            "sheet_name": _safe_sheet_name(br.batch_name),
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
