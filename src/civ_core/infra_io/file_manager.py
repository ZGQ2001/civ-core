"""文件写入：原子替换 + 占用预检。

为什么要这层：
  • Windows 下 Excel / Word 拿到的文件是独占锁，matplotlib.savefig 直跑会
    在写到一半时抛 PermissionError，目标 PNG 已经被截断成 0 字节
  • 业务工具反复跑批量绘图，输出目录里同名 PNG 经常被用户用 Photos 打开预览，
    需要在动笔之前就告诉用户"先关掉那个窗口"，而不是事后留下半截文件
  • 总纲 v2.3 P0 明确："文件占用检测、原子写入、幂等输出"

对外暴露三件套：
  • check_writable(path)            预检（不存在则检查父目录可写；存在则探测独占锁）
  • atomic_writer(path)             上下文管理器，yield 临时路径，成功 os.replace 上去
  • atomic_write_bytes(path, data)  便捷版：直接把 bytes 原子写入

不做的事：
  • 不做 fsync —— 调用方负责文件 close；rename 后操作系统会按自己的策略落盘
  • 不做跨卷 rename —— mkstemp 强制把临时文件放到 path 同目录，os.replace 在
    同卷上是原子的；跨卷会 fall back 到拷贝+删除，那就不原子了
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 异常
# ──────────────────────────────────────────────────────────────────
class FileBusyError(RuntimeError):
    """目标文件被其他进程占用，无法写入。携带 hint 给 UI 三段式提示用。"""

    hint: str

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


class FileWriteError(RuntimeError):
    """原子写入流程中发生不可恢复的错误（非占用，例如父目录不存在/无写权限）。"""

    hint: str

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


# ──────────────────────────────────────────────────────────────────
# 占用预检
# ──────────────────────────────────────────────────────────────────
def check_writable(path: Path | str) -> None:
    """预检目标路径是否可写；被独占锁占用则抛 FileBusyError。

    判定逻辑：
      1. path 不存在：检查父目录存在且可写（os.W_OK）
      2. path 存在：以 'r+b' 打开试探（独占锁会立即返回 PermissionError）
         这是 Windows 上探测 Excel/Word 锁定最稳的方式

    注意：本检查与真正写入之间存在 TOCTOU 窗口（用户在两步之间打开了文件），
    atomic_writer 会在 os.replace 阶段再次失败兜底——预检只是给"友好提示"。
    """
    target = Path(path)

    if not target.exists():
        parent = target.parent
        if not parent.exists():
            # 不抛 FileBusyError——这不是占用，是路径错误
            raise FileWriteError(
                f"父目录不存在：{parent}",
                hint="请先创建目录或在 config.toml 里把 paths.* 指到一个真实存在的位置。",
            )
        if not os.access(str(parent), os.W_OK):
            raise FileWriteError(
                f"父目录不可写：{parent}",
                hint="请检查目录权限，或换一个有写权限的输出位置。",
            )
        return

    # 文件已存在：试探独占锁
    try:
        with target.open("r+b"):
            pass
    except PermissionError as e:
        raise FileBusyError(
            f"文件被占用，无法写入：{target.name}",
            hint=(
                f"路径：{target}\n"
                "请关闭可能正在使用该文件的程序（Excel / Word / 图片预览 / 杀毒扫描），"
                "然后重试。"
            ),
        ) from e
    except OSError as e:
        # 有些情况（只读卷、文件被设了只读属性）也会落到这里
        raise FileWriteError(
            f"无法以读写模式打开 {target.name}：{e}",
            hint=f"路径：{target}\n可能是只读文件或所在卷只读。",
        ) from e


# ──────────────────────────────────────────────────────────────────
# 原子写入
# ──────────────────────────────────────────────────────────────────
@contextmanager
def atomic_writer(path: Path | str) -> Iterator[Path]:
    """原子写入上下文管理器。

    用法：
        with atomic_writer(out_png) as tmp:
            fig.savefig(tmp, dpi=150)
        # __exit__ 时把 tmp 原子替换到 out_png；异常时清理 tmp，目标保持原样

    保证：
      • 目标路径在进程视角下要么是"老内容"要么是"新内容"，不会出现写到一半的截断文件
      • 临时文件与目标同目录，os.replace 在同卷上是原子的
      • 写入异常时清理临时文件，不留垃圾
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    check_writable(target)

    # 把临时文件强制放到 target.parent，确保 os.replace 跨同一卷
    fd, tmp_str = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    # mkstemp 返回的 fd 我们不用（让调用方自己 open 临时路径写）；立刻关掉
    os.close(fd)
    tmp = Path(tmp_str)
    log.debug("atomic_writer 临时路径：%s", tmp.name)

    try:
        yield tmp
    except BaseException:
        # 调用方在写入过程中失败：删掉临时文件，不动目标
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise

    # yield 正常返回 → 原子替换；这一步本身也可能因竞态被占用而失败
    try:
        os.replace(str(tmp), str(target))
    except PermissionError as e:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise FileBusyError(
            f"替换目标文件时被占用：{target.name}",
            hint=(
                f"路径：{target}\n"
                "在写入过程中，目标文件被其他程序占用了。"
                "请关闭 Excel / Word / 图片预览后重试。"
            ),
        ) from e
    except OSError as e:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise FileWriteError(
            f"原子替换失败：{target.name}：{e}",
            hint=f"路径：{target}",
        ) from e

    log.debug("atomic_writer 成功写入：%s", target.name)


def atomic_write_bytes(path: Path | str, data: bytes) -> Path:
    """便捷接口：把 bytes 原子写入到 path。"""
    target = Path(path)
    with atomic_writer(target) as tmp:
        with tmp.open("wb") as f:
            f.write(data)
    return target
