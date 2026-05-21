"""api handlers：各业务领域的 RPC 方法集合，按模块分。

T5.5 Step 4 之后 leeb.* 全部迁到 C# sidecar（civ-doc），Python 这边只剩
工作区 / 文件树 + 已交付的 Python 工具（plot_curves / pdf_tools / word2pdf）。
"""

from civ_core.api.handlers import (
    files,
    pdf_tools,
    plot_curves,
    word2pdf,
    workspace,
)

__all__ = ["files", "pdf_tools", "plot_curves", "word2pdf", "workspace"]
