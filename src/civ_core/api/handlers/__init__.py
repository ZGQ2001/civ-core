"""api handlers：各业务领域的 RPC 方法集合，按模块分。

T5.5 后 leeb.* / workspace.* 已迁 C# sidecar（civ-doc）。Python 端只剩
文件树 + Python 专属工具（plot_curves / pdf_tools / word2pdf）。
"""

from civ_core.api.handlers import (
    files,
    pdf_tools,
    plot_curves,
    word2pdf,
)

__all__ = ["files", "pdf_tools", "plot_curves", "word2pdf"]
