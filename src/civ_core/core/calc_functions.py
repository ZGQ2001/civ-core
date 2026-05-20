"""检测计算函数集合（INSP-001/002/003）。

为什么单文件而不是按规范拆 3 个：
  - 3 个公式都是"统计 + 规范表查找"模式，共用 _trim_mean / _lookup_interp 等工具
  - 后续可能再加 INSP-004/005，到 ~10 个函数时再按域拆模块也来得及

设计要点：
  - 纯 Python（不引 numpy/scipy）：用 statistics + 手写线性插值
  - StandardsDB 由外部传入（沿用 project_db / chart_writer 等的模式）
  - 出参全部走 domain/calc_schema 的 frozen dataclass
  - 异常用 utils/exceptions 的 InputError（用户输入不合规）
  - 数据精度严格按公式文档要求做 round（避免下游再 round 一遍）

模块结构：
  ── 工具函数 ──
    _trim_mean / _round_half_up / _lookup_with_interp / _stdev_sample
  ── INSP-002 钻芯法 ──
    calc_core_drilling_concrete
  ── INSP-001 / INSP-003 骨架 ──（占位；查表数据待用户提供后实现）
"""

from __future__ import annotations

import statistics
from typing import Literal, Sequence

from civ_core.domain.calc_schema import CoreDrillingResult
from civ_core.infra_io.standards_db import (
    TABLE_CORE_DRILLING_K,
    StandardsDB,
)
from civ_core.utils.exceptions import InputError


# ════════════════════════════════════════════════════════════════
# 通用工具
# ════════════════════════════════════════════════════════════════
def _stdev_sample(values: Sequence[float]) -> float:
    """样本标准差（n-1 自由度）；n<2 返回 0。"""
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def _lookup_with_interp(
    db: StandardsDB,
    table_name: str,
    key: float,
    *,
    value_idx: Literal["value1", "value2", "value3"],
) -> float:
    """在 standards_tables 的某逻辑表上按 key1 查找 value，超出/未命中点用线性插值。

    要求：表内所有行 key2 IS NULL（1D 表）；key 必须落在 [min(key1), max(key1)] 内。
    超出范围抛 InputError（不外推，更安全）。
    """
    rows = db.list_rows(table_name)
    if not rows:
        raise InputError(
            cause=f"规范查表 {table_name!r} 为空",
            location=f"_lookup_with_interp({table_name})",
            hint="请先用 seed_*_table 函数初始化该规范表的数据",
        )

    # rows 已按 key1 升序；先做精确命中
    for row in rows:
        if row.key1 == key:
            v = getattr(row, value_idx)
            if v is None:
                raise InputError(
                    cause=f"规范表 {table_name!r} 的 key={key} 行 {value_idx} 为空",
                    location=f"_lookup_with_interp({table_name})",
                )
            return float(v)

    # 越界检查
    if key < rows[0].key1 or key > rows[-1].key1:
        raise InputError(
            cause=f"查表 key={key} 超出规范表 {table_name!r} 范围 [{rows[0].key1}, {rows[-1].key1}]",
            location=f"_lookup_with_interp({table_name})",
            hint="请检查输入是否在规范允许范围内",
        )

    # 线性插值：找前后两点
    for i in range(len(rows) - 1):
        lo, hi = rows[i], rows[i + 1]
        if lo.key1 < key < hi.key1:
            v_lo = getattr(lo, value_idx)
            v_hi = getattr(hi, value_idx)
            if v_lo is None or v_hi is None:
                raise InputError(
                    cause=f"规范表 {table_name!r} 插值区间内 {value_idx} 缺值",
                    location=f"_lookup_with_interp({table_name})",
                )
            t = (key - lo.key1) / (hi.key1 - lo.key1)
            return float(v_lo) + t * (float(v_hi) - float(v_lo))

    # 理论上走不到这里（精确命中或区间内插值已覆盖）；兜底抛 InputError
    raise InputError(
        cause=f"查表 key={key} 在 {table_name!r} 内未找到匹配行",
        location=f"_lookup_with_interp({table_name})",
    )


# ════════════════════════════════════════════════════════════════
# INSP-002 钻芯法
# ════════════════════════════════════════════════════════════════
_CORE_DRILLING_N_MIN = 10
_CORE_DRILLING_N_MAX = 500
_CORE_DRILLING_TAKES = ("upper", "lower")


