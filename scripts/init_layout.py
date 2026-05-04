"""一键生成项目目录骨架（幂等：已存在的目录不报错）。

用法：
    python scripts/init_layout.py [project_root]

不指定参数时，以脚本所在文件的上一级作为项目根。
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_NAME = "civil_auto"

# 目录树（相对于项目根）
DIRS: list[str] = [
    ".vscode",
    f"src/{PACKAGE_NAME}",
    f"src/{PACKAGE_NAME}/ui",
    f"src/{PACKAGE_NAME}/ui/components",
    f"src/{PACKAGE_NAME}/ui/windows",
    f"src/{PACKAGE_NAME}/core",
    f"src/{PACKAGE_NAME}/io",
    f"src/{PACKAGE_NAME}/models",
    f"src/{PACKAGE_NAME}/config",
    f"src/{PACKAGE_NAME}/utils",
    "templates",
    "data/raw",
    "data/output",
    "tests",
    "logs",
    "scripts",
]

# 需要带 __init__.py 的 Python 包目录
PACKAGE_DIRS: list[str] = [
    f"src/{PACKAGE_NAME}",
    f"src/{PACKAGE_NAME}/ui",
    f"src/{PACKAGE_NAME}/ui/components",
    f"src/{PACKAGE_NAME}/ui/windows",
    f"src/{PACKAGE_NAME}/core",
    f"src/{PACKAGE_NAME}/io",
    f"src/{PACKAGE_NAME}/models",
    f"src/{PACKAGE_NAME}/config",
    f"src/{PACKAGE_NAME}/utils",
    "tests",
]

# 数据目录占位（让 git track 空目录）
GITKEEP_DIRS: list[str] = ["data/raw", "data/output", "logs"]


def main() -> int:
    # 在 Windows GBK 控制台下也能稳跑：强制 stdout 走 utf-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    root = (
        Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    )

    print(f"[ROOT] {root}")

    for rel in DIRS:
        d = root / rel
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [dir]  {rel}")

    for rel in PACKAGE_DIRS:
        init = root / rel / "__init__.py"
        if not init.exists():
            init.touch()
            print(f"  [pkg]  {rel}/__init__.py")

    for rel in GITKEEP_DIRS:
        keep = root / rel / ".gitkeep"
        if not keep.exists():
            keep.touch()
            print(f"  [keep] {rel}/.gitkeep")

    print("\n[OK] Layout ready. Now run: pip install -r requirements.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
