@echo off
:: 自动激活虚拟环境
call .venv\Scripts\activate
chcp 65001
uv run python -m civil_auto.main
pause 