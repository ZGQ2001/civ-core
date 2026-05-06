"""app 子包：桌面应用的"装配厂"。

这一层只负责把进程拼装起来 —— 加载配置、初始化日志、创建 QApplication、
拉起主窗口、跑事件循环。任何业务逻辑都不应进入此层；具体的工具页面在 ui/。

入口点 = bootstrap.run() （见 main.py 的 GUI 分支）。
"""

from __future__ import annotations
