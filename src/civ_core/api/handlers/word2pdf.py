"""word2pdf handlers：Word → PDF 批量转换 RPC 接口。

RPC 方法（前缀 "word2pdf."）：
  word2pdf.convert(inputs, output_dir)
    -> {written: [str], failed: [{path, error}], total: int}

底层走 utils.word_com（COM）→ infra_io.word_to_pdf.convert_batch。
同步阻塞（COM 单进程跑完所有文件）；无流式进度（与 plot_curves 同决策）。
"""

from __future__ import annotations

from pathlib import Path

from civ_core.infra_io.word_to_pdf import convert_batch

__all__ = ["convert"]


def convert(inputs: list[str], output_dir: str) -> dict:
    result = convert_batch([Path(p) for p in inputs], Path(output_dir))
    return {
        "written": [str(p) for p in result.written],
        "failed": [
            {"path": str(src), "error": f"{type(e).__name__}: {e}"}
            for src, e in result.failed
        ],
        "total": len(inputs),
    }
