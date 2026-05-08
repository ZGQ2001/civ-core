"""infra_io：所有文件 I/O 操作集中在此层。

架构红线（v2.3 总纲）：
  • core/ 层禁止直接读写文件，必须经由 infra_io/ 暴露的函数
  • UI 层（ui/）禁止 import openpyxl / python-docx 这类 IO 库
  • 旧路径 civ_core.io.* / civ_core.models.* 仍保留只读，
    新代码一律从 infra_io / domain 引用
"""

from __future__ import annotations
