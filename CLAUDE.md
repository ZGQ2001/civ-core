## 项目说明

项目名 `civ-core`（筑核）：无编程经验的土木检测从业者，用 AI 辅助编程做的内业报告自动化辅助工具。接收 Excel/CSV/Word，自动化完成数据格式化、规范评定、图表生成、Word 报告填充。Windows 平台，内部自用。

**2026-05-20 UI 技术栈转型 + 后端混合架构**：Qt + qfluentwidgets 视觉天花板过不去，转 Tauri + React 前端。后端走 **Python + C# 双 sidecar 渐进迁移**：业务计算 + 文件 IO 留 Python（已交付），Word/Excel 重资产场景 T5.5 起加 C#（.NET 9 + OpenXML SDK）。Tauri 同时管理两个 sidecar，前端 `rpc(method, params)` 按 method 前缀路由 —— 互不干扰，可永远停在某个比例不强求全切。

---

## 工作流

1. 会话开始 `git add . && git commit -m "chore: 会话开始检查点"` → 读 `.ai/PROGRESS.md` 顶部摘要 + `.ai/CONTEXT.md` 当前焦点 → 报告状态/待办/下一步 → 确认后动手
2. 单步骤 `git add . && git commit -m "feat: 完成 xxx"`（commit message 不用 emoji）
3. 新增/修改文件 → 先写 pytest 拦边界 → 写实现 → `uv run --frozen ruff check .` → `uv run --frozen pytest` → `uv run --frozen python scripts/healthcheck.py`
4. 阶段结束 → 更新 `.ai/CONTEXT.md`（当前焦点 / 妥协项）；里程碑完成才动 `.ai/PROGRESS.md`

`--frozen` 模式跑：当 `frontend/src-tauri && npm run tauri:dev` 在跑时 `.venv` 被锁，`uv` 默认会重装包失败；加 `--frozen` 跳过重装。

---

## 文档与 AI 上下文

| 文件 | 维护者 | 时效 | 内容 |
|---|---|---|---|
| `CLAUDE.md`（本文件） | 用户 | 长效，缓慢演化 | 规则、架构、禁令、技术栈 |
| `.ai/PROGRESS.md` | AI | 中长期 | 里程碑（T1-T7）、已交付 commit、关键架构决策 |
| `.ai/CONTEXT.md` | AI | 短期（每会话更新） | 当前焦点、用户偏好、UX 待补、RPC 清单 |
| `docs/dev_guide/*.md` | 用户 | 长效 | 开发环境配置、项目通用原则（人读） |
| `docs/civil_kb/*.md` | 用户 | 长效 | 土木知识库：规范条文、检测 SOP、公式 |

`.ai/` 隐藏目录约定 = 给 AI 读的工作上下文，思路同 `.github/`、`.vscode/`、`.cursor/`。

---

## 目录结构（双语言）

| 目录 | 角色 | 规则 |
|---|---|---|
| `src/civ_core/domain/` | 数据契约（dataclass） | 纯 Python，零外部依赖 |
| `src/civ_core/core/` | 业务逻辑 | 禁直接 IO；入参出参全 dataclass |
| `src/civ_core/infra_io/` | 文件读写 / COM / 预设 / SQLite | 唯一 IO 边界 |
| `src/civ_core/api/` | JSON-RPC server（stdin/stdout，Tauri sidecar） | `server.py` + `handlers/{workspace,files,plot_curves,leeb,pdf_tools,word2pdf}.py` |
| `src/civ_core/configs/` | 配置加载 | `loader.py` `lru_cache` 单例 |
| `src/civ_core/utils/` | 日志 / 异常 / COM 入口 | 无业务逻辑 |
| `src/civ_core/main.py` | CLI 入口 | GUI 分支已弃；no-args 输出迁移提示 |
| `frontend/src/components/` | 公共布局组件 | TitleBar / ActivityBar / SideBar / EditorArea / BottomPanel / RightPanel / StatusBar / AgentPanel |
| `frontend/src/tools/_shared/` | 跨工具共用 form 控件 | `forms.tsx` Field / Picker / ResetBtn / RunBtn |
| `frontend/src/tools/<tool>/` | 单工具子目录 | 全部 4 个工具（plot_curves / data_processing / pdf_tools / word2pdf）统一用 controller/Page/SettingsForm/index 范式 |
| `frontend/src-tauri/` | Tauri 2 主进程（Rust） | spawn Python/C# sidecar，`rpc_call` 按前缀转发 |
| `dotnet/civ-doc/` *(T5.5 新建)* | .NET 9 + OpenXML SDK | C# sidecar：`doc.*` / `xlsx_complex.*` 方法 |
| `presets/` | 系统预设（只读） | 程序运行时禁写 |
| `~/.civ-core/` | 用户家目录 | `presets/` 用户预设、`workspace.json` 上次工作区、`standards.db` 规范库、`logs/` |
| `templates/` | docx/xlsx 空白模板（docxtpl 填充） | 不是预设 |
| `docs/civil_kb/` | 土木知识库（Markdown） | 公式 + 规范 + SOP |

