"""里氏硬度报检单 Excel 导入 / 导出。

为什么独立成 leeb_excel.py 而不复用 excel_reader.py：
  - excel_reader 是「绘曲线图」专用的通用 Excel 读取（按表头取列）
  - 里氏硬度报检单是「每构件 3 行 9 列」的固定结构 + 首行带元信息（序号/构件名/厚度）
    后两行只有 9 个 HL 测点，需要专门的"按构件分组读取"逻辑
  - 与其在 excel_reader 加 if-else 分支，不如独立一个语义清晰的模块

报检单 Excel 格式（参考 data/training_materials/防火厚度报检单(D号站房)新.xlsx
                  「里氏硬度（钢柱）」sheet）：

    | 序号 | 构件位置 | HL1 | HL2 | ... | HL9 | 厚度 | 抗拉特征值 | 平均值 | ... | 检测批 |
    |  1  | 2×H钢柱  | 467 | 465 | ... | 463 | 16   | (Excel公式) | ...   | ... | 检测批1 |
    |     |          | 471 | 478 | ... | 465 |      |             |       |     |        |
    |     |          | 477 | 481 | ... | 462 |      |             |       |     |        |
    |  2  | 2×J钢柱  | ...                                                                |

  • 序号 / 构件位置 / 厚度 / 检测批 仅在每构件第 1 行有值；后 2 行的对应单元格为 None
  • HL 9 列每行都有值（即每测区 9 个测点单独一行）

测量角度（angle_degrees）报检单 Excel 中通常不显式列出（钢柱默认向下 90°）；
由调用方（UI 层）作为全局参数传入，本模块不负责猜测。

写入：
  output_workbook 写两张 sheet：
    Sheet「原始数据」复制输入构件清单（按报检单格式）
    Sheet「计算结果」每行一个测区，列：序号 / 构件 / 测区号 / HL_m / HL_t / HL_a / HL_corr / fb_min / fb_max
    并在底部追加批级 fb_char_avg
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

from civ_core.domain.calc_schema import (
    LeebHardnessBatchResult,
    LeebHardnessComponentInput,
)
from civ_core.utils.exceptions import InfraIOError, InputError
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ── 报检单列位置（按 D 号站房格式锁定；其他格式可扩展为参数）────
_COL_SEQ = 1            # A: 序号
_COL_NAME = 2           # B: 构件位置
_COL_HL_START = 3       # C..K: HL1..HL9 (9 列)
_COL_HL_COUNT = 9
_COL_THICKNESS = 12     # L: 厚度
_COL_BATCH = 16         # P: 检测批


def read_leeb_components(
    path: Path,
    sheet_name: str,
    *,
    rows_per_component: int = 3,
    header_rows: int = 1,
    default_angle_degrees: float = -90.0,
) -> list[LeebHardnessComponentInput]:
    """从报检单 Excel 读取多构件里氏硬度数据。

    参数:
        path: xlsx 文件路径
        sheet_name: 工作表名（如「里氏硬度（钢柱）」）
        rows_per_component: 每构件占多少行（= 测区数；规范 ≥3，常用 3）
        header_rows: 表头占多少行（用于偏移）
        default_angle_degrees: 默认角度（钢柱常用 -90°/+90°；UI 全局选）

    返回:
        LeebHardnessComponentInput 列表，按 Excel 序号顺序。

    异常:
        InfraIOError —— 文件不存在 / sheet 不存在 / 文件被占用
        InputError   —— 数据格式不符（HL 非整数 / 9 列缺失 / 厚度非数）
    """
    if not path.exists():
        raise InfraIOError(
            cause=f"文件不存在：{path}",
            location="read_leeb_components",
            hint="请检查路径拼写或文件是否被移动",
        )

    try:
        wb = load_workbook(str(path), data_only=True, read_only=True)
    except Exception as e:
        raise InfraIOError(
            cause=f"打开 Excel 文件失败：{e}",
            location="read_leeb_components",
            hint="请检查文件是否被 Office 占用、是否为有效 xlsx 格式",
        ) from e

    if sheet_name not in wb.sheetnames:
        wb.close()
        raise InputError(
            cause=f"工作表 {sheet_name!r} 不存在；可选 sheet：{wb.sheetnames}",
            location="read_leeb_components",
            hint="请在文件中确认工作表名称（注意全角/半角括号）",
        )

    ws = wb[sheet_name]
    components: list[LeebHardnessComponentInput] = []
    # 当前检测批名跨子表头继承（每构件首行可能不再写检测批名，但属于上一批）
    current_batch_name = ""

    # 从 header_rows + 1 开始遍历；每 rows_per_component 行处理一个构件
    row = header_rows + 1
    while row <= ws.max_row:
        seq_cell = ws.cell(row, _COL_SEQ).value
        # 跳过空行（报检单底部可能有备注/分隔空行）
        if seq_cell is None and ws.cell(row, _COL_HL_START).value is None:
            row += 1
            continue
        # 跳过 mid-sheet 子表头：报检单每检测批起始处会重复表头行
        # 识别方式：A 列非数字（"序号" 字面量）或 C 列非数字（"里氏硬度值（HLi）"）
        if seq_cell is not None and not isinstance(seq_cell, (int, float)):
            log.debug("跳过子表头 row=%d (A=%r)", row, seq_cell)
            row += 1
            continue
        if not isinstance(ws.cell(row, _COL_HL_START).value, (int, float)):
            log.debug("跳过子表头/异常行 row=%d (C=%r)", row, ws.cell(row, _COL_HL_START).value)
            row += 1
            continue

        name = ws.cell(row, _COL_NAME).value
        thickness = ws.cell(row, _COL_THICKNESS).value
        batch_cell = ws.cell(row, _COL_BATCH).value
        if batch_cell:
            current_batch_name = str(batch_cell).strip()
        batch_name = current_batch_name

        # 读取 rows_per_component 行的 HL 数据
        test_areas: list[tuple[int, ...]] = []
        for offset in range(rows_per_component):
            r = row + offset
            if r > ws.max_row:
                break
            hl_values: list[int] = []
            for c_offset in range(_COL_HL_COUNT):
                v = ws.cell(r, _COL_HL_START + c_offset).value
                if v is None:
                    raise InputError(
                        cause=f"行 {r} 列 {get_column_letter(_COL_HL_START + c_offset)} HL 值缺失",
                        location="read_leeb_components",
                        hint=f"构件 #{seq_cell} 的第 {offset + 1} 测区缺测点；请补完 9 个值",
                    )
                try:
                    hl_values.append(int(round(float(v))))
                except (TypeError, ValueError) as e:
                    raise InputError(
                        cause=f"行 {r} 列 {get_column_letter(_COL_HL_START + c_offset)} HL 值非数字：{v!r}",
                        location="read_leeb_components",
                    ) from e
            test_areas.append(tuple(hl_values))

        if len(test_areas) != rows_per_component:
            log.warning(
                "构件 #%s 实际只读到 %d 个测区（期望 %d），可能文件末尾不完整",
                seq_cell,
                len(test_areas),
                rows_per_component,
            )

        # seq/name/thickness 解析（容忍 None 缺失，用合理默认或抛错）
        try:
            seq = int(seq_cell) if seq_cell is not None else len(components) + 1
        except (TypeError, ValueError) as e:
            raise InputError(
                cause=f"行 {row} 序号非整数：{seq_cell!r}",
                location="read_leeb_components",
            ) from e
        if not name:
            raise InputError(
                cause=f"行 {row} 构件位置（B 列）为空",
                location="read_leeb_components",
                hint=f"序号 {seq} 缺构件位置；请检查 Excel",
            )
        try:
            thickness_f = float(thickness) if thickness is not None else 0.0
        except (TypeError, ValueError) as e:
            raise InputError(
                cause=f"行 {row} 厚度非数字：{thickness!r}",
                location="read_leeb_components",
            ) from e
        if thickness_f <= 0:
            raise InputError(
                cause=f"行 {row} 厚度无效（{thickness_f}），需 > 0",
                location="read_leeb_components",
                hint=f"序号 {seq} 厚度列（L 列）缺失或非正数",
            )

        components.append(
            LeebHardnessComponentInput(
                seq=seq,
                name=str(name).strip(),
                thickness=thickness_f,
                angle_degrees=default_angle_degrees,
                test_areas_raw=tuple(test_areas),
                batch_name=batch_name,
            )
        )

        row += rows_per_component

    wb.close()

    if not components:
        raise InputError(
            cause=f"工作表 {sheet_name!r} 未读到任何构件数据",
            location="read_leeb_components",
            hint=f"请确认数据从第 {header_rows + 1} 行起、每 {rows_per_component} 行一个构件",
        )

    log.info("读取里氏硬度数据完成：%d 个构件（来自 %s / %s）", len(components), path.name, sheet_name)
    return components


# ════════════════════════════════════════════════════════════════
# 导出：批级结果 → Excel 两张表
# ════════════════════════════════════════════════════════════════
def write_leeb_results(
    path: Path,
    batch: LeebHardnessBatchResult,
    *,
    angle_degrees: float | None = None,
) -> None:
    """把批级结果导出为 xlsx 两张表（原始数据 + 计算结果 + 底部批级汇总）。

    参数:
        path: 输出文件路径（含 .xlsx 后缀）
        batch: calc_leeb_hardness_batch 返回的批级结果
        angle_degrees: 用于在表头追加角度信息（None 则不写）
    """
    wb = Workbook()

    # ── Sheet 1：原始数据（仿报检单结构）───────────────────────
    ws_raw = wb.active
    ws_raw.title = "原始数据"
    ws_raw.append(
        ["序号", "构件位置", *[f"HL{i + 1}" for i in range(9)], "厚度(mm)", "检测批", "角度°"]
    )
    for comp, _result in batch.components_with_results:
        for zone_idx, zone in enumerate(comp.test_areas_raw):
            if zone_idx == 0:
                ws_raw.append(
                    [
                        comp.seq,
                        comp.name,
                        *list(zone),
                        comp.thickness,
                        comp.batch_name,
                        comp.angle_degrees,
                    ]
                )
            else:
                ws_raw.append(["", "", *list(zone), "", "", ""])

    # ── Sheet 2：计算结果（每测区一行 + 构件聚合 + 批级总）──
    ws_res = wb.create_sheet("计算结果")
    ws_res.append(
        [
            "序号",
            "构件位置",
            "测区",
            "HL_m",
            "HL_t",
            "HL_a",
            "HL_corr",
            "fb_min(MPa)",
            "fb_max(MPa)",
            "构件下限平均",
            "构件推定值",
        ]
    )
    for comp, result in batch.components_with_results:
        for zone_idx, area in enumerate(result.test_areas):
            ws_res.append(
                [
                    comp.seq if zone_idx == 0 else "",
                    comp.name if zone_idx == 0 else "",
                    f"测区{zone_idx + 1}",
                    area.hl_m,
                    round(area.hl_t, 2),
                    round(area.hl_a, 2),
                    round(area.hl_corrected, 2),
                    round(area.fb_min, 1),
                    round(area.fb_max, 1),
                    round(result.comp_fb_min_avg, 1) if zone_idx == 0 else "",
                    round(result.comp_fb_est, 1) if zone_idx == 0 else "",
                ]
            )

    # 批级汇总（最后追加 2 行：分隔 + 数据）
    ws_res.append([])
    ws_res.append(
        [
            "—",
            f"批级汇总（共 {batch.n_components} 个构件）",
            "—",
            "—",
            "—",
            "—",
            "—",
            "—",
            "—",
            "批级特征值平均",
            round(batch.batch_fb_char_avg, 1),
        ]
    )

    # 角度元信息追加到表 1 顶部（A 列前可看）
    if angle_degrees is not None:
        ws_raw.cell(1, 14).value = f"全局测量角度：{angle_degrees}°"

    try:
        wb.save(str(path))
    except Exception as e:
        raise InfraIOError(
            cause=f"写入 Excel 失败：{e}",
            location="write_leeb_results",
            hint="请确认目标目录可写且文件未被 Excel 打开",
        ) from e

    log.info(
        "导出里氏硬度结果完成：%s（%d 构件，批级 fb_char_avg=%.1f MPa）",
        path,
        batch.n_components,
        batch.batch_fb_char_avg,
    )
