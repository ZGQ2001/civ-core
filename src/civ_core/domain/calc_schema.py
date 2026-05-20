"""检测计算函数的结果契约（INSP-001/002/003）。

为什么和 schema.py / project_schema.py 平级独立一份：
  - 绘曲线图（PlotJob 等）走 schema.py，项目看板走 project_schema.py，
    检测计算属于"业务计算结果"独立维度；放一起会让 schema.py 变成杂物筐
  - 后续 calc_functions 计算函数模块只 import 这一份契约，
    UI / 报告填充层也只看这一份，分层清晰

3 类结果对应 3 份公式文档：
  INSP-001 钢材里氏硬度 → LeebHardnessTestArea + LeebHardnessResult
  INSP-002 钻芯法       → CoreDrillingResult
  INSP-003 回弹法       → ReboundTestArea + ReboundResult

frozen=True：结果一旦计算出来就不该被外部改，UI / 报告只读不写。
"""

from __future__ import annotations

from dataclasses import dataclass

# ════════════════════════════════════════════════════════════════
# INSP-001 钢材里氏硬度推算抗拉强度
# ════════════════════════════════════════════════════════════════
# INSP-001 §1.4：fb_max 由 fb_min 平移 150 MPa 推导（GB/T 17394.4-2014）
_LEEB_FB_RANGE = 150.0


@dataclass(slots=True, frozen=True)
class LeebHardnessTestArea:
    """里氏硬度单测区结果（INSP-001 §1）。

    每测区强制 9 个原始测点（规范要求），截尾平均剔除 4/9 极值后取 5 个均值。

    字段单位 / 精度：
      raw_hl_values  原始 9 点（int，精确至 1）
      hl_m           截尾均值后取整（int）
      hl_t           厚度修正量（float，可正可负）
      hl_a           角度修正量（float，可正可负）
      hl_corrected   = hl_m + hl_t + hl_a
      fb_min/fb_max  抗拉强度下/上限（MPa），其中 fb_max = fb_min + 150
    """

    raw_hl_values: tuple[int, ...]
    hl_m: int
    hl_t: float
    hl_a: float
    hl_corrected: float
    fb_min: float
    fb_max: float

    def __post_init__(self) -> None:
        if len(self.raw_hl_values) != 9:
            raise ValueError(
                f"LeebHardnessTestArea.raw_hl_values 必须是 9 个测点，得到 {len(self.raw_hl_values)}"
            )
        if self.fb_min <= 0 or self.fb_max <= 0:
            raise ValueError("LeebHardnessTestArea.fb_min/fb_max 必须 > 0")
        if self.fb_max <= self.fb_min:
            raise ValueError(
                f"LeebHardnessTestArea.fb_max ({self.fb_max}) 必须 > fb_min ({self.fb_min})"
            )
        # 容差 0.01：浮点累计误差兜底
        if abs((self.fb_max - self.fb_min) - _LEEB_FB_RANGE) > 0.01:
            raise ValueError(
                f"LeebHardnessTestArea.fb_max - fb_min 必须 ≈ {_LEEB_FB_RANGE}（INSP-001 §1.4），"
                f"得到 {self.fb_max - self.fb_min}"
            )


@dataclass(slots=True, frozen=True)
class LeebHardnessResult:
    """里氏硬度构件 + 批级聚合结果（INSP-001 §2-3）。

    多个测区 → 构件下/上限平均 → 构件推定值 = (下限+上限)/2
    多个构件 → 批级 = 全局下限值集合的平均

    本 dataclass 同时承载"单构件"和"单批"两种粒度的结果；
    batch_fb_char_avg 在 test_areas 来自同一构件时 == comp_fb_min_avg。
    """

    test_areas: tuple[LeebHardnessTestArea, ...]
    comp_fb_min_avg: float  # 构件下限值（MPa）
    comp_fb_max_avg: float  # 构件上限值（MPa）
    comp_fb_est: float      # 构件推定值（MPa）= (下限+上限)/2
    batch_fb_char_avg: float  # 批级抗拉强度特征值的平均（MPa）

    def __post_init__(self) -> None:
        if len(self.test_areas) < 1:
            raise ValueError("LeebHardnessResult.test_areas 不少于 1 个测区")


@dataclass(slots=True, frozen=True)
class LeebHardnessComponentInput:
    """单构件输入数据（批级计算的最小单元，对应报检单 Excel 中一个构件的 3 行）。

    字段:
        seq             序号（来自报检单 Excel）
        name            构件位置/名称（如「地上一层2×H钢柱」）
        thickness       构件厚度（mm），全部测区共用
        angle_degrees   测量角度（必须 ∈ {-90, -45, 0, 45, 90}）
        test_areas_raw  N 个测区，每测区 9 个 HL 测点（常见 N=3）
        batch_name      检测批名（可选，便于 UI 分组显示）
    """

    seq: int
    name: str
    thickness: float
    angle_degrees: float
    test_areas_raw: tuple[tuple[int, ...], ...]
    batch_name: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("LeebHardnessComponentInput.name 不可为空")
        if self.thickness <= 0:
            raise ValueError(
                f"LeebHardnessComponentInput.thickness 必须 > 0，得到 {self.thickness}"
            )
        if not self.test_areas_raw:
            raise ValueError("LeebHardnessComponentInput.test_areas_raw 至少 1 个测区")
        for i, area in enumerate(self.test_areas_raw):
            if len(area) != 9:
                raise ValueError(
                    f"LeebHardnessComponentInput.test_areas_raw[{i}] 必须 9 个测点，"
                    f"得到 {len(area)}"
                )


