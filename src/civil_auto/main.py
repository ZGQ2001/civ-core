"""程序唯一入口点。"""

import sys
from pathlib import Path

# 把 src/ 加入 path，确保 civil_auto 包可被子进程找到
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from civil_auto.ui.main_window import MainWindow


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("工程自动化主控制台")
    app.setOrganizationName("CivilAuto")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
