# 开发日志

> 本文件由 AI 维护，用户可读可改。每次任务结束后 AI 负责更新（表述 AI 友好）。

---

## 📌 顶部摘要

**当前状态（2026-05-21）：** 🚧 **UI 技术栈转型进行中（Tauri + React + Python sidecar）**

旧 Qt UI 因视觉天花板过不去被彻底清理。当前进度 **4.5/7**：

```
T1 ✅ Python JSON-RPC server (stdin/stdout)
T2 ✅ 前端骨架 (Vite + React + TS + Tailwind v4 + codicons)
T3 ✅ Tauri 主进程 + Python sidecar 桥 + 自画 VSCode 风顶栏
T4 ✅ 工作区 + 文件树端到端（SideBar 真实 FileTree + workspace 持久化）
T5 ✅ 工具页迁移 — 4 个工具全部 controller/Page/SettingsForm 范式 + 中间预览 + 右侧参数
     plot_curves（实时 PNG）/ data_processing（Excel 表格）/ pdf_tools（PDF 列表）/
     word2pdf（docx 列表）。data_processing 用 calcType 下拉留接口（未来加钻芯/回弹）
─────────────────── 当前在这里 ───────────────────
T5.5 🚧 加 C# sidecar
     ✅ Step 1: 建 dotnet/civ-doc/（.NET 9 + JSON-RPC server + doc.ping/version + NuGet 华为云镜像）
                + Tauri 双 sidecar (Python + C#) + SidecarRouter 按 method 前缀路由
                + 前端 App.tsx 并行 ping 两边
     ⏳ Step 2: 第一个业务方法 doc.fill_template（Word 模板填充，OpenXML SDK + 模板引擎选型）
     ⏳ Step 3: leeb 的 Excel 读取迁 xlsx.* 系列方法（合并单元格 OpenXML 原生）
T6 ⏳ 打包（PyInstaller 把 Python sidecar 打成 exe；dotnet publish 把 C# 打成 exe
        → Tauri externalBin 同时引两个）
T7 ✅ 删旧 Qt UI（提前做了 —— 见 2026-05-20 大清理）
```

### 🔀 混合架构决策（2026-05-20 晚）

**方向：Python + C# 双 sidecar，渐进迁移。** 业务底座 Python 保留；Word/Excel
重资产场景走 C#（OpenXML SDK / ClosedXML，原生强）。Tauri 同时管理两个 sidecar，
前端 `rpc(method, params)` 按 method 前缀路由：

- Python（`civ_core.api`）：`workspace.* / files.* / plot_curves.* / leeb.* / calc.*`
- C#（`civ-doc.api`，T5.5 新建）：`doc.* / xlsx_complex.*`

**渐进策略**：一次只迁一个方法。第一次 Word 报告功能时直接 C# 写，老 Python
方法不动。可以永远停在某个 Python/C# 比例，不强求全切。

**业务底座状态：** ① 画图、② INSP-001 里氏硬度 / INSP-002 钻芯法、③ PDF 工具、④ Word→PDF 计算与 IO 层完整可用（**322 pytest / ruff 0 / healthcheck 6/6** 全过）。前端 UI 全 4 个工具页可用。C# sidecar 链路 `doc.ping/version` 已通。

**下一步具体动作（T5.5 Step 2）：**
- 选业务用例：Word 模板填充 `doc.fill_template(template_path, context)` —— 对齐 docxtpl 行为（`{{var}}` 变量、`{%for%}` 循环、`{%if%}` 条件）
- 模板引擎选型决策：
  - A. 自己写最简单的 `{{var}}` 替换 + 段落迭代（轻、可控、不依赖外部包）
  - B. Scriban（.NET 流行模板引擎，类 Jinja2）+ OpenXML SDK 段落 walk
  - C. 找 docxtemplater 等专门 Word 模板包（已封装段落 / 表格行 / 图片占位）
- 看用户现有 `templates/*.docx` 的模板复杂度来选 —— 简单填空 A 够；复杂表格循环就 B/C

**T5.5 起手清单（Step 1 已完成）：**
1. ✅ 新建 `dotnet/civ-doc/` 子项目（.NET 9）+ NuGet 华为云镜像
2. ✅ JSON-RPC over stdin/stdout 协议（Server/JsonRpcServer.cs 对齐 Python server.py）
3. ⏳ 第一个业务方法 `doc.fill_template`（Step 2）
4. ⏳ `xlsx.*` 系列方法（Step 3，把 leeb Excel 读取切过来）
5. ✅ Tauri `sidecar.rs` 抽通用 `JsonRpcSidecar` + `SidecarRouter` 按 method 前缀路由；`lib.rs` 启动时 spawn 两个 sidecar
6. ⏳ T6 阶段：PyInstaller + dotnet publish 都放进 `tauri.conf.json` 的 externalBin