依赖方向：`frontend → Tauri rpc_call → {Python api/server.py | C# civ-doc} → core/infra_io/domain`。禁反向 import。

**RPC 方法前缀路由**（Tauri 端按前缀选 sidecar）：

| 前缀 | sidecar | 例子 |
|---|---|---|
| `workspace.*` / `files.*` | Python | `workspace.last`、`files.list_dir` |
| `plot_curves.*` / `leeb.*` / `pdf_tools.*` / `word2pdf.*` | Python | 业务计算与出图 |
| `doc.*` *(T5.5)* | C# | `doc.fill_template`（Word 模板填充走 OpenXML，不靠 COM） |
| `xlsx_complex.*` *(T5.5 后期)* | C# | **leeb 等 Excel 读取也会迁此**：合并单元格 / 复杂格式 openpyxl 解析弱，OpenXML SDK 原生 |

**handler 强约束**：每个 `api/handlers/*.py` 必须在文件顶部写 `__all__` 显式列出要暴露的 RPC 方法。`register_module` 优先读 `__all__`；不写会把顶部 `import Path` 等工具类误暴露成 RPC 方法（API 边界泄漏）。

---

## 前端布局规范（VSCode 风）

```
TitleBar (30px)
[ActivityBar(48) | SideBar(全高) | (Editor + 底部输出 Panel) | RightPanel(全高)]
StatusBar (22px)
```

- **SideBar 全高**：资源管理器；不被底部 Panel 截断
- **底部 Panel**：专用「输出/日志」Tab；Ctrl+J / StatusBar「面板」按钮 toggle
- **RightPanel 全高**：tab 化 —— `当前工具调参 + AI 助手（占位）`；Ctrl+Alt+B / StatusBar「调参」按钮 toggle
- **工具页交互范式**：中间上部预览区 + 右侧参数区（RightPanel）。4 个工具页全部对齐：
  - `plot_curves`：实时 PNG 预览（render_preview）
  - `data_processing`：Excel 前 50 行表格预览（leeb.preview_excel）
  - `pdf_tools`：每个 PDF 的页数 + 大小列表（pdf_tools.inspect）
  - `word2pdf`：每个 docx 的段落数 + 大小列表（word2pdf.inspect）
- **图标必须用 @vscode/codicons 真实存在的名字**：找不到的会渲染透明。常用确认存在的：`symbol-method`、`symbol-numeric`、`graph-line`、`file-pdf`、`file-binary`、`table`、`folder-opened`、`add`、`close`、`pass`、`error`、`warning`、`loading`、`chevron-up/down`、`hubot`、`settings-gear`、`discard`、`edit`、`new-file`、`copy`、`trash`、`eye`、`eye-closed`、`clear-all`。**不存在**：`calculator`（用 `symbol-method` 代替）

---

## 关键入口