@dataclass(slots=True, frozen=True)
class LeebHardnessBatchResult:
    """单个检测批级计算结果（对应 xlsx 中一个 sheet）。

    batch_name: 检测批名（= 来源 sheet 名，便于 UI 切换 / 导出还原）
    components_with_results: (输入构件, 该构件的 LeebHardnessResult) 元组列表，
                             保持输入顺序，方便 UI 表格按序号渲染
    batch_fb_char_avg:       全部构件 comp_fb_min_avg 的平均（INSP-001 §3 批级特征值）
    n_components:            构件总数
    """

    components_with_results: tuple[tuple[LeebHardnessComponentInput, LeebHardnessResult], ...]
    batch_fb_char_avg: float
    n_components: int
    batch_name: str = ""

    def __post_init__(self) -> None:
        if self.n_components != len(self.components_with_results):
            raise ValueError(
                f"LeebHardnessBatchResult.n_components ({self.n_components}) 与列表长度不一致 "
                f"({len(self.components_with_results)})"
            )
        if self.n_components < 1:
            raise ValueError("LeebHardnessBatchResult.n_components 必须 >= 1")


@dataclass(slots=True, frozen=True)
class LeebHardnessBatch:
    """单个检测批输入（对应原始数据 xlsx 中一个 sheet）。

    batch_name: 检测批名（= sheet 名）
    components: 该批内的所有构件（≥1）
    """

    batch_name: str
    components: tuple[LeebHardnessComponentInput, ...]

    def __post_init__(self) -> None:
        if not self.batch_name.strip():
            raise ValueError("LeebHardnessBatch.batch_name 不可为空")
        if not self.components:
            raise ValueError("LeebHardnessBatch.components 至少需要 1 个构件")


@dataclass(slots=True, frozen=True)
class LeebHardnessWorkbook:
    """一次检测项目实例的全部数据（对应一个 xlsx 文件）。

    file_label: 项目实例标签（如「里氏硬度-D号站房」），可空
    batches:    各检测批；按 sheet 顺序保持
    """

    batches: tuple[LeebHardnessBatch, ...]
    file_label: str = ""

    def __post_init__(self) -> None:
        if not self.batches:
            raise ValueError("LeebHardnessWorkbook.batches 至少需要 1 个检测批")
        # 检测批名应唯一（sheet 不允许重名）
        names = [b.batch_name for b in self.batches]
        if len(names) != len(set(names)):
            raise ValueError(
                f"LeebHardnessWorkbook.batches 检测批名重复：{names}"
            )


@dataclass(slots=True, frozen=True)
class LeebHardnessWorkbookResult:
    """整 workbook 的批级计算结果聚合。

    batch_results: 每检测批的结果，按输入顺序
    n_batches:     检测批数
    n_components_total: 所有批的构件总数（便于 UI 状态行显示）
    """

    batch_results: tuple[LeebHardnessBatchResult, ...]
    n_batches: int
    n_components_total: int

    def __post_init__(self) -> None:
        if self.n_batches != len(self.batch_results):
            raise ValueError(
                f"LeebHardnessWorkbookResult.n_batches ({self.n_batches}) 与列表长度不一致 "
                f"({len(self.batch_results)})"
            )
        expected = sum(r.n_components for r in self.batch_results)
        if expected != self.n_components_total:
            raise ValueError(
                f"LeebHardnessWorkbookResult.n_components_total ({self.n_components_total}) "
                f"与各批之和不一致 ({expected})"
            )


# ════════════════════════════════════════════════════════════════
# INSP-002 钻芯法混凝土抗压强度推定
# ════════════════════════════════════════════════════════════════
# JGJ/T 384-2016 表 A.0.2：系数表从 n=10 开始
_CORE_DRILLING_N_MIN = 10
_CORE_DRILLING_TAKE_KINDS = frozenset({"upper", "lower"})


