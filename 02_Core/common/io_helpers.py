"""文件 I/O、外部进程调用、stdout 行缓冲修复等系统层工具。

每个函数纯靠参数工作，不依赖全局配置。
"""

import os
import subprocess
import sys
from tkinter import filedialog


def enable_line_buffered_stdout() -> None:
    """让 print 实时刷新，避免 IDE / 重定向场景下日志被块缓冲攒到最后才一次性输出。

    Python 3.7+ 才有 sys.stdout.reconfigure；类型存根可能没标，所以用 getattr 兜底。
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(line_buffering=True)
        except Exception:
            pass


def pick_excel_file(title: str = "选择 Excel 文件") -> str:
    """弹原生文件对话框选 Excel，返回绝对路径或空字符串（用户取消）。

    单独抽出来是因为：要预读 Sheet 列表才能在主参数表单里给下拉框，所以必须分两步弹窗。
    """
    return filedialog.askopenfilename(
        title=title,
        filetypes=[("Excel 文件", "*.xlsx *.xlsm *.xls"), ("所有文件", "*.*")],
    )


def read_sheet_names(excel_path: str) -> list[str]:
    """读取 Excel 的 sheet 列表。失败返回空列表（调用方判空决定是否中止）。"""
    # 延迟导入：避免在不需要 pandas 的工具里也强制加载它
    import pandas as pd

    try:
        sheet_names = pd.ExcelFile(excel_path).sheet_names
        return [str(name) for name in sheet_names]
    except Exception as e:
        print(f"❌ 读取 Sheet 列表失败: {e}")
        return []


def kill_winword_processes(reason: str = "") -> None:
    """强制结束所有 WINWORD.EXE，避免 COM 附着到挂着隐藏弹窗的僵尸 Word。

    会顺带杀掉用户正在用的 Word！调用方需要在文档里提示用户先存盘。
    """
    tag = f"（{reason}）" if reason else ""
    print(f"🧹 正在清理残留 WINWORD.EXE 进程{tag}...")
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "WINWORD.EXE", "/T"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print("   ↳ 已结束残留 Word 进程")
        else:
            # returncode 128 / 1 通常代表"没有匹配进程"，正常
            print("   ↳ 没有发现需要清理的 Word 进程")
    except Exception as e:
        print(f"   ⚠️ taskkill 调用失败（忽略，继续）: {e}")


def unblock_file(file_path: str) -> None:
    """移除 Windows 的"来自互联网"标记 (Zone.Identifier ADS)，避免 Word 触发受保护视图。

    对来自网盘 / 邮件 / 浏览器下载的文件特别有用 —— 否则 Word.Open 可能挂在受保护视图上。
    """
    abs_path = os.path.abspath(file_path)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f'Unblock-File -LiteralPath "{abs_path}"'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"🔓 已解除文件网络标记: {os.path.basename(abs_path)}")
        else:
            print(f"   ⚠️ Unblock-File 返回非 0（通常无标记，可忽略）: {result.stderr.strip()}")
    except Exception as e:
        print(f"   ⚠️ Unblock-File 调用失败（忽略，继续）: {e}")


def ensure_extension(filename: str, allowed: tuple, default: str | None = None) -> str:
    """如果文件名后缀不在允许列表里，补上 default（或 allowed[0]）。"""
    if filename.lower().endswith(allowed):
        return filename
    return filename + (default or allowed[0])
