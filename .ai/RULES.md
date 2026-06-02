# 编码规范与参考清单

> **角色**：AI 编码时的详细参考。当需要查 RPC 方法清单、目录结构、测试命令、Git 工作流、已知技术债时加载。
> **维护**：AI 每次改架构/RPC/技术栈后更新。用户不改。
> **配套**：`CLAUDE.md`（宪法）| `PROGRESS.md`（里程碑）| `CONTEXT.md`（当前焦点）

---

## 目录结构

| 目录                     | 角色                                                                 | 语言     |
| ------------------------ | -------------------------------------------------------------------- | -------- |
| `src/civ_core/domain/`   | 数据契约 dataclass，零外部依赖                                       | Python   |
| `src/civ_core/core/`     | 业务逻辑，禁 IO，入参出参全 dataclass                                | Python   |
| `src/civ_core/infra_io/` | 文件读写/COM/SQLite，唯一 IO 边界                                    | Python   |
| `src/civ_core/api/`      | JSON-RPC server，`server.py` + `handlers/`                           | Python   |
| `src/civ_core/configs/`  | 配置加载，`lru_cache` 单例                                           | Python   |
| `src/civ_core/utils/`    | 日志/异常/工具函数，无业务逻辑                                       | Python   |
| `dotnet/civ-doc/`        | C# sidecar：JSON-RPC server + Calc/Handlers/StandardsDb/ReportTables | C#       |
| `dotnet/civ-doc.Tests/`  | xUnit 测试项目                                                       | C#       |
| `frontend/src/`          | React 前端，`components/` + `tools/` + `lib/`                        | TS/TSX   |
| `frontend/src-tauri/`    | Tauri 主进程，`sidecar.rs` + `lib.rs`                                | Rust     |
| `mcp/`                   | MCP server：spawn sidecar + 包 RPC 成 MCP tools（agent 入口）        | TS/Node  |
| `presets/`               | 系统预设，运行时只读                                                 | —        |
| `~/.civ-core/`           | 用户家目录：`presets/` `workspace.json` `standards.db` `logs/`       | —        |
| `templates/`             | docx/xlsx 空白模板                                                   | —        |
| `docs/civil_kb/`         | 土木知识库（规范条文/SOP/公式）                                      | Markdown |

## RPC 方法全表

### Python sidecar（白名单路由）

| 方法                         | 文件                      | 用途                        |
| ---------------------------- | ------------------------- | --------------------------- |
| `ping`                       | `__main__.py`             | 桥联自测                    |
| `version`                    | `__main__.py`             | 版本信息                    |
| `plot_curves.list_presets`   | `handlers/plot_curves.py` | 预设列表（含系统/用户来源） |
| `plot_curves.list_sheets`    | `handlers/plot_curves.py` | Excel sheet 列表            |
| `plot_curves.list_headers`   | `handlers/plot_curves.py` | Excel 表头行列名            |
| `plot_curves.render_preview` | `handlers/plot_curves.py` | 实时 PNG base64 预览        |
| `plot_curves.run`            | `handlers/plot_curves.py` | 批量出图                    |
| `plot_curves.preflight`      | `handlers/plot_curves.py` | 跑前预检列名匹配            |
| `plot_curves.save_preset`    | `handlers/plot_curves.py` | 保存预设                    |
| `plot_curves.delete_preset`  | `handlers/plot_curves.py` | 删除预设                    |
| `plot_curves.rename_preset`  | `handlers/plot_curves.py` | 重命名预设                  |
| `plot_curves.copy_preset`    | `handlers/plot_curves.py` | 复制预设                    |

### C# sidecar（默认路由）

