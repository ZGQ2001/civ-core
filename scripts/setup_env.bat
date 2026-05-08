@echo off
REM ─────────────────────────────────────────────────────────────────
REM 筑核 (civ-core) — 一键创建虚拟环境 + 安装依赖
REM 用法：双击运行，或在终端 .\scripts\setup_env.bat
REM ─────────────────────────────────────────────────────────────────

setlocal
chcp 65001 >nul
cd /d "%~dp0\.."

echo.
echo === 1/3  生成目录骨架 ===
if not exist .venv (
    py -3.12 -m venv .venv
)

call .venv\Scripts\activate.bat

python scripts\init_layout.py

echo.
echo === 2/3  升级 pip ===
python -m pip install --upgrade pip --quiet

echo.
echo === 3/3  安装依赖 ===
pip install -r requirements.txt

echo.
echo ✅ 环境就绪。现在可以双击 run.bat 启动主程序。
pause
endlocal
