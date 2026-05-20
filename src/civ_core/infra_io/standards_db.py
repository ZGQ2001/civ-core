"""standards_db：规范参数 / 查表的 SQLite 持久化层。

为什么独立一张通用表 standards_tables 而不是给每种查表建一张物理表：
  规范查表千差万别（1D：厚度修正；2D：回弹×碳化测强曲线；多列：钻芯 k1/k2_005/k2_010），
  与其物理上分表，不如逻辑上分 `table_name` —— DDL 一次到位，
  调用方按 TABLE_* 常量识别用途，calc_functions 在外层做插值。

表结构（单表）：
    standards_tables
      id          INTEGER PK
      table_name  TEXT NOT NULL    -- 逻辑表名（用 TABLE_* 常量识别）
      key1        REAL NOT NULL    -- 主键值（n / R_m / 厚度 …）
      key2        REAL             -- 次键值（碳化深度 / 角度 …）；NULL = 1D 表
      value1      REAL NOT NULL    -- 主值（k1 / 强度换算值 / 修正量）
      value2      REAL             -- 次值（k2_005）
      value3      REAL             -- 三值（k2_010）

    唯一性由两条 partial unique index 保证：
      uniq_2d (table_name, key1, key2)  WHERE key2 IS NOT NULL
      uniq_1d (table_name, key1)        WHERE key2 IS NULL

设计要点：
  - 连接生命周期不由本层管理（沿用 project_db 的模式：外部传入 conn）
  - ON CONFLICT REPLACE：同 (table_name, key1, key2) 重复 put 直接覆盖，
    便于 seed_* 函数幂等执行
  - 用 partial index 而不是表级 UNIQUE 约束，因 SQLite 把 NULL 视作各不相等，
    单一 UNIQUE(table_name, key1, key2) 在 1D 表场景下无法触发 upsert
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable

from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ── 逻辑表名常量（新规范加表时在此追加） ────────────────────────
TABLE_CORE_DRILLING_K = "core_drilling_k"  # INSP-002：n → (k1, k2_005, k2_010)
TABLE_LEEB_THICKNESS = "leeb_thickness_correction"  # INSP-001：厚度 → HL_t
TABLE_LEEB_ANGLE = "leeb_angle_correction"  # INSP-001：(角度档, HL_m) → HL_a
TABLE_LEEB_STRENGTH = "leeb_strength_conversion"  # INSP-001：HL_corr → fb_min
TABLE_REBOUND_STRENGTH = "rebound_strength_curve"  # INSP-003：(R_m, d_m) → fcu
TABLE_REBOUND_ANGLE = "rebound_angle_correction"  # INSP-003：(角度档, R_m) → ΔR_α
TABLE_REBOUND_SURFACE = "rebound_surface_correction"  # INSP-003：(检测面, R_m) → ΔR_s


# ── 数据契约 ────────────────────────────────────────────────────
@dataclass(slots=True, frozen=True)
class StandardsRow:
    """规范查表的一行；具体含义由 table_name 决定。

    1D 表：只用 key1 + value1
    2D 表：用 key1 + key2 + value1
    多列表（如钻芯 k1/k2_005/k2_010）：key1 + value1/value2/value3
    """

    table_name: str
    key1: float
    value1: float
    key2: float | None = None
    value2: float | None = None
    value3: float | None = None

    def __post_init__(self) -> None:
        if not self.table_name:
            raise ValueError("StandardsRow.table_name 不可为空")


# ── SQL 常量 ────────────────────────────────────────────────────
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS standards_tables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    key1        REAL NOT NULL,
    key2        REAL,
    value1      REAL NOT NULL,
    value2      REAL,
    value3      REAL
);

CREATE INDEX IF NOT EXISTS ix_standards_table_name
    ON standards_tables(table_name);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_standards_2d
    ON standards_tables(table_name, key1, key2)
    WHERE key2 IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_standards_1d
    ON standards_tables(table_name, key1)
    WHERE key2 IS NULL;
"""

# ON CONFLICT 走对应的 partial index：2D 表用 (table_name,key1,key2)，1D 表用 (table_name,key1)
UPSERT_ROW_SQL_2D = """
INSERT INTO standards_tables (table_name, key1, key2, value1, value2, value3)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(table_name, key1, key2) WHERE key2 IS NOT NULL DO UPDATE SET
    value1 = excluded.value1,
    value2 = excluded.value2,
    value3 = excluded.value3
"""

