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
| `presets/`               | 系统预设，运行时只读                                                 | —        |
| `~/.civ-core/`           | 用户家目录：`presets/` `workspace.json` `standards.db` `logs/`       | —        |
| `templates/`             | docx/xlsx 空白模板                                                   | —        |
| `docs/civil_kb/`         | 土木知识库（规范条文/SOP/公式）                                      | Markdown |

## RPC 方法全表

### Python sidecar（白名单路由）

| 方法                         | 文件                      | 用途                             |
| ---------------------------- | ------------------------- | -------------------------------- |
| `ping`                       | `__main__.py`             | 桥联自测                         |
| `version`                    | `__main__.py`             | 版本信息                         |
| `workspace.last`             | `handlers/workspace.py`   | 读取上次工作区                   |
| `workspace.set`              | `handlers/workspace.py`   | 设置当前工作区                   |
| `workspace.clear`            | `handlers/workspace.py`   | 清除工作区                       |
| `workspace.create_standard`  | `handlers/workspace.py`   | 新建标准骨架                     |
| `files.list_dir`             | `handlers/files.py`       | 列目录（隐藏 .开头 + .civ-core） |
| `files.exists`               | `handlers/files.py`       | 文件存在检查                     |
| `plot_curves.list_presets`   | `handlers/plot_curves.py` | 预设列表（含系统/用户来源）      |
| `plot_curves.list_sheets`    | `handlers/plot_curves.py` | Excel sheet 列表                 |
| `plot_curves.render_preview` | `handlers/plot_curves.py` | 实时 PNG base64 预览             |
| `plot_curves.run`            | `handlers/plot_curves.py` | 批量出图                         |
| `plot_curves.preflight`      | `handlers/plot_curves.py` | 跑前预检列名匹配                 |
| `plot_curves.save_preset`    | `handlers/plot_curves.py` | 保存预设                         |
| `plot_curves.delete_preset`  | `handlers/plot_curves.py` | 删除预设                         |
| `plot_curves.rename_preset`  | `handlers/plot_curves.py` | 重命名预设                       |
| `plot_curves.copy_preset`    | `handlers/plot_curves.py` | 复制预设                         |
| `pdf_tools.merge`            | `handlers/pdf_tools.py`   | PDF 合并                         |
| `pdf_tools.split_per_page`   | `handlers/pdf_tools.py`   | 按页拆分                         |
| `pdf_tools.split_by_ranges`  | `handlers/pdf_tools.py`   | 按范围拆分                       |
| `pdf_tools.inspect`          | `handlers/pdf_tools.py`   | 预览（页数+大小）                |
| `word2pdf.convert`           | `handlers/word2pdf.py`    | Word→PDF 批量                    |
| `word2pdf.inspect`           | `handlers/word2pdf.py`    | 预览（段落数+页数+大小）         |

### C# sidecar（默认路由）

| 方法                           | 文件                            | 用途                                                                              |
| ------------------------------ | ------------------------------- | --------------------------------------------------------------------------------- |
| `leeb.run`                     | `Handlers/LeebHandlers.cs`      | 里氏硬度全流程（读+算+返 report_table_data）                                      |
| `leeb.preview_excel`           | `Handlers/LeebHandlers.cs`      | Excel 前 N 行预览                                                                 |
| `anchor.run`                   | `Handlers/AnchorHandlers.cs`    | 锚杆抗拔全流程：读 Excel + 按批次套参数 + 算 + 写 Excel；可选 word_template_path → 出 docx（支持 curve_image_dir 嵌曲线图） |
| `anchor.list_batches`          | `Handlers/AnchorHandlers.cs`    | 读输入 Excel 返回所有 batch_id（前端按批次填参数前用）                            |
| `anchor.generate_template`     | `Handlers/AnchorHandlers.cs`    | 生成锚杆输入 Excel 空白模板                                                       |
| `template.fields`              | `Handlers/TemplateHandlers.cs`  | 按 project_type 返回字段 catalog（{key, name, source, value_type, default_format}） |
| `report.render_placeholder`    | `Handlers/ReportHandlers.cs`    | 通用占位符渲染（docx_path + values + output_path），跟特定 calc 解耦              |
| `doc.ping`                     | `Handlers/DocHandlers.cs`       | C# 链路验证                                                                       |
| `doc.version`                  | `Handlers/DocHandlers.cs`       | C# 版本信息                                                                       |
| `xlsx.write_leeb_report_table` | `Handlers/XlsxHandlers.cs`      | 写里氏报告插入表                                                                  |

