"""ProjectDrawer：右侧滑出抽屉面板。

覆盖主区域约 40%，QPropertyAnimation 控制滑入/滑出。
内部 QStackedWidget 两层：摘要页 ↔ 完整编辑页。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CalendarPicker, LineEdit, MessageBoxBase

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import Project, StageStatus


class DeleteConfirmDialog(MessageBoxBase):

    def __init__(self, project_number: str, parent=None):
        super().__init__(parent)
        self.titleLabel = QLabel("确认删除项目？", self)
        self.titleLabel.setStyleSheet("font-size: 14px; font-weight: bold; color: #212121;")
        self._target = project_number

        hint = QLabel(f"此操作不可逆。请在下方输入项目编号 <b>{project_number}</b> 以确认删除。", self)
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #757575;")

        self._confirm_edit = LineEdit(self)
        self._confirm_edit.setPlaceholderText(f"输入 {project_number}")
        self._confirm_edit.setClearButtonEnabled(True)
        self._confirm_edit.textChanged.connect(self._on_text_changed)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(hint)
        self.viewLayout.addWidget(self._confirm_edit)
        self.widget.setMinimumWidth(380)

        self.yesButton.setText("确认删除")
        self.yesButton.setStyleSheet(
            "QPushButton { background: #E53935; color: white; border: none; "
            "border-radius: 4px; padding: 6px 20px; }"
            "QPushButton:hover { background: #C62828; }"
            "QPushButton:disabled { background: #EF9A9A; }"
        )
        self.yesButton.setEnabled(False)

    def _on_text_changed(self) -> None:
        self.yesButton.setEnabled(self._confirm_edit.text().strip() == self._target)

class ProjectDrawer(QFrame):
    """右侧滑出抽屉。

    用法：
        drawer = ProjectDrawer()
        drawer.set_project(project, service)
        drawer.open()   # 动画滑入
        drawer.close()  # 动画滑出
    """

    _DRAWER_WIDTH = 400  # 覆盖主区域约 40%

    project_updated = None  # Signal(Project)，在 ProjectBoardView 层连接
    stage_changed = None    # Signal(int, str, StageStatus)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Project | None = None
        self._service: ProjectService | None = None
        self._animation: QPropertyAnimation | None = None

        self.setObjectName("ProjectDrawer")
        self.setFixedWidth(0)
        self.setMaximumWidth(0)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            #ProjectDrawer {
                background: #FAFAFA;
                border-left: 1px solid #E0E0E0;
            }
        """)

        # 外层布局
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # 关闭按钮
        header = QHBoxLayout()
        header.addStretch()
        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 18px; color: #757575; }"
            "QPushButton:hover { color: #212121; }"
        )
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        outer.addLayout(header)

        # QStackedWidget
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        # 第 0 页：摘要
        self._summary_page = self._build_summary_page()
        self._stack.addWidget(self._summary_page)

        # 第 1 页：编辑
        self._edit_page = self._build_edit_page()
        self._stack.addWidget(self._edit_page)

    # ════════════════════════════════════════════════════════════
    # 公开 API
    # ════════════════════════════════════════════════════════════
    def set_project(self, project: Project, service: ProjectService | None) -> None:
        self._project = project
        self._service = service
        self._show_summary_page()
        self._populate_summary()

    closed = None       # callback set by ProjectBoardView
    project_deleted = None  # callback: (int) -> None

    def open(self) -> None:
        if self._project is None:
            return
        self._animate_to(self._DRAWER_WIDTH)

    def close(self) -> None:
        # 立即收拢 fixedWidth，动画只负责视觉过渡
        self.setFixedWidth(0)
        if self._animation is not None and self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
        self._animation = QPropertyAnimation(self, b"maximumWidth")
        self._animation.setDuration(80)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(self._DRAWER_WIDTH)
        self._animation.setEndValue(0)
        self._animation.start()
        # 通知外部刷新
        self._on_closed()

    # 内部
    def _animate_to(self, target: int) -> None:
        if self._animation is not None and self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
        self._animation = QPropertyAnimation(self, b"maximumWidth")
        self._animation.setDuration(120)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(self.maximumWidth())
        self._animation.setEndValue(target)
        self._animation.start()

        if target > 0:
            self.setFixedWidth(self._DRAWER_WIDTH)

    def _on_closed(self) -> None:
        if self.closed is not None:
            self.closed()

    def _show_summary_page(self) -> None:
        self._stack.setCurrentIndex(0)

    def _toggle_original_record(self) -> None:
        if self._project is None or self._service is None:
            return
        p = self._project
        folder_text = self._edit_folder.text().strip()
        updated = Project(
            project_id=p.project_id, project_number=p.project_number,
            name=p.name, client=p.client, inspection_type=p.inspection_type,
            amount=p.amount, folder_path=Path(folder_text) if folder_text else None,
            original_record_done=not p.original_record_done,
            notes=p.notes, stages=p.stages,
            created_at=p.created_at, updated_at=p.updated_at,
        )
        self._service.update_project(updated)
        self._project = self._service.get_project(p.project_id)
        self._populate_summary()

    def _toggle_on_hold(self) -> None:
        """切换暂存态。以 _project.is_on_hold 为单一真值源（按钮态由 populate 同步）。"""
        if self._project is None or self._service is None:
            return
        new_value = not self._project.is_on_hold
        try:
            updated = self._service.set_on_hold(self._project.project_id, new_value)
            self._project = updated
            self._populate_summary()
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "更新失败", str(e))

    def _toggle_archived(self) -> None:
        """切换归档态（独立于 7 阶段完成度）。"""
        if self._project is None or self._service is None:
            return
        new_value = not self._project.is_archived
        try:
            updated = self._service.set_archived(self._project.project_id, new_value)
            self._project = updated
            self._populate_summary()
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "更新失败", str(e))

    def _toggle_stage(self, project_id: int, stage_name: str, current_status: StageStatus) -> None:
        """点击阶段按钮：循环切换状态。"""
        if self._service is None:
            return
        # NOT_STARTED → IN_PROGRESS → COMPLETED → NOT_STARTED
        next_status = {
            StageStatus.NOT_STARTED: StageStatus.IN_PROGRESS,
            StageStatus.IN_PROGRESS: StageStatus.COMPLETED,
            StageStatus.COMPLETED: StageStatus.NOT_STARTED,
        }[current_status]
        try:
            updated = self._service.update_stage(project_id, stage_name, next_status)
            self._project = updated
            self._populate_summary()
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "更新失败", str(e))

    def _on_bind_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择项目文件夹", self._edit_folder.text())
        if d:
            self._edit_folder.setText(d)

    def _show_edit_page(self) -> None:
        if self._service is None:
            return
        self._populate_edit()
        self._stack.setCurrentIndex(1)

    # ── 摘要页 ──────────────────────────────────────────────────
    def _build_summary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 项目信息区
        self._summary_name = QLabel()
        self._summary_name.setWordWrap(True)
        self._summary_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #212121;")
        layout.addWidget(self._summary_name)

        self._summary_info = QLabel()
        self._summary_info.setStyleSheet("font-size: 12px; color: #757575;")
        layout.addWidget(self._summary_info)

        self._summary_record = QPushButton()
        self._summary_record.setFlat(True)
        self._summary_record.setStyleSheet(
            "QPushButton { text-align: left; font-size: 12px; border: 1px solid #E0E0E0; "
            "border-radius: 4px; padding: 6px 10px; color: #212121; }"
            "QPushButton:hover { border-color: #1976D2; }"
        )
        self._summary_record.clicked.connect(self._toggle_original_record)
        layout.addWidget(self._summary_record)

        # ── 状态标志：暂存 / 归档（两个可勾选按钮，水平并排） ─────
        # 设计：与 4 档筛选呼应。is_archived 优先级 > is_on_hold（service 层规则）
        flags_row = QHBoxLayout()
        flags_row.setContentsMargins(0, 0, 0, 0)
        flags_row.setSpacing(8)
        self._btn_on_hold = QPushButton("⏸ 暂存")
        self._btn_archived = QPushButton("▣ 归档")
        flag_style = (
            "QPushButton { font-size: 12px; border: 1px solid #E0E0E0; "
            "border-radius: 4px; padding: 6px 10px; color: #424242; background: #FFFFFF; }"
            "QPushButton:hover { border-color: #1976D2; }"
            "QPushButton:checked { background: %s; color: white; border-color: %s; }"
        )
        # 暂存 = 橙色，归档 = 深灰
        self._btn_on_hold.setCheckable(True)
        self._btn_on_hold.setStyleSheet(flag_style % ("#FB8C00", "#FB8C00"))
        self._btn_on_hold.clicked.connect(self._toggle_on_hold)
        self._btn_archived.setCheckable(True)
        self._btn_archived.setStyleSheet(flag_style % ("#616161", "#616161"))
        self._btn_archived.clicked.connect(self._toggle_archived)
        flags_row.addWidget(self._btn_on_hold, 1)
        flags_row.addWidget(self._btn_archived, 1)
        layout.addLayout(flags_row)

        # 阶段列表区域
        stages_label = QLabel("进度")
        stages_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #424242; margin-top:8px;")
        layout.addWidget(stages_label)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        stages_container = QWidget()
        self._stages_layout = QVBoxLayout(stages_container)
        self._stages_layout.setContentsMargins(0, 0, 0, 0)
        self._stages_layout.setSpacing(2)
        scroll.setWidget(stages_container)
        layout.addWidget(scroll)

        layout.addStretch()

        # 底部按钮
        btn_edit = QPushButton("进入完整管理")
        btn_edit.setStyleSheet(
            "QPushButton { background: #1976D2; color: white; border: none; "
            "border-radius: 4px; padding: 8px; font-size: 12px; }"
            "QPushButton:hover { background: #1565C0; }"
        )
        btn_edit.clicked.connect(self._show_edit_page)
        layout.addWidget(btn_edit)

        btn_folder = QPushButton("📁 打开文件夹")
        btn_folder.setStyleSheet(
            "QPushButton { background: #F5F5F5; color: #424242; border: 1px solid #E0E0E0; "
            "border-radius: 4px; padding: 8px; font-size: 12px; }"
            "QPushButton:hover { background: #EEEEEE; }"
        )
        btn_folder.clicked.connect(self._on_open_folder)
        layout.addWidget(btn_folder)

        btn_delete = QPushButton("删除项目")
        btn_delete.setStyleSheet(
            "QPushButton { background: transparent; color: #E53935; border: 1px solid #E53935; "
            "border-radius: 4px; padding: 8px; font-size: 12px; }"
            "QPushButton:hover { background: #FFEBEE; }"
        )
        btn_delete.clicked.connect(self._on_delete)
        layout.addWidget(btn_delete)

        return page

    @staticmethod
    def _clear_sub_layout(layout: QHBoxLayout | QVBoxLayout) -> None:
        while layout.count():
            sub = layout.takeAt(0)
            sw = sub.widget()
            if sw is not None:
                sw.deleteLater()

    def _populate_summary(self) -> None:
        if self._project is None:
            return
        p = self._project
        self._summary_name.setText(p.name)
        self._summary_info.setText(
            f"{p.project_number}\n委托方：{p.client}\n类型：{p.inspection_type}\n"
            f"金额：¥{p.amount:,.0f}"
        )
        self._summary_record.setText(
            f"原始记录 {'✅ 已写完' if p.original_record_done else '○ 未写完'}"
        )
        # 同步两个标志位的勾选态（blockSignals 防止 setChecked 触发 clicked）
        self._btn_on_hold.blockSignals(True)
        self._btn_on_hold.setChecked(p.is_on_hold)
        self._btn_on_hold.blockSignals(False)
        self._btn_archived.blockSignals(True)
        self._btn_archived.setChecked(p.is_archived)
        self._btn_archived.blockSignals(False)

        # 安全清空旧阶段组件（递归处理 widget 和子 layout）
        while self._stages_layout.count():
            item = self._stages_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_sub_layout(item.layout())

        status_map = {
            StageStatus.NOT_STARTED: ("○", "#9E9E9E"),
            StageStatus.IN_PROGRESS: ("●", "#1976D2"),
            StageStatus.COMPLETED: ("✓", "#4CAF50"),
        }
        for stage in p.stages:
            row = QHBoxLayout()
            row.setContentsMargins(4, 0, 4, 0)
            row.setSpacing(10)

            indicator, color = status_map[stage.status]
            dot = QLabel(indicator)
            dot.setFixedWidth(20)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet(f"font-size: 14px; color: {color}; font-weight: bold;")
            row.addWidget(dot)

            btn = QPushButton(stage.name)
            btn.setFlat(True)
            btn.setStyleSheet(
                "QPushButton { text-align: left; font-size: 12px; padding: 4px 0; "
                "border: none; color: #212121; }"
                "QPushButton:hover { color: #1976D2; }"
            )
            btn.clicked.connect(lambda checked, pid=p.project_id, sn=stage.name, ss=stage.status: self._toggle_stage(pid, sn, ss))
            row.addWidget(btn, 1)
            self._stages_layout.addLayout(row)

    def _on_delete(self) -> None:
        if self._project is None or self._service is None:
            return
        dlg = DeleteConfirmDialog(self._project.project_number, self.window())
        if not dlg.exec():
            return
        self._service.delete_project(self._project.project_id)
        pid = self._project.project_id
        self.close()
        if self.project_deleted is not None:
            self.project_deleted(pid)

    def _on_open_folder(self) -> None:
        if self._project is None:
            return
        if self._project.folder_path:
            from civ_core.infra_io.project_folder import open_project_folder
            open_project_folder(self._project.folder_path)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "该项目尚未绑定本地文件夹。\n请在「进入完整管理」中设置文件夹路径。")

    # ── 编辑页 ──────────────────────────────────────────────────
    def _build_edit_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        fields = [
            ("项目编号", "number"),
            ("项目名称", "name"),
            ("委托方", "client"),
            ("检测类型", "inspection_type"),
        ]
        self._edit_fields: dict[str, QLineEdit] = {}

        for label_text, key in fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #757575;")
            layout.addWidget(lbl)
            edit = QLineEdit()
            edit.setStyleSheet("font-size: 12px; padding: 4px;")
            layout.addWidget(edit)
            self._edit_fields[key] = edit

        # 金额独立
        lbl_amt = QLabel("项目金额")
        lbl_amt.setStyleSheet("font-size: 12px; color: #757575;")
        layout.addWidget(lbl_amt)
        self._edit_amount = QLineEdit()
        self._edit_amount.setStyleSheet("font-size: 12px; padding: 4px;")
        layout.addWidget(self._edit_amount)

        # ── 创建日期 ─────────────────────────────────────────
        lbl_date = QLabel("创建日期")
        lbl_date.setStyleSheet("font-size: 11px; color: #757575; margin-top: 8px;")
        layout.addWidget(lbl_date)

        self._edit_date = CalendarPicker(self)
        self._edit_date.setDateFormat("yyyy-MM-dd")
        layout.addWidget(self._edit_date)

        # ── 本地工作区绑定 ──────────────────────────────────────
        lbl_folder = QLabel("本地文件夹")
        lbl_folder.setStyleSheet("font-size: 11px; color: #757575; margin-top: 8px;")
        layout.addWidget(lbl_folder)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self._edit_folder = QLineEdit()
        self._edit_folder.setReadOnly(True)
        self._edit_folder.setPlaceholderText("未绑定（点击右侧按钮选择）")
        self._edit_folder.setStyleSheet(
            "font-size: 12px; padding: 3px 6px; border: 1px solid #E0E0E0; "
            "border-radius: 3px; min-height: 26px; background: #F5F5F5;"
        )
        folder_row.addWidget(self._edit_folder)

        btn_bind = QPushButton("📁 绑定目录...")
        btn_bind.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 4px 12px; border: 1px solid #E0E0E0; "
            "border-radius: 3px; min-height: 26px; } QPushButton:hover { border-color: #1976D2; }"
        )
        btn_bind.clicked.connect(self._on_bind_folder)
        folder_row.addWidget(btn_bind)
        layout.addLayout(folder_row)

        layout.addStretch()

        # 返回 + 保存
        btn_row = QHBoxLayout()
        btn_back = QPushButton("返回")
        btn_back.clicked.connect(self._show_summary_page)
        btn_back.setStyleSheet(
            "QPushButton { background: #F5F5F5; border: 1px solid #E0E0E0; "
            "border-radius: 4px; padding: 8px; }"
        )
        btn_row.addWidget(btn_back)

        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(
            "QPushButton { background: #1976D2; color: white; border: none; "
            "border-radius: 4px; padding: 8px; }"
        )
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        return page

    def _populate_edit(self) -> None:
        if self._project is None:
            return
        p = self._project
        self._edit_fields["number"].setText(p.project_number)
        self._edit_fields["name"].setText(p.name)
        self._edit_fields["client"].setText(p.client)
        self._edit_fields["inspection_type"].setText(p.inspection_type)
        self._edit_amount.setText(str(p.amount))
        self._edit_folder.setText(str(p.folder_path) if p.folder_path else "")
        if hasattr(p.created_at, 'date'):
            from PySide6.QtCore import QDate
            d = p.created_at.date()
            self._edit_date.setDate(QDate(d.year, d.month, d.day))
        self._edit_folder.setText(str(p.folder_path) if p.folder_path else "")
        if hasattr(p.created_at, 'date'):
            from PySide6.QtCore import QDate
            d = p.created_at.date()
            self._edit_date.setDate(QDate(d.year, d.month, d.day))

    def _on_save(self) -> None:
        if self._project is None or self._service is None:
            return
        p = self._project
        folder_text = self._edit_folder.text().strip()
        updated = Project(
            project_id=p.project_id,
            project_number=self._edit_fields["number"].text().strip() or p.project_number,
            name=self._edit_fields["name"].text().strip() or p.name,
            client=self._edit_fields["client"].text().strip(),
            inspection_type=self._edit_fields["inspection_type"].text().strip(),
            amount=float(self._edit_amount.text() or 0),
            created_at=datetime.combine(
                self._edit_date.date, p.created_at.time().replace(tzinfo=p.created_at.tzinfo)
            ) if hasattr(self._edit_date, 'date') and p.created_at else p.created_at,
            folder_path=Path(folder_text) if folder_text else None,
            original_record_done=p.original_record_done,
            notes=p.notes,
            stages=p.stages,
            updated_at=p.updated_at,
        )
        self._service.update_project(updated)
        self._project = self._service.get_project(p.project_id)
        self._show_summary_page()
        self._populate_summary()