---

## 🧩 架构（双语言）

```
┌──────────────────────── frontend/ ─────────────────────────┐
│  Vite + React + TS + Tailwind v4 + codicons                │
│  TitleBar / ActivityBar / SideBar / EditorArea / StatusBar │
└──────────────────┬─────────────────────────────────────────┘
                   │ invoke('rpc_call', { method, params })
┌──────────────────▼─────────────────────────────────────────┐
│  frontend/src-tauri/ (Tauri 2.11, Rust)                    │
│  spawn Python sidecar (kill_on_drop)                       │
│  PythonSidecar.call(): stdin 写请求 / stdout 读响应（Mutex 串行）│
└──────────────────┬─────────────────────────────────────────┘
                   │ JSON-RPC 2.0 over stdin/stdout
┌──────────────────▼─────────────────────────────────────────┐
│  src/civ_core/api/ (Python)                                │
│  Dispatcher.handle_raw() → handlers/{workspace,files,...} │
└──────────────────┬─────────────────────────────────────────┘
                   ▼
                core/ → infra_io/ → domain/
              （业务底座，与 UI 无关，可单独 CLI 跑）
```

---

## 📦 已交付（按 commit 时间倒序）

| commit | 内容 |
|---|---|
| `1ae71f1` 2026-05-21 | T5 完结：word2pdf 工具页对齐范式 + word2pdf.inspect RPC（读 docx 段落数 + size + Word 缓存 Pages）+ 3 个 pytest |
| `7175729` 2026-05-21 | pdf_tools 工具页对齐范式（3 个 mode 共享 state） + pdf_tools.inspect RPC（PDF 页数 + size） + fix 数据处理图标 codicon-calculator 不存在→透明 改 symbol-method |
| `94751e0` 2026-05-21 | leeb_hardness → data_processing 模块改名 + Page 顶部加「计算类型」下拉（留接口给未来钻芯/回弹）+ 去 INSP 字眼 + ActivityBar 改名「数据处理」 |
| `c77d156` 2026-05-21 | leeb 工具页对齐 plot_curves 范式（中间表格预览 + 右侧参数）+ 后端 leeb.preview_excel RPC + 抽公共 _shared/forms.tsx |
| `dbb7921` 2026-05-21 | plot_curves 数据对照条只显示图引用的列 + CONTEXT 同步 |
| `bca7883` 2026-05-21 | fix plot_curves 数据对照条永远空（stem 反查 id 失配，改按 BuildSummary 跳过行号反推） |
| `36641b7` 2026-05-21 | fix plot_curves 对照视图改上下 + 跳转行号 + 深色 spinbox |
| `92057c4` 2026-05-21 | refactor plot_curves 一预设一曲线 + UI 改名 预设→曲线 |
| `ca9accf` 2026-05-21 | 移 AI 文档到 .ai/ + 更新 CLAUDE.md 同步新架构 |
| `[本次]` 2026-05-20 | 大清理：删旧 Qt UI（30+ 文件）+ 重写 logger.py 去 QtLogBridge + 重写 main.py 去 GUI 分支 + healthcheck 改 6 项 + pyproject 去 pyside6/qfluentwidgets/pytest-qt + 重写 CLAUDE.md/PROGRESS.md 到 200 行内 |
| `921e9bb` 2026-05-20 | 自画 VSCode 风 TitleBar（decorations=false + 30px 顶栏 + chrome-* 按钮 + 拖动区）+ `run.sh` 一键启动 + CLAUDE.md 加中国镜像表 |
| `dc1f53a` 2026-05-20 | T3 Tauri 主进程 + sidecar.rs（PythonSidecar Mutex 串行 RPC）+ `frontend/src-tauri/.cargo/config.toml` 字节镜像 |
| `6af15b3` 2026-05-20 | T2 Vite/React/Tailwind/codicons 前端骨架 + react-resizable-panels（Group/Panel/Separator API） |
| `084033e` 2026-05-20 | T1 Python JSON-RPC server + workspace/files handlers + 25 个测试 |
| `c731acc` 2026-05-19 | 删旧项目看板（22 文件，包括 SQLite 持久化层） |
| `7a8a076` 2026-05-19 | 里氏硬度 Excel 格式固化 + 多批支持 + 角度语义修正 |
| `0bac5aa` 2026-05-19 | INSP-001 里氏硬度切到完整可用 |
| `47db417` 2026-05-19 | INSP-002 钻芯法计算函数底座 |

---

## 🗓️ 会话历史

### [2026-05-20] UI 技术栈转型 + 旧代码大清理