| 模块 | 职责 |
|---|---|
| `api/server.py` | `Dispatcher` JSON-RPC 路由 + `serve()` stdin/stdout 行循环；`register_module` 强制读 `__all__` |
| `api/__main__.py` | `python -m civ_core.api` 入口；自己挂"文件 + stderr" logger（绝不污染 stdout 协议流） |
| `api/handlers/workspace.py` | `workspace.{last,set,clear,create_standard}` |
| `api/handlers/files.py` | `files.{list_dir,exists}`；默认隐藏 `.civ-core` 和点开头 |
| `api/handlers/plot_curves.py` | `plot_curves.{list_presets,list_sheets,run,preflight,render_preview,save_preset,delete_preset,rename_preset,copy_preset}` |
| `api/handlers/leeb.py` | `leeb.{run,preview_excel}` —— preview_excel 给 data_processing 中间预览用 |
| `api/handlers/pdf_tools.py` | `pdf_tools.{merge,split_per_page,split_by_ranges,inspect}` —— inspect 给中间预览拉每个 PDF 页数 |
| `api/handlers/word2pdf.py` | `word2pdf.{convert,inspect}` —— inspect 读 docx 段落数 + size + Word 缓存 Pages |
| `frontend/src-tauri/src/lib.rs` / `sidecar.rs` | Tauri 启动 + Python sidecar Mutex 串行 RPC |
| `frontend/src/App.tsx` | 顶层 layout + 快捷键（Ctrl+B / Ctrl+J / Ctrl+Alt+B）+ 嵌套 Providers（plot_curves / data_processing / pdf_tools / word2pdf）|
| `frontend/src/lib/rpc.ts` | `invoke('rpc_call', ...)` 包装 |
| `frontend/src/tools/plot_curves/` | controller/Page/SettingsForm + tabs/ 子目录范式（form 复杂 tabs 拆） |
| `frontend/src/tools/data_processing/` | calcType 下拉切计算类型（当前只 leeb，留接口）+ controller/Page/SettingsForm |
| `frontend/src/tools/pdf_tools/` | mode 切换（merge / split_per_page / split_by_ranges）共享 state |
| `frontend/src/tools/word2pdf/` | 简版三件套（最少参数：仅输出目录）|
| `frontend/src/tools/_shared/forms.tsx` | Field / Picker / ResetBtn / RunBtn 跨工具共用 |
| `core/plot_curves.py` | Excel → PlotJob → 批量出 PNG（`render_plot_to_bytes` 内存版供预览） |
| `core/calc_functions.py` | INSP-001/002/003 计算（里氏 / 钻芯 / 回弹） |
| `infra_io/standards_db.py` | SQLite 通用查表层 |
| `infra_io/preset_manager.py` | 系统/用户预设双路径 + CRUD（save/delete/rename/copy_user_preset） |
| `infra_io/workspace_scaffold.py` | 标准项目骨架生成 |

---

## 已锁定技术决策

| 维度 | 决策 |
|---|---|
| Python | 3.12+，`uv` 管理（禁 pip install） |
| C#（T5.5+） | .NET 9 + OpenXML SDK / ClosedXML；`dotnet` CLI；目标场景 Word/Excel 重资产 |
| 前端 | Vite + React 19 + TS + Tailwind v4 + @vscode/codicons + react-resizable-panels |
| 主进程 | Tauri 2.11（Rust 1.95+） |
| 跨语言协议 | JSON-RPC 2.0 over stdin/stdout，行协议（Python/C# 两个 sidecar 同协议） |
| 渐进迁移 | 一次只迁一个方法；Python 已交付的不迁；新功能按场景选最合适 sidecar |
| Excel 主路径（Python 侧） | openpyxl-only（`excel_reader.py`），禁主流程 pandas |
| Excel 辅助 | pandas 延迟 import；复杂格式（透视/条件格式/公式重算）走 C# OpenXML |
| Word（Python 侧） | docxtpl + python-docx；COM 仅域刷新/目录/转 PDF/精修，集中在 `utils/word_com.py` |
| Word（C# 侧 T5.5+） | OpenXML SDK 原生；不依赖 Word 安装；域代码/目录/复杂表格首选 |
| 图片 | PNG 字节（`chart_writer.render_plot_to_bytes`）+ base64 给前端预览；落盘还是 PNG |
| 配置 | `config.toml`（`tomllib` 读 / `tomli-w` 写） |
| 数据契约 | `@dataclass` + `__post_init__`，禁 pydantic |
| 日志 | stdlib `logging`，`ZoneInfo("Asia/Shanghai")` |
| 路径 | `pathlib.Path` |
| 编码 | `encoding='utf-8'`，失败转 GBK |
| 类型检查 | Pylance Basic 零红线 + ruff |

---

## 工具链