@dataclass(slots=True, frozen=True)
class CoreDrillingResult:
    """钻芯法推定值结果（INSP-002）。

    字段对应 INSP-002 出参：
      f_cu_cor_values  原始芯样强度（MPa，精确至 0.1）
      n                芯样数量（>= 10）
      f_cu_cor_m       平均值（MPa，0.1）
      s_cu             样本标准差（MPa，0.01）
      k1 / k2          推定区间系数（从 standards_db 取 / 必要时线性插值）
      f_cu_e1          推定上限 = m - k1·s
      f_cu_e2          推定下限 = m - k2·s
      f_cu_est         检测批推定值 = e1 或 e2（由 take 决定）
      take             "upper" / "lower"，取上限还是下限作为推定值
      passed           推定值是否满足设计强度等级（外部判定后回填）
    """

    f_cu_cor_values: tuple[float, ...]
    n: int
    f_cu_cor_m: float
    s_cu: float
    k1: float
    k2: float
    f_cu_e1: float
    f_cu_e2: float
    f_cu_est: float
    take: str
    passed: bool

    def __post_init__(self) -> None:
        if self.n < _CORE_DRILLING_N_MIN:
            raise ValueError(
                f"CoreDrillingResult.n 必须 >= {_CORE_DRILLING_N_MIN}（JGJ/T 384-2016 表 A.0.2），得到 {self.n}"
            )
        if len(self.f_cu_cor_values) != self.n:
            raise ValueError(
                f"CoreDrillingResult.f_cu_cor_values 长度 ({len(self.f_cu_cor_values)}) 必须等于 n ({self.n})"
            )
        if self.take not in _CORE_DRILLING_TAKE_KINDS:
            raise ValueError(
                f"CoreDrillingResult.take 必须是 {sorted(_CORE_DRILLING_TAKE_KINDS)} 之一，得到 {self.take!r}"
            )
        if self.s_cu < 0:
            raise ValueError(f"CoreDrillingResult.s_cu 必须 >= 0，得到 {self.s_cu}")


# ════════════════════════════════════════════════════════════════
# INSP-003 回弹法混凝土抗压强度推定
# ════════════════════════════════════════════════════════════════
# JGJ/T 23-2011 §4.1.3：回弹法每测区固定 16 点
_REBOUND_RAW_COUNT = 16
# §4.2 / §7.3：n<10 单构件取最小；n>=10 批量按推定区间上限
_REBOUND_BATCH_THRESHOLD = 10
_REBOUND_MODE_KINDS = frozenset({"single", "batch"})


@dataclass(slots=True, frozen=True)
class ReboundTestArea:
    """回弹法单测区结果（INSP-003 §1-3）。

    raw_rebound_values  原始 16 点回弹值（剔 3 高 3 低取 10 个均值得 R_m）
    r_m                 测区平均回弹值（精确至 0.1）
    d_m                 碳化深度（精确至 0.5 mm，< 0.5 → 0，≥ 6 → 6）
    f_cu_i              测区强度换算值（MPa，0.1，从测强曲线表 (R_m, d_m) 二维插值）
    """

    raw_rebound_values: tuple[int, ...]
    r_m: float
    d_m: float
    f_cu_i: float

    def __post_init__(self) -> None:
        if len(self.raw_rebound_values) != _REBOUND_RAW_COUNT:
            raise ValueError(
                f"ReboundTestArea.raw_rebound_values 必须是 {_REBOUND_RAW_COUNT} 个测点，"
                f"得到 {len(self.raw_rebound_values)}"
            )
        if self.d_m < 0 or self.d_m > 6.0:
            raise ValueError(
                f"ReboundTestArea.d_m 应在 [0, 6.0] mm 范围内（碳化深度规范化后），得到 {self.d_m}"
            )
        if self.f_cu_i < 0:
            raise ValueError(f"ReboundTestArea.f_cu_i 必须 >= 0，得到 {self.f_cu_i}")


@dataclass(slots=True, frozen=True)
class ReboundResult:
    """回弹法构件 / 批级推定值（INSP-003 §4）。

    两种 mode：
      single  n<10  单构件检测：f_cu_e = min(f_cu_i)；m_fcu/s_fcu 仅做参考
      batch   n>=10 批量检测：f_cu_e = m_fcu - 1.645 * s_fcu
    """

    test_areas: tuple[ReboundTestArea, ...]
    n: int
    mode: str
    m_fcu: float       # 测区强度换算值平均（MPa，0.1）
    s_fcu: float       # 测区强度换算值标准差（MPa，0.01）
    f_cu_e: float      # 推定值（MPa，0.1）

    def __post_init__(self) -> None:
        if self.mode not in _REBOUND_MODE_KINDS:
            raise ValueError(
                f"ReboundResult.mode 必须是 {sorted(_REBOUND_MODE_KINDS)} 之一，得到 {self.mode!r}"
            )
        if self.n < 1:
            raise ValueError(f"ReboundResult.n 必须 >= 1，得到 {self.n}")
        if self.s_fcu < 0:
            raise ValueError(f"ReboundResult.s_fcu 必须 >= 0，得到 {self.s_fcu}")
        # 自洽校验：mode 与 n 应匹配规范的判定阈值
        if self.mode == "batch" and self.n < _REBOUND_BATCH_THRESHOLD:
            raise ValueError(
                f"ReboundResult.mode=batch 要求 n >= {_REBOUND_BATCH_THRESHOLD}，得到 n={self.n}"
            )