| 方法                           | 文件                               | 用途                                                                                                                                 |
| ------------------------------ | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `leeb.run`                     | `Handlers/LeebHandlers.cs`         | 里氏硬度全流程（读+算+返 report_table_data）                                                                                         |
| `leeb.preview_excel`           | `Handlers/LeebHandlers.cs`         | Excel 前 N 行预览                                                                                                                    |
| `anchor.run`                   | `Handlers/AnchorHandlers.cs`       | 锚杆抗拔全流程：读 Excel + 按批次套参数 + 算 + 写 Excel；可选 word_template_path → 出 docx（支持 curve_image_dir 嵌曲线图）          |
| `anchor.list_batches`          | `Handlers/AnchorHandlers.cs`       | 读输入 Excel 返回所有 batch_id（前端按批次填参数前用）                                                                               |
| `anchor.generate_template`     | `Handlers/AnchorHandlers.cs`       | 生成锚杆输入 Excel 空白模板                                                                                                          |
| `template.fields`              | `Handlers/TemplateHandlers.cs`     | 按 catalog_id（兼容旧 project_type）返回字段 catalog（{key, name, group, level, source, value_type, default_format, aliases}）       |
| `template.validate`            | `Handlers/TemplateHandlers.cs`     | docx 模板占位符校验：匹配 / 未识别 / 未用字段 / marker 嵌套 + 字段层级 hint                                                          |
| `catalog.list`                 | `Handlers/CatalogHandlers.cs`      | 列所有字段目录（id, name, project_type, fields 个数）                                                                                |
| `catalog.get`                  | `Handlers/CatalogHandlers.cs`      | 读单个字段目录的完整字段定义                                                                                                         |
| `catalog.save`                 | `Handlers/CatalogHandlers.cs`      | 新建或覆盖字段目录                                                                                                                   |
| `catalog.delete`               | `Handlers/CatalogHandlers.cs`      | 删除字段目录                                                                                                                         |
| `report.render_placeholder`    | `Handlers/ReportHandlers.cs`       | 通用占位符渲染（docx_path + values + output_path），跟特定 calc 解耦                                                                 |
| `report.run_from_result`       | `Handlers/ReportHandlers.cs`       | 读 anchor.run 已产出的结果 xlsx 直接出 Word，不重算（隐藏 `_批次参数` sheet 读 P/Lf/La/A/E + 灌浆日期；日期 GUI/预设优先、文件兜底） |
| `report_preset.list`           | `Handlers/ReportPresetHandlers.cs` | 列报告 user_inputs 预设（可按 catalog_id 过滤）；按 updated_at 倒序                                                                  |
| `report_preset.get`            | `Handlers/ReportPresetHandlers.cs` | 读单个预设完整内容                                                                                                                   |
| `report_preset.save`           | `Handlers/ReportPresetHandlers.cs` | 新建或覆盖预设；server 端自动盖 updated_at                                                                                           |
| `report_preset.delete`         | `Handlers/ReportPresetHandlers.cs` | 删预设                                                                                                                               |
| `report_preset.rename`         | `Handlers/ReportPresetHandlers.cs` | 改预设 label（不动 id / user_inputs）                                                                                                |
| `doc.ping`                     | `Handlers/DocHandlers.cs`          | C# 链路验证                                                                                                                          |
| `doc.version`                  | `Handlers/DocHandlers.cs`          | C# 版本信息                                                                                                                          |
| `xlsx.write_leeb_report_table` | `Handlers/XlsxHandlers.cs`         | 写里氏报告插入表                                                                                                                     |
| `workspace.last`               | `Handlers/WorkspaceHandlers.cs`    | 读取上次工作区路径                                                                                                                   |
| `workspace.set`                | `Handlers/WorkspaceHandlers.cs`    | 设置当前工作区路径                                                                                                                   |
| `workspace.clear`              | `Handlers/WorkspaceHandlers.cs`    | 清除工作区记忆                                                                                                                       |
| `workspace.create_standard`    | `Handlers/WorkspaceHandlers.cs`    | 新建标准项目骨架（4 业务子目录 + .civ-core/）                                                                                        |
| `files.list_dir`               | `Handlers/FilesHandlers.cs`        | 列目录（隐藏 .开头 + .civ-core；目录排前 + 自然排序）                                                                                |
| `files.exists`                 | `Handlers/FilesHandlers.cs`        | 文件存在检查                                                                                                                         |
| `files.create_file`            | `Handlers/FilesHandlers.cs`        | 创建空文件（Windows 名校验）                                                                                                         |
| `files.create_folder`          | `Handlers/FilesHandlers.cs`        | 创建文件夹                                                                                                                           |
| `files.rename`                 | `Handlers/FilesHandlers.cs`        | 同目录改名                                                                                                                           |
| `files.delete`                 | `Handlers/FilesHandlers.cs`        | 发送到回收站（仅 Windows）                                                                                                           |
| `files.undo_delete`            | `Handlers/FilesHandlers.cs`        | 从回收站还原（5 分钟内，Shell COM）                                                                                                  |
| `files.copy`                   | `Handlers/FilesHandlers.cs`        | 复制（同名追加 (2)/(3)；目录递归）                                                                                                   |
| `files.move`                   | `Handlers/FilesHandlers.cs`        | 移动（同名追加 (2)/(3)）                                                                                                             |
| `files.reveal`                 | `Handlers/FilesHandlers.cs`        | explorer /select 定位选中                                                                                                            |
| `pdf_tools.merge`              | `Handlers/PdfToolsHandlers.cs`     | PDF 合并（PDFsharp，原子写）                                                                                                         |
| `pdf_tools.split_per_page`     | `Handlers/PdfToolsHandlers.cs`     | 按页拆分（{stem}\_p{n}.pdf 零填充）                                                                                                  |
| `pdf_tools.split_by_ranges`    | `Handlers/PdfToolsHandlers.cs`     | 按范围拆分（"1-3,5,7-9" 表达式）                                                                                                     |
| `pdf_tools.inspect`            | `Handlers/PdfToolsHandlers.cs`     | 预览（页数 + 大小；单文件失败不影响整体）                                                                                            |
| `word2pdf.convert`             | `Handlers/Word2PdfHandlers.cs`     | Word→PDF 批量（仅 Windows，COM dynamic；非 Windows 抛 PlatformNotSupported）                                                         |
| `word2pdf.inspect`             | `Handlers/Word2PdfHandlers.cs`     | 预览（段落数+页数+大小；OpenXML SDK，跨平台）                                                                                        |