UPSERT_ROW_SQL_1D = """
INSERT INTO standards_tables (table_name, key1, key2, value1, value2, value3)
VALUES (?, ?, NULL, ?, ?, ?)
ON CONFLICT(table_name, key1) WHERE key2 IS NULL DO UPDATE SET
    value1 = excluded.value1,
    value2 = excluded.value2,
    value3 = excluded.value3
"""

# 注意 NULL 比较要用 IS：1D 表 key2 写入是 NULL，查询时需要 IS NULL 才能命中
SELECT_ROW_SQL_2D = """
SELECT key1, key2, value1, value2, value3 FROM standards_tables
WHERE table_name = ? AND key1 = ? AND key2 = ?
"""
SELECT_ROW_SQL_1D = """
SELECT key1, key2, value1, value2, value3 FROM standards_tables
WHERE table_name = ? AND key1 = ? AND key2 IS NULL
"""

LIST_ROWS_SQL = """
SELECT key1, key2, value1, value2, value3 FROM standards_tables
WHERE table_name = ? ORDER BY key1, key2
"""

DELETE_TABLE_SQL = "DELETE FROM standards_tables WHERE table_name = ?"


# ════════════════════════════════════════════════════════════════
# StandardsDB
# ════════════════════════════════════════════════════════════════
class StandardsDB:
    """规范查表 SQLite 持久化。

    用法：
        conn = sqlite3.connect("~/.civ-core/standards.db")
        conn.row_factory = sqlite3.Row
        db = StandardsDB(conn)
        db.create_tables()
        seed_core_drilling_k_table(db)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ── 建表 ──────────────────────────────────────────────────
    def create_tables(self) -> None:
        with self.conn:
            self.conn.executescript(CREATE_TABLES_SQL)

    # ── 写入 ──────────────────────────────────────────────────
    def put_row(self, row: StandardsRow) -> None:
        with self.conn:
            self._exec_upsert(row)

    def put_rows(self, rows: Iterable[StandardsRow]) -> None:
        # 一次事务批量写：按 1D / 2D 分别用对应 upsert 语句
        with self.conn:
            for r in rows:
                self._exec_upsert(r)

    def _exec_upsert(self, row: StandardsRow) -> None:
        if row.key2 is None:
            self.conn.execute(
                UPSERT_ROW_SQL_1D,
                (row.table_name, row.key1, row.value1, row.value2, row.value3),
            )
        else:
            self.conn.execute(
                UPSERT_ROW_SQL_2D,
                (
                    row.table_name,
                    row.key1,
                    row.key2,
                    row.value1,
                    row.value2,
                    row.value3,
                ),
            )

    # ── 读取 ──────────────────────────────────────────────────
    def get_row(
        self,
        table_name: str,
        key1: float,
        key2: float | None = None,
    ) -> StandardsRow | None:
        """精确查找一行；找不到返回 None。"""
        if key2 is None:
            cur = self.conn.execute(SELECT_ROW_SQL_1D, (table_name, key1))
        else:
            cur = self.conn.execute(SELECT_ROW_SQL_2D, (table_name, key1, key2))
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dataclass(table_name, row)

    def list_rows(self, table_name: str) -> list[StandardsRow]:
        """按 (key1, key2) 升序返回某逻辑表全部行。"""
        cur = self.conn.execute(LIST_ROWS_SQL, (table_name,))
        return [_row_to_dataclass(table_name, r) for r in cur.fetchall()]

    # ── 清表（用于重新 seed） ─────────────────────────────────
    def delete_table(self, table_name: str) -> int:
        with self.conn:
            cur = self.conn.execute(DELETE_TABLE_SQL, (table_name,))
            return cur.rowcount


def _row_to_dataclass(table_name: str, row: sqlite3.Row) -> StandardsRow:
    return StandardsRow(
        table_name=table_name,
        key1=row["key1"],
        key2=row["key2"],
        value1=row["value1"],
        value2=row["value2"],
        value3=row["value3"],
    )


# ════════════════════════════════════════════════════════════════
# Seed：INSP-002 钻芯法 k1/k2 系数表（JGJ/T 384-2016 表 A.0.2）
# ════════════════════════════════════════════════════════════════
# (n, k1, k2_005, k2_010)
# k2_005 → 漏判概率 0.05（常规芯样）；k2_010 → 漏判概率 0.10（小直径芯样）
_CORE_DRILLING_K_DATA: tuple[tuple[int, float, float, float], ...] = (
    (10, 1.01730, 2.91096, 2.56837),
    (11, 1.04127, 2.81499, 2.50262),
    (12, 1.06247, 2.73634, 2.44825),
    (13, 1.08141, 2.67050, 2.40240),
    (14, 1.09848, 2.61443, 2.36311),
    (15, 1.11397, 2.56600, 2.32898),
    (16, 1.12812, 2.52366, 2.29900),
    (17, 1.14112, 2.48626, 2.27240),
    (18, 1.15311, 2.45295, 2.24862),
    (19, 1.16423, 2.42304, 2.22720),
    (20, 1.17458, 2.39600, 2.20778),
    (21, 1.18425, 2.37142, 2.19007),
    (22, 1.19330, 2.34896, 2.17385),
    (23, 1.20181, 2.32832, 2.15891),
    (24, 1.20982, 2.30929, 2.14510),
    (25, 1.21739, 2.29167, 2.13229),
    (26, 1.22455, 2.27530, 2.12037),
    (27, 1.23135, 2.26005, 2.10924),
    (28, 1.23780, 2.24578, 2.09881),
    (29, 1.24395, 2.23241, 2.08903),
    (30, 1.24981, 2.21984, 2.07982),
    (31, 1.25540, 2.20800, 2.07113),
    (32, 1.26075, 2.19682, 2.06292),
    (33, 1.26588, 2.18625, 2.05514),
    (34, 1.27079, 2.17623, 2.04776),
    (35, 1.27551, 2.16672, 2.04075),
    (36, 1.28004, 2.15768, 2.03407),
    (37, 1.28441, 2.14906, 2.02771),
    (38, 1.28861, 2.14085, 2.02164),
    (39, 1.29266, 2.13300, 2.01583),
    (40, 1.29657, 2.12549, 2.01027),
    (41, 1.30035, 2.11831, 2.00494),
    (42, 1.30399, 2.11142, 1.99983),
    (43, 1.30752, 2.10481, 1.99493),
    (44, 1.31094, 2.09846, 1.99021),
    (45, 1.31425, 2.09235, 1.98567),
    (46, 1.31746, 2.08648, 1.98130),
    (47, 1.32058, 2.08081, 1.97708),
    (48, 1.32360, 2.07535, 1.97302),
    (49, 1.32653, 2.07008, 1.96909),
    (50, 1.32939, 2.06499, 1.96529),
    (60, 1.35412, 2.02216, 1.93327),
    (70, 1.37364, 1.98987, 1.90903),
    (80, 1.38959, 1.96444, 1.88988),
    (90, 1.40294, 1.94376, 1.87428),
    (100, 1.41433, 1.92654, 1.86125),
    (110, 1.42421, 1.91191, 1.85017),
    (120, 1.43289, 1.89929, 1.84059),
    (130, 1.44060, 1.88827, 1.83222),
    (140, 1.44750, 1.87852, 1.82481),
    (150, 1.45372, 1.86984, 1.81820),
    (160, 1.45938, 1.86203, 1.81225),
    (170, 1.46456, 1.85497, 1.80686),
    (180, 1.46931, 1.84854, 1.80196),
    (190, 1.47370, 1.84265, 1.79746),
    (200, 1.47777, 1.83724, 1.79332),
    (250, 1.49443, 1.81547, 1.77667),
    (300, 1.50687, 1.79964, 1.76454),
    (400, 1.52453, 1.77776, 1.74773),
    (500, 1.53671, 1.76305, 1.73641),
)


def seed_core_drilling_k_table(db: StandardsDB) -> None:
    """录入 INSP-002 钻芯法 k1/k2 系数表（共 60 行）。

    幂等：UPSERT 自动覆盖同 n 的旧值；重复调用不会翻倍。
    """
    rows = [
        StandardsRow(
            table_name=TABLE_CORE_DRILLING_K,
            key1=float(n),
            value1=k1,
            value2=k2_005,
            value3=k2_010,
        )
        for (n, k1, k2_005, k2_010) in _CORE_DRILLING_K_DATA
    ]
    db.put_rows(rows)
    log.info("seed standards_tables.%s 完成，共 %d 行", TABLE_CORE_DRILLING_K, len(rows))


# ════════════════════════════════════════════════════════════════
# Seed：INSP-001 里氏硬度三表（GB/T 50344-2019 附录 N + GB/T 17394.4-2014）
# 数据来源：docs/civil_kb/formulas/计算表格.xlsx → 钢材硬度 sheet
# ════════════════════════════════════════════════════════════════

# 板厚修正：板厚 mm → HL_t（薄板回弹偏低，HL 正向加值校正）
# 表只覆盖 6~12mm；> 12mm 视作无需修正（用 999.0 哨兵行 + 0 让插值始终返回 0）
_LEEB_THICKNESS_DATA: tuple[tuple[float, float], ...] = (
    (6.0, 30.0),
    (7.0, 22.0),
    (8.0, 18.0),
    (10.0, 10.0),
    (12.0, 0.0),
    (999.0, 0.0),  # 哨兵：> 12mm 任意厚度 → HL_t = 0
)


def seed_leeb_thickness_correction(db: StandardsDB) -> None:
    """录入 INSP-001 板厚修正表（5 行真实数据 + 1 行 > 12mm 哨兵）。"""
    rows = [
        StandardsRow(table_name=TABLE_LEEB_THICKNESS, key1=t, value1=hl_t)
        for (t, hl_t) in _LEEB_THICKNESS_DATA
    ]
    db.put_rows(rows)
    log.info("seed standards_tables.%s 完成，共 %d 行", TABLE_LEEB_THICKNESS, len(rows))


# 角度修正：(角度档 = float 度数, HL_m) → HL_a
# 角度档：+90° = 竖直向上 / 0° = 水平 / -90° = 竖直向下（GB/T 17394 符号约定）
# 注：源 Excel 文件中 (HL_m=650, +90°) 单元格为 18，按整列趋势（其他行均为 -33..-14 单调递增）
#     该值显然漏掉负号，已手动修正为 -18。修订需要确认时直接改下方 _LEEB_ANGLE_RAW 中标注行。
_LEEB_ANGLE_RAW: tuple[tuple[float, float, float, float, float, float], ...] = (
    # HL_m,  -90°,  -45°,   0°,  +45°,  +90°
    (200.0,   0.0,  -7.0, -14.0, -23.0, -33.0),
    (250.0,   0.0,  -6.0, -13.0, -22.0, -31.0),
    (300.0,   0.0,  -6.0, -12.0, -20.0, -29.0),
    (350.0,   0.0,  -6.0, -12.0, -19.0, -27.0),
    (400.0,   0.0,  -5.0, -11.0, -18.0, -25.0),
    (450.0,   0.0,  -5.0, -10.0, -17.0, -24.0),
    (500.0,   0.0,  -5.0, -10.0, -16.0, -22.0),
    (550.0,   0.0,  -4.0,  -9.0, -15.0, -20.0),
    (600.0,   0.0,  -4.0,  -8.0, -14.0, -19.0),
    (650.0,   0.0,  -4.0,  -8.0, -13.0, -18.0),  # 源 Excel 此格为 18，趋势修正为 -18
    (700.0,   0.0,  -3.0,  -7.0, -12.0, -17.0),
    (750.0,   0.0,  -3.0,  -6.0, -11.0, -16.0),
    (800.0,   0.0,  -3.0,  -6.0, -10.0, -15.0),
    (850.0,   0.0,  -2.0,  -5.0,  -9.0, -14.0),
)
_LEEB_ANGLE_DEGREES: tuple[float, ...] = (-90.0, -45.0, 0.0, 45.0, 90.0)


def seed_leeb_angle_correction(db: StandardsDB) -> None:
    """录入 INSP-001 角度修正表（5 角度档 × 14 HL_m 行 = 70 行）。"""
    rows: list[StandardsRow] = []
    for row in _LEEB_ANGLE_RAW:
        hl_m, *hl_a_values = row
        for deg, hl_a in zip(_LEEB_ANGLE_DEGREES, hl_a_values, strict=True):
            rows.append(
                StandardsRow(
                    table_name=TABLE_LEEB_ANGLE,
                    key1=deg,
                    key2=hl_m,
                    value1=hl_a,
                )
            )
    db.put_rows(rows)
    log.info("seed standards_tables.%s 完成，共 %d 行", TABLE_LEEB_ANGLE, len(rows))


# 强度换算：HL_corrected → fb_min（MPa）。fb_max = fb_min + 150 由 dataclass 校验
# 数据范围 HL_dm 255..480（100 行；前段 5 步长，HL>=302 后 2 步长）
_LEEB_STRENGTH_DATA: tuple[tuple[float, float], ...] = (
    (255.0, 306.0), (260.0, 306.0), (265.0, 307.0), (270.0, 307.0), (275.0, 308.0),
    (280.0, 309.0), (285.0, 310.0), (290.0, 311.0), (295.0, 313.0), (300.0, 315.0),
    (302.0, 316.0), (304.0, 317.0), (306.0, 318.0), (308.0, 319.0), (310.0, 320.0),
    (312.0, 321.0), (314.0, 322.0), (316.0, 323.0), (318.0, 324.0), (320.0, 326.0),
    (322.0, 327.0), (324.0, 328.0), (326.0, 329.0), (328.0, 331.0), (330.0, 332.0),
    (332.0, 334.0), (334.0, 335.0), (336.0, 337.0), (338.0, 338.0), (340.0, 340.0),
    (342.0, 342.0), (344.0, 343.0), (346.0, 345.0), (348.0, 347.0), (350.0, 349.0),
    (352.0, 350.0), (354.0, 352.0), (356.0, 354.0), (358.0, 356.0), (360.0, 358.0),
    (362.0, 360.0), (364.0, 362.0), (366.0, 365.0), (368.0, 367.0), (370.0, 369.0),
    (372.0, 371.0), (374.0, 374.0), (376.0, 376.0), (378.0, 378.0), (380.0, 381.0),
    (382.0, 383.0), (384.0, 386.0), (386.0, 388.0), (388.0, 391.0), (390.0, 393.0),
    (392.0, 396.0), (394.0, 399.0), (396.0, 401.0), (398.0, 404.0), (400.0, 407.0),
    (402.0, 410.0), (404.0, 413.0), (406.0, 416.0), (408.0, 419.0), (410.0, 422.0),
    (412.0, 425.0), (414.0, 428.0), (416.0, 431.0), (418.0, 434.0), (420.0, 437.0),
    (422.0, 441.0), (424.0, 444.0), (426.0, 447.0), (428.0, 451.0), (430.0, 454.0),
    (432.0, 458.0), (434.0, 461.0), (436.0, 465.0), (438.0, 468.0), (440.0, 472.0),
    (442.0, 475.0), (444.0, 479.0), (446.0, 483.0), (448.0, 487.0), (450.0, 491.0),
    (452.0, 494.0), (454.0, 498.0), (456.0, 502.0), (458.0, 506.0), (460.0, 510.0),
    (462.0, 514.0), (464.0, 518.0), (466.0, 523.0), (468.0, 527.0), (470.0, 531.0),
    (472.0, 535.0), (474.0, 539.0), (476.0, 544.0), (478.0, 548.0), (480.0, 553.0),
)


def seed_leeb_strength_conversion(db: StandardsDB) -> None:
    """录入 INSP-001 强度换算表（共 100 行 HL_dm 255~480 → fb_min MPa）。"""
    rows = [
        StandardsRow(table_name=TABLE_LEEB_STRENGTH, key1=hl, value1=fb_min)
        for (hl, fb_min) in _LEEB_STRENGTH_DATA
    ]
    db.put_rows(rows)
    log.info("seed standards_tables.%s 完成，共 %d 行", TABLE_LEEB_STRENGTH, len(rows))


def seed_all_leeb_tables(db: StandardsDB) -> None:
    """一次性 seed INSP-001 三张表（厚度 + 角度 + 强度）。"""
    seed_leeb_thickness_correction(db)
    seed_leeb_angle_correction(db)
    seed_leeb_strength_conversion(db)


# ════════════════════════════════════════════════════════════════
# 默认 DB 文件 + 一键初始化（供 bootstrap / healthcheck 调用）
# ════════════════════════════════════════════════════════════════
import sqlite3 as _sqlite3
from pathlib import Path as _Path


def get_default_db_path() -> _Path:
    """规范库默认存放位置：~/.civ-core/standards.db。"""
    return _Path("~/.civ-core/standards.db").expanduser()


def init_standards_db(
    path: _Path | None = None,
) -> tuple[StandardsDB, _sqlite3.Connection]:
    """打开规范库 DB，建表，幂等 seed 全部规范表。

    返回 (db, conn)：调用方负责持有 conn 直到不再用（关闭见 conn.close()）。
    若 path 为空，落 ~/.civ-core/standards.db（自动 mkdir 父目录）。

    当前 seed 的表：
      - INSP-002 钻芯法 k1/k2 系数表（60 行）
      - INSP-001 里氏硬度三表：厚度修正（6 行含哨兵）/ 角度修正（70 行）/
        强度换算（100 行）
    """
    db_path = path or get_default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    db = StandardsDB(conn)
    db.create_tables()
    seed_core_drilling_k_table(db)
    seed_all_leeb_tables(db)
    log.info("standards_db 初始化完成：%s", db_path)
    return db, conn
