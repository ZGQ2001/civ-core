"""里氏硬度（INSP-001）批级计算工具页（2026-05-20 多批格式版）。

工作流（钢结构厂房项目实战）：
  1. [导入 Excel] 选符合规范的 xlsx（每 sheet=一检测批）→ 解析为 workbook
  2. 顶栏选全局测量角度（-90/-45/0/+45/+90，默认 0° 水平）
  3. 顶栏批选择器：切换查看不同检测批的构件清单 + 结果
  4. [计算] → 一次性算所有批 → 显示当前批结果
  5. [导出 Excel] → 写一个结果文件，每批 2 sheet（过程数据 + 报告插入表）

布局：
  ┌── 顶栏（导入 / 角度 / 批选 / 计算 / 导出 / 清空 / 模板下载）──┐
  ├──────────┬──────────────────────────────────────────────────┤
  │ 构件清单  │ 当前批批级 fb_char_avg（醒目大字号）              │
  │ Table    │ ────────────────────────────────                  │
  │ (当前批)  │ 当前批详细结果 Table（每测区一行）                 │
  └──────────┴──────────────────────────────────────────────────┘

设计要点：
  • angle_degrees 全局参数（默认 0° 水平；规范表 -90° = 向下垂直基线档）
  • 数据持有：self._workbook + self._workbook_result + self._current_batch_idx
  • 切换批不触发重算（结果已经按整 workbook 算好缓存）
  • db 由 MainWindow 注入
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TitleLabel,
)

from civ_core.core.calc_functions import calc_leeb_hardness_workbook
from civ_core.domain.calc_schema import (
    LeebHardnessBatchResult,
    LeebHardnessComponentInput,
    LeebHardnessWorkbook,
    LeebHardnessWorkbookResult,
)
from civ_core.infra_io.leeb_excel import (
    read_leeb_workbook,
    write_leeb_results_workbook,
)
from civ_core.infra_io.standards_db import StandardsDB
from civ_core.ui.components.error_infobar import (
    show_error_infobar,
    show_success_infobar,
    show_warning_infobar,
)
from civ_core.utils.exceptions import CivCoreError
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ── 表格模型 ────────────────────────────────────────────────────
class _ComponentsTableModel(QAbstractTableModel):
    """左栏构件清单：序号 / 构件位置 / 厚度 / 测区数 / 检测批。"""

    HEADERS = ("序号", "构件位置", "厚度(mm)", "测区数", "检测批")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[LeebHardnessComponentInput] = []

    def set_components(self, components: list[LeebHardnessComponentInput]) -> None:
        self.beginResetModel()
        self._data = components
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        c = self._data[index.row()]
        col = index.column()
        if col == 0:
            return c.seq
        if col == 1:
            return c.name
        if col == 2:
            return f"{c.thickness:g}"
        if col == 3:
            return len(c.test_areas_raw)
        if col == 4:
            return c.batch_name
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


class _ResultsTableModel(QAbstractTableModel):
    """右栏详细结果：每测区一行 + 构件聚合在首行显示。"""

    HEADERS = (
        "序号",
        "构件位置",
        "测区",
        "HL_m",
        "HL_t",
        "HL_a",
        "HL_corr",
        "fb_min",
        "fb_max",
        "构件推定",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple] = []

    def set_batch_result(self, batch: LeebHardnessBatchResult | None) -> None:
        self.beginResetModel()
        self._rows = []
        if batch is not None:
            for comp, result in batch.components_with_results:
                for zone_idx, area in enumerate(result.test_areas):
                    self._rows.append(
                        (
                            comp.seq if zone_idx == 0 else "",
                            comp.name if zone_idx == 0 else "",
                            f"测区{zone_idx + 1}",
                            area.hl_m,
                            f"{area.hl_t:.2f}",
                            f"{area.hl_a:.2f}",
                            f"{area.hl_corrected:.2f}",
                            f"{area.fb_min:.1f}",
                            f"{area.fb_max:.1f}",
                            f"{result.comp_fb_est:.1f}" if zone_idx == 0 else "",
                        )
                    )
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return self._rows[index.row()][index.column()]

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


# ── 主视图 ──────────────────────────────────────────────────────
# 物理含义：-90° = 向下垂直（基线档，HL_a=0）；+90° = 向上垂直（最大修正）；0° = 水平（默认）
_ANGLE_OPTIONS: tuple[tuple[str, float], ...] = (
    ("-90° 向下垂直 ↓", -90.0),
    ("-45° 向下 45°", -45.0),
    ("0° 水平 →（默认）", 0.0),
    ("+45° 向上 45°", 45.0),
    ("+90° 向上垂直 ↑", 90.0),
)
_ANGLE_DEFAULT_INDEX = 2

_TEMPLATE_PATH = Path("templates/leeb_hardness/原始数据模板.xlsx")


class LeebHardnessView(QWidget):
    """里氏硬度批级计算工具页（导航 routing key = leebHardnessPage）。"""

    def __init__(self, db: StandardsDB, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("leebHardnessPage")
        self._db = db
        self._workbook: LeebHardnessWorkbook | None = None
        self._workbook_result: LeebHardnessWorkbookResult | None = None
        self._current_batch_idx: int = 0
        self._last_dir: Path | None = None

        self._build_ui()
        self._refresh_buttons()

    # ── UI 构造 ──────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # ── 顶栏：操作按钮 ───────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_import = PushButton("导入 Excel")
        self.btn_import.clicked.connect(self._on_import)
        toolbar.addWidget(self.btn_import)

        self.btn_template = PushButton("下载模板")
        self.btn_template.clicked.connect(self._on_download_template)
        toolbar.addWidget(self.btn_template)

        toolbar.addSpacing(12)
        toolbar.addWidget(BodyLabel("测量角度："))
        self.cmb_angle = ComboBox()
        for label, _ in _ANGLE_OPTIONS:
            self.cmb_angle.addItem(label)
        self.cmb_angle.setCurrentIndex(_ANGLE_DEFAULT_INDEX)
        self.cmb_angle.currentIndexChanged.connect(self._on_angle_changed)
        toolbar.addWidget(self.cmb_angle)

        toolbar.addSpacing(12)
        toolbar.addWidget(BodyLabel("检测批："))
        self.cmb_batch = ComboBox()
        self.cmb_batch.setMinimumWidth(160)
        self.cmb_batch.currentIndexChanged.connect(self._on_batch_changed)
        toolbar.addWidget(self.cmb_batch)

        toolbar.addSpacing(12)
        self.btn_calc = PrimaryPushButton("▶ 计算")
        self.btn_calc.clicked.connect(self._on_calculate)
        toolbar.addWidget(self.btn_calc)

        self.btn_export = PushButton("导出 Excel")
        self.btn_export.clicked.connect(self._on_export)
        toolbar.addWidget(self.btn_export)

        self.btn_clear = PushButton("清空")
        self.btn_clear.clicked.connect(self._on_clear)
        toolbar.addWidget(self.btn_clear)

        toolbar.addStretch(1)
        self.lbl_status = BodyLabel("尚未导入数据")
        toolbar.addWidget(self.lbl_status)

        root.addLayout(toolbar)

        # ── 主体：左右两栏 ───────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(4)

        # 左：构件清单
        left = QWidget()
        left_lo = QVBoxLayout(left)
        left_lo.setContentsMargins(0, 0, 0, 0)
        left_lo.addWidget(StrongBodyLabel("当前批构件清单"))
        self.tbl_components = QTableView()
        self._comp_model = _ComponentsTableModel(self)
        self.tbl_components.setModel(self._comp_model)
        self.tbl_components.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_components.horizontalHeader().setStretchLastSection(True)
        self.tbl_components.verticalHeader().setVisible(False)
        self.tbl_components.setAlternatingRowColors(True)
        left_lo.addWidget(self.tbl_components, stretch=1)
        splitter.addWidget(left)

        # 右：批级摘要 + 详细结果
        right = QWidget()
        right_lo = QVBoxLayout(right)
        right_lo.setContentsMargins(0, 0, 0, 0)

        self.lbl_batch_summary = TitleLabel("批级抗拉强度特征值平均：—")
        self.lbl_batch_summary.setFont(self._make_summary_font())
        right_lo.addWidget(self.lbl_batch_summary)

        right_lo.addWidget(StrongBodyLabel("当前批详细结果（每测区一行）"))
        self.tbl_results = QTableView()
        self._res_model = _ResultsTableModel(self)
        self.tbl_results.setModel(self._res_model)
        self.tbl_results.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_results.verticalHeader().setVisible(False)
        self.tbl_results.setAlternatingRowColors(True)
        right_lo.addWidget(self.tbl_results, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([400, 600])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

    def _make_summary_font(self) -> QFont:
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        return f

    # ── 状态切换 ─────────────────────────────────────────────
    def _refresh_buttons(self) -> None:
        has_data = self._workbook is not None
        has_result = self._workbook_result is not None
        self.btn_calc.setEnabled(has_data)
        self.btn_export.setEnabled(has_result)
        self.btn_clear.setEnabled(has_data or has_result)

    def _current_angle(self) -> float:
        return _ANGLE_OPTIONS[self.cmb_angle.currentIndex()][1]

    def _current_batch(self):
        """当前选中的批（输入端）。"""
        if self._workbook is None:
            return None
        return self._workbook.batches[self._current_batch_idx]

    def _current_batch_result(self) -> LeebHardnessBatchResult | None:
        if self._workbook_result is None:
            return None
        return self._workbook_result.batch_results[self._current_batch_idx]

    # ── 事件处理 ─────────────────────────────────────────────
    def _on_download_template(self) -> None:
        """让用户把内置模板另存到自选位置。"""
        if not _TEMPLATE_PATH.exists():
            show_warning_infobar(
                self, "模板缺失",
                f"未找到模板文件 {_TEMPLATE_PATH}",
                hint="请联系开发者",
            )
            return
        start_dir = str(self._last_dir) if self._last_dir else ""
        out_str, _ = QFileDialog.getSaveFileName(
            self,
            "保存模板副本",
            f"{start_dir}/里氏硬度-原始数据.xlsx" if start_dir else "里氏硬度-原始数据.xlsx",
            "Excel 文件 (*.xlsx)",
        )
        if not out_str:
            return
        import shutil

        try:
            shutil.copy2(_TEMPLATE_PATH, out_str)
        except OSError as e:
            show_error_infobar(
                self,
                CivCoreError(cause=f"复制模板失败：{e}", location="download_template"),
            )
            return
        show_success_infobar(self, "模板已保存", Path(out_str).name)

    def _on_import(self) -> None:
        """选 xlsx → 解析为 LeebHardnessWorkbook。"""
        start_dir = str(self._last_dir) if self._last_dir else ""
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "选择里氏硬度原始数据 Excel",
            start_dir,
            "Excel 文件 (*.xlsx *.xlsm);;所有文件 (*.*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        self._last_dir = path.parent

        try:
            wb = read_leeb_workbook(path, default_angle_degrees=self._current_angle())
        except CivCoreError as e:
            show_error_infobar(self, e, where="导入")
            return
        except Exception as e:
            show_error_infobar(
                self,
                CivCoreError(cause=f"解析失败：{e}", location="read_leeb_workbook"),
                where="导入",
            )
            log.exception("导入失败")
            return

        self._workbook = wb
        self._workbook_result = None
        self._current_batch_idx = 0

        # 填批选择器（先关信号避免触发 _on_batch_changed 时 workbook 还没装完）
        self.cmb_batch.blockSignals(True)
        self.cmb_batch.clear()
        for batch in wb.batches:
            self.cmb_batch.addItem(f"{batch.batch_name} ({len(batch.components)} 构件)")
        self.cmb_batch.setCurrentIndex(0)
        self.cmb_batch.blockSignals(False)

        # 刷新当前批显示
        self._refresh_current_batch_views()
        self.lbl_status.setText(
            f"已导入 {wb.file_label}.xlsx：{len(wb.batches)} 批 / "
            f"共 {sum(len(b.components) for b in wb.batches)} 构件"
        )
        self._refresh_buttons()
        show_success_infobar(
            self,
            "导入成功",
            f"{path.name}：{len(wb.batches)} 个检测批",
        )

    def _on_angle_changed(self) -> None:
        """角度切换 → 同步更新所有批的 angle_degrees，并作废已算结果。"""
        if self._workbook is None:
            return
        angle = self._current_angle()
        # 重建 workbook 把新角度灌入每个构件
        from civ_core.domain.calc_schema import LeebHardnessBatch

        new_batches = []
        for b in self._workbook.batches:
            new_comps = tuple(
                LeebHardnessComponentInput(
                    seq=c.seq,
                    name=c.name,
                    thickness=c.thickness,
                    angle_degrees=angle,
                    test_areas_raw=c.test_areas_raw,
                    batch_name=c.batch_name,
                )
                for c in b.components
            )
            new_batches.append(LeebHardnessBatch(batch_name=b.batch_name, components=new_comps))
        self._workbook = LeebHardnessWorkbook(
            batches=tuple(new_batches), file_label=self._workbook.file_label
        )
        self._workbook_result = None
        self.lbl_batch_summary.setText(
            "批级抗拉强度特征值平均：— （角度已变，请重新计算）"
        )
        self._refresh_current_batch_views()
        self._refresh_buttons()

    def _on_batch_changed(self) -> None:
        idx = self.cmb_batch.currentIndex()
        if idx < 0 or self._workbook is None:
            return
        self._current_batch_idx = idx
        self._refresh_current_batch_views()

    def _refresh_current_batch_views(self) -> None:
        """根据当前 _current_batch_idx 刷新左栏构件清单 + 右栏结果。"""
        batch = self._current_batch()
        if batch is None:
            self._comp_model.set_components([])
            self._res_model.set_batch_result(None)
            self.lbl_batch_summary.setText("批级抗拉强度特征值平均：—")
            return

        self._comp_model.set_components(list(batch.components))
        batch_result = self._current_batch_result()
        self._res_model.set_batch_result(batch_result)
        if batch_result is not None:
            self.lbl_batch_summary.setText(
                f"批级抗拉强度特征值平均：{batch_result.batch_fb_char_avg:.1f} MPa  "
                f"（{batch.batch_name}，{batch_result.n_components} 个构件）"
            )
        else:
            self.lbl_batch_summary.setText(
                f"批级抗拉强度特征值平均：— （{batch.batch_name}，请点 ▶ 计算）"
            )

    def _on_calculate(self) -> None:
        if self._workbook is None:
            return
        try:
            result = calc_leeb_hardness_workbook(self._workbook, db=self._db)
        except CivCoreError as e:
            show_error_infobar(self, e, where="计算")
            return
        except Exception as e:
            show_error_infobar(
                self,
                CivCoreError(cause=f"计算失败：{e}", location="calc_leeb_hardness_workbook"),
                where="计算",
            )
            log.exception("批级计算失败")
            return

        self._workbook_result = result
        self._refresh_current_batch_views()
        self.lbl_status.setText(
            f"已计算 {result.n_batches} 批 / 共 {result.n_components_total} 构件"
        )
        self._refresh_buttons()

    def _on_export(self) -> None:
        if self._workbook_result is None:
            return
        start_dir = str(self._last_dir) if self._last_dir else ""
        default_name = (
            f"{self._workbook.file_label}-结果.xlsx"
            if self._workbook else "里氏硬度-结果.xlsx"
        )
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "导出里氏硬度计算结果",
            f"{start_dir}/{default_name}" if start_dir else default_name,
            "Excel 文件 (*.xlsx)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            write_leeb_results_workbook(
                path, self._workbook_result, angle_degrees=self._current_angle()
            )
        except CivCoreError as e:
            show_error_infobar(self, e, where="导出")
            return

        show_success_infobar(
            self, "导出成功", f"{path.name}：每批 2 sheet（过程数据 + 报告插入表）"
        )

    def _on_clear(self) -> None:
        self._workbook = None
        self._workbook_result = None
        self._current_batch_idx = 0
        self.cmb_batch.blockSignals(True)
        self.cmb_batch.clear()
        self.cmb_batch.blockSignals(False)
        self._refresh_current_batch_views()
        self.lbl_status.setText("尚未导入数据")
        self._refresh_buttons()
