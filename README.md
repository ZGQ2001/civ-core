# 筑核（civ-core）

土木工程检测内业报告自动化工具。

输入 Excel/CSV/Word → 自动完成数据格式化、规范评定、图表生成、Word 报告填充。

Windows 平台 · 内部自用 · AI 辅助开发 · 非商业分发


## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vite + React 19 + TypeScript + Tailwind v4 |
| 桌面壳 | Tauri 2.11（Rust） |
| RPC 协议 | JSON-RPC 2.0 over stdin/stdout |
| 后端 | Python 3.12+（uv 管理） |
| Excel 读写 | openpyxl |
| Word 填充 | python-docx + docxtpl |
| 规范查表 | SQLite（stdlib sqlite3） |
| 配置 | TOML |
| 测试 / Lint | pytest / ruff |
| CI | GitHub Actions（Windows） |


## 当前功能

- **绘图工具** — 导入 Excel，选择预设，批量出曲线图
- **里氏硬度（INSP-001）** — 钢材硬度 → 抗拉强度推定，支持多批/角度修正/厚度修正
- **钻芯法（INSP-002）** — 混凝土芯样抗压强度推定
- **回弹法（INSP-003）** — 混凝土回弹强度推定（骨架就绪）
- **Word → PDF** — 批量转换（WPS/Word COM）
- **PDF 工具** — 合并 / 分拆
- **工作区管理** — 自动创建项目文件夹结构
- **预设系统** — 系统预设 + 用户自定义，保存/复制/删除


## 启动

```bash
# 开发模式（一键 Tauri + Vite + Python sidecar）
bash run.sh

# 或手动启动
cd frontend && npm run tauri:dev
```


## 命令行（脱壳用）

```bash
uv run python -m civ_core.main --list-presets
uv run python -m civ_core.main --tool plot_curves --input data.xlsx --preset 预设名 --output ./输出/
uv run pytest
uv run ruff check .
uv run python scripts/healthcheck.py
```


## 目录结构

```
civ-core/
├── frontend/                React UI（Vite + TS + Tailwind）
│   ├── src/                 组件、RPC 调用
│   └── src-tauri/           Tauri 2 主进程（Rust）+ sidecar 管理
├── src/civ_core/
│   ├── api/                 JSON-RPC 后端（stdin/stdout）
│   ├── core/                业务逻辑（计算、出图）
│   ├── infra_io/            IO 层（Excel/Word/PDF/SQLite）
│   ├── domain/              数据契约（dataclass）
│   ├── configs/             配置加载（TOML）
│   └── utils/               日志/异常/路径/COM
├── docs/
│   ├── civil_kb/            土木知识库（公式 + SOP）
│   └── dev_journal/         开发日志（PROGRESS.md）
├── tests/                   305+ 条 pytest
├── presets/                 系统预设（只读）
├── ~/.civ-core/             用户数据（预设/工作区/规范库/日志）
├── run.sh                   一键启动脚本
├── pyproject.toml           Python 项目配置
├── CLAUDE.md                AI 助手开发规范
└── config.toml              运行时配置
```


## 质量

- 305+ 个测试，ruff 零警告
- healthcheck 6/6 端到端自检（配置 → 预设 → CLI → 规范库 → 计算 → API）
- CI：GitHub Actions，每次 push 自动 ruff + pytest + healthcheck