```bash
# 一键启动（开发模式：Tauri + Vite + Python sidecar）
bash run.sh
# 等价
cd frontend && npm run tauri:dev

# Python 后端
uv add <package>                              # 装依赖（禁 pip install）
uv run --frozen python -m civ_core.api        # 启 RPC server（Tauri 自动调，也可手测）
uv run --frozen python -m civ_core.main --list-presets
uv run --frozen python -m civ_core.main --tool plot_curves --input <xlsx> --preset <名> --output <dir>
uv run --frozen ruff check .                  # lint
uv run --frozen pytest                        # 测试
uv run --frozen python scripts/healthcheck.py # 6 项冒烟（每次验收必跑）

# 前端 / Tauri 构建
cd frontend && npm run build                  # 仅前端 build
cd frontend/src-tauri && cargo check          # 仅 Rust 检查
cd frontend && npm run tauri:build            # 安装包（T6 PyInstaller + dotnet publish 配好才完整）

# C# sidecar（T5.5 起；当前还没建项目）
# cd dotnet/civ-doc && dotnet run            # dev 跑 sidecar
# cd dotnet/civ-doc && dotnet test           # 测试
# cd dotnet/civ-doc && dotnet publish -c Release --self-contained -r win-x64
```

### 中国镜像（必走，国外直连超时）

| 工具链 | 位置 | 镜像 |
|---|---|---|
| Cargo | `frontend/src-tauri/.cargo/config.toml`（项目级已配） | 字节 `sparse+https://rsproxy.cn/index/` |
| rustup | shell env | `RUSTUP_DIST_SERVER=https://rsproxy.cn` + `RUSTUP_UPDATE_ROOT=https://rsproxy.cn/rustup` |
| npm | 暂未配；需要时项目级 `.npmrc` 加 `registry=https://registry.npmmirror.com` | 淘宝 |
| pip / uv | 暂未配；需要时 `UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/` | 阿里 |

---

## 禁止 / 必须

| 禁止 | 必须 |
|---|---|
| 无通知就开始改代码 | 提方案 → 不确定问 → 等验收 → 通过再继续 |
| 无注释、全英文 | 中文注释，说"为什么这么做" |
| 自行决定规范与代码冲突 | 向用户说明 |
| 凭直觉优化 | 先 profile |
| 异常只报错 | 异常 + 上下文（三段式） |
| `core/` 直接读写文件、`api/handlers/` 直接做计算 | 分层：UI(前端) → api/handlers → core → infra_io → domain |
| `presets/` 运行时写入 | 只读；用户预设走 `~/.civ-core/` |
| docxtpl 能干的活用 COM | 模板填充用 docxtpl；COM 仅域代码/目录/转 PDF/精修 |
| 主流程用 pandas 读 Excel | openpyxl-only；pandas 延迟 import 只用于辅助 |
| 引 pydantic / requests | dataclass + `__post_init__`；HTTP 另议 |
| 大文件 `f.read()` 一把梭 | generator / 流式 |
| 在 api server 里 print 到 stdout | stdout 是协议流；日志走 stderr 或文件（C# 端 Console.Out 同样禁用，用 Console.Error 或 file logger） |
| 在 Python 已稳的功能上重写 C# | 渐进迁移：Python 已交付 + 有测试的功能不动；只在新功能 / 真正痛点时切 C# |
| 跨 sidecar 共享状态（如全局变量） | 各 sidecar 进程独立；共享状态走 `~/.civ-core/` 下文件（如 workspace.json / standards.db） |
| handler 不写 `__all__` | 每个 `api/handlers/*.py` 顶部显式列白名单，防 RPC 边界泄漏 |
| UI 用 emoji 表情符号 | 用 codicons 或纯文字标签（系统/我的 等）；commit message 和 AI 维护的文档同此规则 |
| 工具页参数堆在主区 | 工具参数放 RightPanel；中间上部是预览区。新工具按这个范式 |

```python
# 禁                            必
base_dir + "/output/" + f    →  base_dir / "output" / f
except: pass                 →  except Err as e: logger.error(...); raise
threshold = 0.85             →  config["evaluation"]["threshold"]
subprocess.run(f"python {s}")→  subprocess.run(["python", str(s)])
def fn(data: dict)           →  def fn(job: PlotJob)
import pandas as pd  # 顶层  →  函数内 lazy import + try/except ImportError
```