### 未实现（预留）

| 方法                   | 计划                                                                       |
| ---------------------- | -------------------------------------------------------------------------- |
| `calc.core_drilling.*` | 钻芯法切 C#                                                                |
| `calc.rebound.*`       | 回弹法切 C#                                                                |
| `anchor.run` 多批 user_inputs | 当前 user_inputs 是项目级 dict；多批共享字段（灌浆日期等）按批不同时需扩展为 `user_inputs_by_batch` + 切回 GenerateMultiBatch |

## 子域文档（避免重复，按目录加载）

- C# 项目结构、handler 注册模式、record/UTF-8 等 C# 约定 → [`dotnet/CLAUDE.md`](../dotnet/CLAUDE.md)
- 前端工具页范式（Controller/Page/SettingsForm 模板、RPC 调用陈旧闭包反例）、布局/快捷键 → [`frontend/CLAUDE.md`](../frontend/CLAUDE.md)

### 可用 codicons

存在：`symbol-method` `symbol-numeric` `graph-line` `file-pdf` `file-binary` `table` `folder-opened` `add` `close` `pass` `error` `warning` `loading~spin` `chevron-up/down` `hubot` `settings-gear` `discard` `edit` `new-file` `copy` `trash` `eye` `eye-closed` `clear-all` `list-tree` `refresh` `search` `kebab-vertical` `chrome-maximize/minimize/close`

不存在：`calculator`（用 `symbol-method` 替代）

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

| 层级             | 跑什么                                   | 何时触发                                          | 成本        |
| ---------------- | ---------------------------------------- | ------------------------------------------------- | ----------- |
| IDE 实时         | LSP 类型 / ESLint / Pyright 红波浪       | 敲字符时                                          | 0 摩擦      |
| 保存时           | `format on save`（Prettier/ruff format） | Ctrl+S                                            | <100ms      |
| **单元完成**     | **该语言全链**（见下表）                 | **写完一个函数/组件/effect/handler/修完一个 bug** | 数秒~数十秒 |
| **commit 前** | **所有涉及语言的全链** | **git add 之前，必须全链通过才允许 commit** | 同上 |
| push             | 跨语言全跑                               | 推送前最终兜底                                    | 同上        |

**关键判断**——什么是「一个有意义的改动单元」：一个完整函数、一个 effect、一个 handler、一个 bug 修完、一个组件的 Provider 加完。**不是**每改一行、每加个注释、每改个变量名。

**单元完成层的全链命令**：

| 改完这种文件    | 跑                                                                                                   |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| 前端 `.ts/.tsx` | `cd frontend && npx tsc -b --noEmit && npm run lint && npm run format:check`                         |
| Python `.py`    | `uv run --frozen ruff format --check . && uv run --frozen ruff check . && uv run --frozen pytest -q` |
| C# `.cs`        | `cd dotnet/civ-doc && dotnet format style --verify-no-changes && dotnet build && dotnet test`        |
| Rust `.rs`      | `cd frontend/src-tauri && cargo fmt --check && cargo clippy -- -D warnings && cargo check --lib`     |
| Markdown `.md`  | `cd frontend && npx prettier --check <相对路径>`（Prettier 也管 markdown 表格对齐）                  |

发现 format/lint 报错立刻用 `--write`/`--fix` 自动修。**别把 format/lint 留到 push 前——它们是 CI 一票否决项。**

## 编码规范

- **类型注解全开（新代码）**：Python `from __future__ import annotations` + mypy/pyright，TS 显式类型。不只是给 IDE 看，也是给 AI 看——AI 看到类型能给出准确得多的补全和重构。旧代码的 pyright 报错不主动迁移（项目锁定「维护 + 新功能」模式）。

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