### MCP server tools（agent 入口）

52 个 tool，命名规则：RPC 方法 `anchor.run` → MCP tool 名 `anchor_run`（点改下划线）。
基本与 sidecar RPC 全表对齐（除未实现的 calc 类型 stub）。完整列表见 `mcp/src/tools/`
各文件 + `allXxxTools` 数组。

| 域            | tool 数 | 文件                            | 备注                                                                                                      |
| ------------- | ------- | ------------------------------- | --------------------------------------------------------------------------------------------------------- |
| doc           | 2       | `mcp/src/tools/doc.ts`          | 探活 `doc_ping` / `doc_version`                                                                           |
| workspace     | 4       | `mcp/src/tools/workspace.ts`    | last / set / clear / create_standard                                                                      |
| anchor        | 4       | `mcp/src/tools/anchor.ts`       | generate_template / list_batches / read_batch_info / run（含 Word）                                       |
| leeb          | 2       | `mcp/src/tools/leeb.ts`         | run / preview_excel                                                                                       |
| xlsx          | 1       | `mcp/src/tools/xlsx.ts`         | write_leeb_report_table                                                                                   |
| template      | 2       | `mcp/src/tools/template.ts`     | fields / validate                                                                                         |
| report        | 2       | `mcp/src/tools/report.ts`       | render_placeholder / run_from_result                                                                      |
| report_preset | 5       | `mcp/src/tools/reportPreset.ts` | list / get / save / delete / rename                                                                       |
| catalog       | 4       | `mcp/src/tools/catalog.ts`      | list / get / save / delete                                                                                |
| files         | 10      | `mcp/src/tools/files.ts`        | list_dir/exists/create_file/create_folder/rename/copy/move/delete/undo_delete/reveal                      |
| pdf_tools     | 4       | `mcp/src/tools/pdfTools.ts`     | merge / split_per_page / split_by_ranges / inspect                                                        |
| word2pdf      | 2       | `mcp/src/tools/word2pdf.ts`     | convert（仅 Win）/ inspect                                                                                |
| plot_curves   | 10      | `mcp/src/tools/plot_curves.ts`  | list_presets/list_sheets/list_headers/preflight/run/render_preview + 预设 CRUD（save/delete/rename/copy） |