def calc_core_drilling_concrete(
    values: Sequence[float],
    *,
    db: StandardsDB,
    take: Literal["upper", "lower"] = "lower",
    small_diameter: bool = False,
    design_fcu: float | None = None,
) -> CoreDrillingResult:
    """钻芯法混凝土抗压强度推定（INSP-002 / JGJ/T 384-2016 §6.3.2 + 附录 A）。

    参数:
        values: 单个芯样试件抗压强度 f_cu,cor,i 列表（MPa）。
                数量 n 必须 ∈ [10, 500]（JGJ/T 384-2016 表 A.0.2 适用范围）。
        db: 已 seed 过 core_drilling_k 表的 StandardsDB 实例。
        take: 推定值取上限还是下限；批量验收常用 "lower"（保守），上限多用于争议复检。
        small_diameter: True → 小直径芯样，k2 用漏判概率 0.10 列；
                        False → 常规芯样，k2 用漏判概率 0.05 列。
        design_fcu: 设计强度等级（MPa）。提供则自动判定 passed = (f_cu_est >= design_fcu)。

    返回:
        CoreDrillingResult，含统计量 + 推定上下限 + 推定值 + passed。

    异常:
        InputError —— n 越界 / take 非法 / 查表失败时抛出（带规范定位）。
    """
    n = len(values)

    # ── 输入校验 ──────────────────────────────────────────────
    if n < _CORE_DRILLING_N_MIN:
        raise InputError(
            cause=f"芯样数量 n={n} 小于规范最低 {_CORE_DRILLING_N_MIN}",
            location="calc_core_drilling_concrete",
            hint=f"JGJ/T 384-2016 表 A.0.2 起始 n={_CORE_DRILLING_N_MIN}；请补足芯样或改用单值判定",
        )
    if n > _CORE_DRILLING_N_MAX:
        raise InputError(
            cause=f"芯样数量 n={n} 超过规范上限 {_CORE_DRILLING_N_MAX}",
            location="calc_core_drilling_concrete",
            hint=f"JGJ/T 384-2016 表 A.0.2 仅给到 n={_CORE_DRILLING_N_MAX}；请按多批分别评定",
        )
    if take not in _CORE_DRILLING_TAKES:
        raise InputError(
            cause=f"take={take!r} 不在 {_CORE_DRILLING_TAKES}",
            location="calc_core_drilling_concrete",
            hint="批量验收 take='lower'（推定下限），争议复检常用 take='upper'（推定上限）",
        )

    # ── 统计量（按规范精度 round）──────────────────────────────
    f_cu_cor_m = round(statistics.mean(values), 1)
    s_cu = round(_stdev_sample(values), 2)

    # ── 查 k1 / k2（小直径用 k2_010 = value3，常规用 k2_005 = value2）──
    k1 = _lookup_with_interp(db, TABLE_CORE_DRILLING_K, float(n), value_idx="value1")
    k2_col: Literal["value2", "value3"] = "value3" if small_diameter else "value2"
    k2 = _lookup_with_interp(db, TABLE_CORE_DRILLING_K, float(n), value_idx=k2_col)

    # ── 推定区间（INSP-002 §3）─────────────────────────────────
    f_cu_e1 = round(f_cu_cor_m - k1 * s_cu, 1)
    f_cu_e2 = round(f_cu_cor_m - k2 * s_cu, 1)
    f_cu_est = f_cu_e1 if take == "upper" else f_cu_e2

    # ── 合规判定 ──────────────────────────────────────────────
    passed = True if design_fcu is None else (f_cu_est >= design_fcu)

    return CoreDrillingResult(
        f_cu_cor_values=tuple(values),
        n=n,
        f_cu_cor_m=f_cu_cor_m,
        s_cu=s_cu,
        k1=k1,
        k2=k2,
        f_cu_e1=f_cu_e1,
        f_cu_e2=f_cu_e2,
        f_cu_est=f_cu_est,
        take=take,
        passed=passed,
    )


# ════════════════════════════════════════════════════════════════
# INSP-001 钢材里氏硬度 / INSP-003 回弹法
# （骨架占位：等用户提供 GB/T 17394.4-2014、JGJ/T 23-2011 附录 A
#  的厚度/角度/强度/测强曲线表数据后，按本文件已建立的 _lookup_with_interp
#  接口实现，并在 standards_db.py 加对应的 seed_*_table 函数）
# ════════════════════════════════════════════════════════════════
