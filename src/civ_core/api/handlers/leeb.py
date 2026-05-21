"""leeb handlers：INSP-001 里氏硬度工具的 RPC 接口。

RPC 方法（注册时前缀 "leeb."）：
  leeb.run(input_xlsx, output_xlsx=None, angle_degrees=0.0)
    -> {batches: int, components: int, output: str}

业务逻辑全部委派给 core.calc_functions + infra_io.leeb_excel + infra_io.standards_db。
"""

from __future__ import annotations

from pathlib import Path

from civ_core.core.calc_functions import calc_leeb_hardness_workbook
from civ_core.infra_io.leeb_excel import read_leeb_workbook, write_leeb_results_workbook
from civ_core.infra_io.standards_db import init_standards_db

__all__ = ["run"]


def run(
    input_xlsx: str,
    output_xlsx: str | None = None,
    angle_degrees: float = 0.0,
) -> dict:
    """读 Excel → 套规范 → 算硬度 → 写结果 Excel。

    output_xlsx=None 时默认 <input 同级>/<stem>_结果.xlsx。
    angle_degrees：全部构件的默认测量角度，沿用 read_leeb_workbook 语义。
    """
    src = Path(input_xlsx)
    if output_xlsx:
        out = Path(output_xlsx)
    else:
        out = src.parent / f"{src.stem}_结果.xlsx"

    # 读 workbook → 规范库 → 计算 → 写出
    workbook = read_leeb_workbook(src, default_angle_degrees=angle_degrees)
    db, conn = init_standards_db()
    try:
        result = calc_leeb_hardness_workbook(workbook, db=db)
    finally:
        conn.close()
    write_leeb_results_workbook(out, result, angle_degrees=angle_degrees)

    return {
        "batches": result.n_batches,
        "components": result.n_components_total,
        "output": str(out),
    }
