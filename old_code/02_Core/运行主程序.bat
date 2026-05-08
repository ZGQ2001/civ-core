@echo off
:: 自动激活虚拟环境
call .venv\Scripts\activate
chcp 65001
python "02_Core/main.py "
pause 