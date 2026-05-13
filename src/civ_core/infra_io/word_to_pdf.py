"""Word/WPS → PDF 批量转换的 IO 层。

为什么放 infra_io：
  • 走 COM (pywin32) —— 这是 IO 边界，禁止在 core/ 或 ui/ 直接调用
  • 进程级资源（Word.Application）必须 try/finally 释放（CLAUDE.md 总纲）
  • pythoncom.CoInitialize/Uninitialize 在 worker 线程也必须配对

对外 API：
  convert_one(in_path, out_dir)             单文件转换；返回输出 PDF 路径
  convert_batch(inputs, out_dir, progress_cb=None)  批量；返回 ConvertResult

实现细节：
  • SaveAs FileFormat=17 是 PDF 的 Word 内部常量（wdFormatPDF）
  • 用 DispatchEx 而非 Dispatch —— DispatchEx 强制起新进程，避免与用户当前
    打开的 Word 窗口共用进程导致互相阻塞 / 弹窗
  • 失败优先尝试 Word，再尝试 WPS（DispatchEx("KWPS.Application")）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# Word 内置 FileFormat 常量：17 = wdFormatPDF
_WD_FORMAT_PDF = 17


# ──────────────────────────────────────────────────────────────────
# 异常
# ──────────────────────────────────────────────────────────────────
class Word2PdfError(RuntimeError):
    """Word 转 PDF 的业务异常。hint 字段供 UI 三段式提示用。"""

    hint: str

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


@dataclass(slots=True)
class ConvertResult:
    """批量转换结果。

    written  成功转换的输出 PDF 路径列表（顺序与 inputs 对应）
    failed   失败的 (输入路径, 异常) 列表；单文件失败不打断批量
    """

    written: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, Exception]] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
# COM 引擎挂载（优先 Word，回退 WPS）
# ──────────────────────────────────────────────────────────────────
def _mount_engine() -> tuple[Any, str]:
    """挂载 Word 或 WPS COM 引擎；返回 (com_app, 引擎名)。

    失败时抛 Word2PdfError —— 调用方 finally 中即使 com_app 为 None 也安全。

    为什么不复用 utils/word_com.py：那里只有 word_optimized_environment
    上下文管理器（关耗时选项加速 Find/Replace），不负责"挂载/卸载 Word 进程"。
    本函数的职责是"创建一个独立的 Word/WPS 实例并返回"，二者职责不同。
    """
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as e:
        raise Word2PdfError(
            "未安装 pywin32（win32com）",
            hint="请运行 `uv add pywin32`。Word 转 PDF 必须有 pywin32。",
        ) from e

    # 1) 先试 Microsoft Word
    try:
        app = win32com.client.DispatchEx("Word.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        log.info("已挂载 Microsoft Word 引擎")
        return app, "Microsoft Word"
    except Exception as word_err:
        log.debug("Word 挂载失败，尝试 WPS：%s", word_err)

    # 2) 回退 WPS
    try:
        app = win32com.client.DispatchEx("KWPS.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        log.info("已挂载 WPS Office 引擎")
        return app, "WPS Office"
    except Exception as wps_err:
        raise Word2PdfError(
            "未检测到 Word 或 WPS 环境",
            hint=(
                "Word 转 PDF 需要本机安装 Microsoft Word 或 WPS Office。"
                "请确认任一软件已正确安装、能正常启动。"
            ),
        ) from wps_err


def _quit_engine(app: Any) -> None:
    """安全关闭 COM 引擎。任何失败 warn 不抛 —— finally 中调用，不能再次抛错。"""
    if app is None:
        return
    try:
        app.Quit()
        log.debug("COM 引擎已 Quit")
    except Exception as e:
        log.warning("COM 引擎 Quit 失败（已忽略）：%s", e)


# ──────────────────────────────────────────────────────────────────
# 单文件转换
# ──────────────────────────────────────────────────────────────────
def _convert_one_with_app(app: Any, in_path: Path, out_path: Path) -> None:
    """已有 COM 引擎的情况下转一个文件；不负责 Quit。

    抽出来是为了批量场景共用一个 Word 进程（启动 Word 很慢，~3 秒）。
    """
    if not in_path.is_file():
        raise Word2PdfError(
            f"输入文件不存在：{in_path}",
            hint="请检查路径或重新选择文件。",
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = None
    try:
        # ReadOnly=1 防止修改原文档；FileFormat=17=wdFormatPDF
        # 路径必须是绝对路径 + 字符串（COM 不接 PathLike）
        doc = app.Documents.Open(str(in_path.resolve()), ReadOnly=1)
        doc.SaveAs(str(out_path.resolve()), FileFormat=_WD_FORMAT_PDF)
    except Exception as e:
        raise Word2PdfError(
            f"转换失败 {in_path.name}：{e}",
            hint=(
                "可能原因：文件被加密 / 文件损坏 / Word 自动恢复弹窗未关闭。"
                "请用 Word 打开该文件确认能正常浏览，再重试。"
            ),
        ) from e
    finally:
        if doc is not None:
            try:
                doc.Close(0)  # 0=wdDoNotSaveChanges
            except Exception as close_err:
                log.warning("关闭文档失败（已忽略）：%s", close_err)


def convert_one(in_path: Path | str, out_dir: Path | str) -> Path:
    """单文件转换：单独起 Word 进程跑完关掉。

    适用于只转 1~2 个文件的场景；多文件请用 convert_batch（共享 Word 实例）。

    out 文件名 = 输入 stem + ".pdf"，落到 out_dir。
    """
    import pythoncom  # type: ignore[import-untyped]

    src = Path(in_path)
    out_dir_p = Path(out_dir)
    out_path = out_dir_p / f"{src.stem}.pdf"

    pythoncom.CoInitialize()
    app = None
    try:
        app, name = _mount_engine()
        log.info("convert_one 引擎：%s", name)
        _convert_one_with_app(app, src, out_path)
    finally:
        _quit_engine(app)
        pythoncom.CoUninitialize()

    log.info("Word→PDF 完成：%s → %s", src.name, out_path)
    return out_path


# ──────────────────────────────────────────────────────────────────
# 批量转换（共享 Word 进程）
# ──────────────────────────────────────────────────────────────────
def convert_batch(
    inputs: list[Path | str],
    out_dir: Path | str,
    *,
    progress_cb: Callable[[int, int, Path], None] | None = None,
) -> ConvertResult:
    """批量转换：起 1 个 Word 进程跑完所有文件。

    单文件失败不打断批量；记入 ConvertResult.failed 由 UI 决定怎么报。
    progress_cb(done, total, current_input) 每完成 1 个调用 1 次（成败都调）。
    回调内异常会被吞掉 + warn，避免拖垮整批。
    """
    import pythoncom  # type: ignore[import-untyped]

    if not inputs:
        raise Word2PdfError(
            "输入列表为空",
            hint="请至少添加 1 个 Word 文件再开始转换。",
        )

    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    total = len(inputs)
    result = ConvertResult()

    pythoncom.CoInitialize()
    app = None
    try:
        app, name = _mount_engine()
        log.info("convert_batch 引擎：%s | 共 %d 个文件", name, total)

        for i, raw in enumerate(inputs, start=1):
            src = Path(raw)
            out_path = out_dir_p / f"{src.stem}.pdf"
            try:
                _convert_one_with_app(app, src, out_path)
                result.written.append(out_path)
            except Exception as e:
                # 单文件失败：记下来继续下一个，不中断批量
                log.error(
                    "批量转换第 %d/%d 个失败：%s — %s", i, total, src.name, e
                )
                result.failed.append((src, e))

            if progress_cb is not None:
                try:
                    progress_cb(i, total, src)
                except Exception as cb_err:
                    log.warning(
                        "progress_cb 抛异常（已忽略）：%s", cb_err
                    )
    finally:
        _quit_engine(app)
        pythoncom.CoUninitialize()

    log.info(
        "批量 Word→PDF 完成：成功 %d / 失败 %d / 总 %d",
        len(result.written), len(result.failed), total,
    )
    return result


__all__ = [
    "ConvertResult",
    "Word2PdfError",
    "convert_batch",
    "convert_one",
]