**已全部包完**（Phase 1 + Phase 2）。仅剩待评估项：`leeb.preview_excel` 是否跟
`plot_curves.list_sheets` 合并成通用 `excel_preview`（暂未动，两者入参/返回不同）。
未来新检测类型（钻芯/回弹切 C#）的 calc RPC 落地后，在 `mcp/src/tools/` 补对应 ToolDef。

### 未实现（预留）

| 方法                          | 计划                                                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `calc.core_drilling.*`        | 钻芯法切 C#                                                                                                                   |
| `calc.rebound.*`              | 回弹法切 C#                                                                                                                   |
| `anchor.run` 多批 user_inputs | 当前 user_inputs 是项目级 dict；多批共享字段（灌浆日期等）按批不同时需扩展为 `user_inputs_by_batch` + 切回 GenerateMultiBatch |

## 子域文档（避免重复，按目录加载）

- C# 项目结构、handler 注册模式、record/UTF-8 等 C# 约定 → [`dotnet/CLAUDE.md`](../dotnet/CLAUDE.md)
- 前端工具页范式（Controller/Page/SettingsForm 模板、RPC 调用陈旧闭包反例）、布局/快捷键 → [`frontend/CLAUDE.md`](../frontend/CLAUDE.md)

### 可用 codicons

**判定标准**：名字在 `@vscode/codicons` 包里有对应 `.codicon-X` 字形就能用（v0.0.45 共 ~649 个）。下面只是常用清单，**非穷举**——不在表里 ≠ 不存在（`check` `info` `save` `folder` `run-all` `question` `go-to-file` `expand-all`/`collapse-all` 等都真实存在，别因为没列就当违规）。拿不准查 `frontend/node_modules/@vscode/codicons/dist/codicon.css`。

常用：`symbol-method` `symbol-numeric` `graph-line` `file-pdf` `file-binary` `table` `folder-opened` `add` `close` `pass` `error` `warning` `loading~spin` `chevron-up/down` `hubot` `settings-gear` `discard` `edit` `new-file` `copy` `trash` `eye` `eye-closed` `clear-all` `list-tree` `refresh` `search` `kebab-vertical` `chrome-maximize/minimize/close`

不存在示例：`calculator`（用 `symbol-method` 替代）

## 测试命令

```bash
# Python
uv run --frozen ruff format --check . && uv run --frozen ruff check . && uv run --frozen pytest -q
uv run --frozen python scripts/healthcheck.py   # 冒烟检查（每次验收必跑）

# C#
cd dotnet/civ-doc && dotnet format style --verify-no-changes && dotnet build && dotnet test

# Rust
cd frontend/src-tauri && cargo fmt --check && cargo clippy -- -D warnings && cargo check --lib && cargo test --lib

# 前端 TS
cd frontend && npx tsc -b --noEmit && npm run lint && npm run format:check

# MCP server（Node + TS）
cd mcp && npm run typecheck && npm test
# 冒烟（先 dotnet build；spawn 真 sidecar 端到端）：
cd mcp && npm run build && node scripts/smoke.mjs
```

## Git 工作流

```bash
# 会话开始：保存检查点
git add -A && git commit -m "chore: 会话检查点"

# 每步完成：先跑 CI 全链，通过后再提交
# 1. 跑涉及语言的全链检查（见下方「单元完成层的全链命令」）
# 2. 全部通过 → 提交
# 3. 有报错 → 修完 → 重跑 → 通过 → 再提交
git add -A && git commit -m "feat: xxx"
```

**CI 先行原则**：每次改完代码、准备 commit 之前，必须先跑对应语言的全链检查并确认通过。不通过不提交——把错误拦在本地，不带进 git 历史。具体步骤：

1. 改完代码
2. 跑该语言的全链命令（format + lint + build/test）
3. 如果有报错：`--write`/`--fix` 自动修 → 手动修剩余 → 重跑直到通过
4. 全部通过后 `git add && git commit`
5. 如果改了多种语言，每种都要跑

