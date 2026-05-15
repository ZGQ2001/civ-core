"""ProjectDrawer：右侧滑出抽屉面板。

覆盖主区域约 40%，QPropertyAnimation 控制滑入/滑出。
内部 QStackedWidget 两层：摘要页 ↔ 完整编辑页。
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import (
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

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import Project, StageStatus


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

    def open(self) -> None:
        if self._project is None:
            return
        self._animate_to(self._DRAWER_WIDTH)

    def close(self) -> None:
        self._animate_to(0)
        # 动画结束后重置 fixedWidth，让主视图恢复全宽
        if self._animation is not None:
            self._animation.finished.connect(lambda: self.setFixedWidth(0))

    # ════════════════════════════════════════════════════════════
    # 内部
    # ════════════════════════════════════════════════════════════
    def _animate_to(self, target: int) -> None:
        if self._animation is not None and self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
        self._animation = QPropertyAnimation(self, b"maximumWidth")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(self.maximumWidth())
        self._animation.setEndValue(target)
        self._animation.start()

        if target > 0:
            self.setFixedWidth(self._DRAWER_WIDTH)

    def _show_summary_page(self) -> None:
        self._stack.setCurrentIndex(0)

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

        self._summary_record = QLabel()
        self._summary_record.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._summary_record)

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
        self._stages_layout.setSpacing(4)
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

        return page

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

        # 重建阶段列表
        while self._stages_layout.count():
            item = self._stages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, stage in enumerate(p.stages):
            row = QHBoxLayout()
            row.setSpacing(8)
            indicator = "✅" if stage.status == StageStatus.COMPLETED else (
                "●" if stage.status == StageStatus.IN_PROGRESS else "○"
            )
            btn = QPushButton(f"{indicator}  {stage.name}")
            btn.setFlat(True)
            btn.setStyleSheet(
                "QPushButton { text-align: left; font-size: 12px; padding: 4px 8px; "
                "border: 1px solid transparent; border-radius: 4px; color: #212121; }"
                "QPushButton:hover { background: #F0F0F0; border-color: #E0E0E0; }"
            )
            # 点击切换阶段状态：NOT_STARTED → IN_PROGRESS → COMPLETED → NOT_STARTED
            btn.clicked.connect(lambda checked, pid=p.project_id, sn=stage.name, ss=stage.status: self._toggle_stage(pid, sn, ss))
            row.addWidget(btn)
            row.addStretch()
            self._stages_layout.addLayout(row)

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
        layout.setSpacing(8)

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

    def _on_save(self) -> None:
        if self._project is None or self._service is None:
            return
        p = self._project
        updated = Project(
            project_id=p.project_id,
            project_number=self._edit_fields["number"].text().strip() or p.project_number,
            name=self._edit_fields["name"].text().strip() or p.name,
            client=self._edit_fields["client"].text().strip(),
            inspection_type=self._edit_fields["inspection_type"].text().strip(),
            amount=float(self._edit_amount.text() or 0),
            folder_path=p.folder_path,
            original_record_done=p.original_record_done,
            notes=p.notes,
            stages=p.stages,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        self._service.update_project(updated)
        self._project = self._service.get_project(p.project_id)
        self._show_summary_page()
        self._populate_summary()