**起因：** 用户对 Qt + qfluentwidgets 视觉多轮调整后仍不满意 ——"过家家"、"不像 VSCode"。Qt 字体抗锯齿/动画质感/图标风格的天花板不可弥补。

**决策：** 走 Tauri + Web 路线。业务底座 Python 完全保留；新增 `api/` 暴露 JSON-RPC；UI 全在 `frontend/` 用 React 重写。

**已删（30+ 源文件 + 20 个 UI 测试 + pyside6/qfluentwidgets/pytest-qt 三个依赖）：**
- 整个 `src/civ_core/ui/`
- 整个 `src/civ_core/apps/`
- `infra_io/file_dialogs.py`、`infra_io/workspace_settings.py`（已被 `~/.civ-core/workspace.json` 替代）
- `utils/logger.py` 里的 `QtLogBridge` / `_QtSignalHandler` / `get_qt_bridge`（重写成纯 stdlib logging）
- `main.py` 的 `_launch_gui` 分支（no-args 现在输出迁移提示）
- `tests/test_*_view.py` / `test_*_panel.py` / `test_*_pane.py` / `test_curves_editor.py` / `test_log_panel.py` / `test_splitter_persistence.py` / `test_ui_bugfix_resize_and_preset.py` / `test_preset_undo.py` / `test_preset_form_panel.py` / `test_preset_list_buttons.py` / `test_preset_accordion_panel.py` / `test_preset_validation.py`（UI staticmethod 测试） / `test_activity_bar.py` / `test_breadcrumb_bar.py` / `test_project_tree.py` / `test_shell_window.py` / `test_agent_panel.py` / `test_workspace_settings.py`

**保留：** `domain/ core/ infra_io/ configs/ utils/`（除 logger 删 Qt 部分外）全部业务底座；`api/` 新增；`tests/` 业务测试全保留。

**已交付节点：** T1（API server）→ T2（前端骨架）→ T3（Tauri 桥）→ 自画 VSCode 风顶栏 → 大清理。

---

### [2026-05-19] 删项目看板

转 Tauri 决策的前奏 —— 用户已经放弃旧 Qt UI 中复杂的项目看板（SQLite 持久化 + 4 档筛选 + 排序 + Drawer + 暂存归档）。删 22 个文件。

---

### [2026-05-14] 主管线定调

业务主管线（前端工具页面）：
```
① 画图 ✅ → ② INSP-001/002 计算 ✅ → ③ 数据生成 ⏳ → ④ 报告填充 ⏳ → ⑤ Word 报告 ⏳
```
规范评定独立插在数据生成和报告填充之间，下拉选规范；Word 排版不单独设模块，模板预排版，auto_filler 只填数据不动格式。

---

## 🧠 关键架构决策

| 决策 | 内容 | 原因 |
|---|---|---|
| UI 技术栈 | Tauri + Web 替代 Qt | Qt 视觉天花板不可弥补；Web 生态可任意复刻 VSCode |
| 后端混合 | Python + C# 双 sidecar，渐进迁移 | Word/Excel 重资产场景 C# OpenXML 工具链强；Python 业务底座保留不重写；按方法前缀路由互不干扰 |
| Python 后端形态 | JSON-RPC over stdin/stdout（sidecar） | 协议极简，绕开 IPC 复杂度；前端 invoke 直接转发 |
| stdout 协议流 | 不可被 logger 污染 | api/__main__.py 自己挂"文件 + stderr" handler，绝不上 stdout |
| 预设双路径 | 系统在 `presets/`，用户在 `~/.civ-core/` | 防软件更新覆盖用户数据 |
| 预设系统目录 | 运行时只读 | 静态资源原则；开发者通过 git 维护 |
| 数据契约 | dataclass + `__post_init__` | 不引 pydantic，保持依赖轻量 |
| 镜像 | 字节 rsproxy.cn（Cargo + rustup） | 中国直连国外源超时 |
| 文档分层 | CLAUDE.md（规则，用户维护）+ PROGRESS.md（状态，AI 维护） | 职责分离 |

---

## ⏭️ 明天恢复指南

1. `cd D:/CodeProjects/civ-core` → `git status`（应该 clean）→ `git pull`（如果有别处提交）
2. 跑 `bash run.sh` 看 Tauri 应用能否起 → 状态栏右下应显示"后端就绪 (pong)"
3. 跑 `uv run --frozen python scripts/healthcheck.py` 看 6 项全过
4. 跑 `uv run --frozen pytest` 看 305 个测试全过
5. 开始 **T4**：照本文档「下一步具体动作」一节做。前端工作集中在 `frontend/src/components/SideBar.tsx`，需要 Tauri dialog plugin（已在 `Cargo.toml` 引入 `tauri-plugin-dialog`），调用方式见 [Tauri 2 dialog docs](https://v2.tauri.app/plugin/dialog/)。