commit 信息写**为什么**，不写做了什么——diff 已经告诉读者改了啥，commit 要补充原因。
阶段结束→更新 `.ai/CONTEXT.md`；里程碑完成→更新 `.ai/PROGRESS.md`。

### 质检分层频次（不是"改一行跑一次"，也不是"攒到 push"）

反馈越快越省事，但跑全链有启动成本。两个极端都要避：

- **太稀疏**（攒到 push）：错误堆叠、定位翻倍、CI 必挂
- **太频繁**（字符级跑）：启动成本占大头、打断 flow、收益边际递减

正确做法是**分层**——不同检查在不同时机跑：

| 层级          | 跑什么                                   | 何时触发                                          | 成本        |
| ------------- | ---------------------------------------- | ------------------------------------------------- | ----------- |
| IDE 实时      | LSP 类型 / ESLint / Pyright 红波浪       | 敲字符时                                          | 0 摩擦      |
| 保存时        | `format on save`（Prettier/ruff format） | Ctrl+S                                            | <100ms      |
| **单元完成**  | **该语言全链**（见下表）                 | **写完一个函数/组件/effect/handler/修完一个 bug** | 数秒~数十秒 |
| **commit 前** | **所有涉及语言的全链**                   | **git add 之前，必须全链通过才允许 commit**       | 同上        |
| push          | 跨语言全跑                               | 推送前最终兜底                                    | 同上        |

**关键判断**——什么是「一个有意义的改动单元」：一个完整函数、一个 effect、一个 handler、一个 bug 修完、一个组件的 Provider 加完。**不是**每改一行、每加个注释、每改个变量名。

**单元完成层的全链命令**：

| 改完这种文件      | 跑                                                                                                   |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| 前端 `.ts/.tsx`   | `cd frontend && npx tsc -b --noEmit && npm run lint && npm run format:check`                         |
| MCP `mcp/**/*.ts` | `cd mcp && npm run typecheck && npm test`（端到端 smoke 视改动决定要不要跑）                         |
| Python `.py`      | `uv run --frozen ruff format --check . && uv run --frozen ruff check . && uv run --frozen pytest -q` |
| C# `.cs`          | `cd dotnet/civ-doc && dotnet format style --verify-no-changes && dotnet build && dotnet test`        |
| Rust `.rs`        | `cd frontend/src-tauri && cargo fmt --check && cargo clippy -- -D warnings && cargo check --lib`     |
| Markdown `.md`    | `cd frontend && npx prettier --check <相对路径>`（Prettier 也管 markdown 表格对齐）                  |

发现 format/lint 报错立刻用 `--write`/`--fix` 自动修。**别把 format/lint 留到 push 前——它们是 CI 一票否决项。**

## 编码规范

- **类型注解全开（新代码）**：Python `from __future__ import annotations` + mypy/pyright，TS 显式类型。不只是给 IDE 看，也是给 AI 看——AI 看到类型能给出准确得多的补全和重构。旧代码的 pyright 报错不主动迁移（项目锁定「维护 + 新功能」模式）。

## 省 token / 上下文卫生

token 烧在「每轮重发的固定底座（system prompt + 工具/MCP schema + skill 列表 + CLAUDE.md）+ 不断累积的历史和工具输出」，跟用户打多少字几乎无关。大模型无状态——每轮都把至今所有上下文重发一遍按 input token 计费，会话越长越贵。下面按收益从高到低。

### 用户侧（最大杠杆，AI 管不了，靠人操作）

| 动作                 | 为什么省                                                                 |
| -------------------- | ------------------------------------------------------------------------ |
| **一个任务一个会话** | 历史全量重发；跨域膨胀（锚杆→前端→MCP）会把前文一直拖着重发              |
| 做完任务 `/clear`    | 上下文打回基线，最有效                                                   |
| 长会话 `/compact`    | 把历史压成摘要再继续                                                     |
| 开工前 `/context`    | 看 token 都被谁占（system/tools/messages/MCP/memory），对症下药          |
| 只开当前任务要的 MCP | 每个 MCP server 的 tool schema 是固定开销；写码用不上 Gmail/Drive 就关   |
| routine 活降模型     | 改文案/加测试/跑格式用 Sonnet/Haiku，硬逻辑（判定/协议）才上 Opus        |
| 相关活集中一口气做   | prompt cache 有几分钟 TTL，连续做缓存命中按 ~1/10 计费；断断续续反复失效 |

