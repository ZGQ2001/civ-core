"""api handlers：各业务领域的 RPC 方法集合，按模块分。

T5.5 后 leeb.* / workspace.* / files.* / pdf_tools.* 已迁 C# sidecar（civ-doc）。
Python 端只剩 plot_curves（matplotlib）与 word2pdf（COM 待迁）。
"""

from civ_core.api.handlers import (
    plot_curves,
    word2pdf,
)

__all__ = ["plot_curves", "word2pdf"]