### AI 侧（已写进 `CLAUDE.md` 行为准则 5，编码时遵守）

- **大范围搜索委派 Explore/子 agent**：扫一片找文件/用法/schema 时用子 agent，它在自己上下文里跑，只回结论，翻过的文件不进主上下文。monorepo 多语言尤其受益。
- **精确读取**：给 `file:line` 或函数名，用 Read 的 offset/limit、Grep 的 output_mode，别读整个大文件（Word 模板、生成报告、standards.db dump 都很大）。
- **别灌大输出**：测试/构建日志别整屏贴；失败时 grep 关键行或重定向到文件再看。
- **先方案后写码**：本项目「先报告方案→确认→执行」本就是省 token 项——小上下文对齐方案，比写错重来（要重读一堆文件）便宜得多。

## 中国镜像

| 工具   | 配置位置                                | 镜像                                    |
| ------ | --------------------------------------- | --------------------------------------- |
| Cargo  | `frontend/src-tauri/.cargo/config.toml` | 字节 `rsproxy.cn`                       |
| rustup | shell env                               | `RUSTUP_DIST_SERVER=https://rsproxy.cn` |
| NuGet  | `dotnet/civ-doc/NuGet.config`           | 华为云 + nuget.org fallback             |
| npm    | 暂未配                                  | 必要时 `registry.npmmirror.com`         |
| pip/uv | 暂未配                                  | 必要时 `mirrors.aliyun.com/pypi/simple` |

## 已知技术债

| 问题                                                      | 位置                                          | 严重度 |
| --------------------------------------------------------- | --------------------------------------------- | ------ |
| Tauri sidecar 崩溃不自动重启                              | `sidecar.rs`                                  | 🔴     |
| `rpc.ts` 无校验的 `as T` 强转                             | `frontend/src/lib/rpc.ts`                     | 🟠     |
| `IconBtn` 在两处重复定义                                  | `plot_curves/Page.tsx` + `pdf_tools/Page.tsx` | 🟡     |
| 空壳文件 `core/steel_hardness.py`                         | `src/civ_core/core/`                          | 🟡     |
| `design_fb_min` 死参数（Python 旧代码）                   | `core/calc_functions.py`                      | 🟡     |
| 常量在 `calc_schema.py` 和 `calc_functions.py` 各定义一份 | Python                                        | 🟡     |

## 架构级 backlog（需先出方案再动手）

> 2026-05-26 用户反馈汇总，🟢 复杂度，单独立项前**禁止**改代码。

### B1：报告填充去硬编码（支持自定义检测类型）

- **问题**：当前 `AnchorRowResolver` / `AnchorFieldCatalog` / `AnchorHandlers` 全部围绕锚杆。换检测类型（钻芯、回弹、回弹+碳化、拉拔…）就要复制一份全链，无法增删自定义字段。
- **影响范围**：`dotnet/civ-doc/Calc/Anchor/*` · `dotnet/civ-doc/Handlers/AnchorHandlers.cs` · `frontend/src/tools/report_generator/*` · 模板占位符约定
- **方案要点（待定）**：字段目录走插件式注册；resolver 走通用 dict-based 字段表；handler 用 `report.run(detection_type, ...)` 通用入口；前端"字段定义"可配置
- **方案文档**：`docs/plans/generic_report_filler.md`（待写）

### B2：模板占位符语法简化（非编程用户友好）

- **问题**：当前 `{{img:曲线图}}` / `{{锚杆序号}}` / `[[每根锚杆]]...[[/每根锚杆]]` 等占位符语法对内业人员太抽象，做不出模板。
- **方向（待评估）**：① 可视化模板编辑器（点 Word 单元格→挑字段）；② Word ContentControl/SDT 借力原生「内容控件」；③ 简化占位符为中文别名 + 快速文档
- **依赖**：B1 完成后再做，否则字段目录还在变
- **方案文档**：`docs/plans/template_authoring_ux.md`（待写）
