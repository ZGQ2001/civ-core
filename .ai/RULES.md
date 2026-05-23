# 编码规范与参考清单

> **角色**：AI 编码时的详细参考。当需要查 RPC 方法清单、目录结构、测试命令、Git 工作流、已知技术债时加载。
> **维护**：AI 每次改架构/RPC/技术栈后更新。用户不改。
> **配套**：`CLAUDE.md`（宪法）| `PROGRESS.md`（里程碑）| `CONTEXT.md`（当前焦点）

---

## 目录结构

| 目录 | 角色 | 语言 |
|------|------|------|
| `src/civ_core/domain/` | 数据契约 dataclass，零外部依赖 | Python |
| `src/civ_core/core/` | 业务逻辑，禁 IO，入参出参全 dataclass | Python |
| `src/civ_core/infra_io/` | 文件读写/COM/SQLite，唯一 IO 边界 | Python |
| `src/civ_core/api/` | JSON-RPC server，`server.py` + `handlers/` | Python |
| `src/civ_core/configs/` | 配置加载，`lru_cache` 单例 | Python |
| `src/civ_core/utils/` | 日志/异常/工具函数，无业务逻辑 | Python |
| `dotnet/civ-doc/` | C# sidecar：JSON-RPC server + Calc/Handlers/StandardsDb/ReportTables | C# |
| `dotnet/civ-doc.Tests/` | xUnit 测试项目 | C# |
| `frontend/src/` | React 前端，`components/` + `tools/` + `lib/` | TS/TSX |
| `frontend/src-tauri/` | Tauri 主进程，`sidecar.rs` + `lib.rs` | Rust |
| `presets/` | 系统预设，运行时只读 | — |
| `~/.civ-core/` | 用户家目录：`presets/` `workspace.json` `standards.db` `logs/` | — |
| `templates/` | docx/xlsx 空白模板 | — |
| `docs/civil_kb/` | 土木知识库（规范条文/SOP/公式） | Markdown |

## RPC 方法全表

### Python sidecar（白名单路由）

| 方法 | 文件 | 用途 |
|------|------|------|
| `ping` | `__main__.py` | 桥联自测 |
| `version` | `__main__.py` | 版本信息 |
| `workspace.last` | `handlers/workspace.py` | 读取上次工作区 |
| `workspace.set` | `handlers/workspace.py` | 设置当前工作区 |
| `workspace.clear` | `handlers/workspace.py` | 清除工作区 |
| `workspace.create_standard` | `handlers/workspace.py` | 新建标准骨架 |
| `files.list_dir` | `handlers/files.py` | 列目录（隐藏 .开头 + .civ-core） |
| `files.exists` | `handlers/files.py` | 文件存在检查 |
| `plot_curves.list_presets` | `handlers/plot_curves.py` | 预设列表（含系统/用户来源） |
| `plot_curves.list_sheets` | `handlers/plot_curves.py` | Excel sheet 列表 |
| `plot_curves.render_preview` | `handlers/plot_curves.py` | 实时 PNG base64 预览 |
| `plot_curves.run` | `handlers/plot_curves.py` | 批量出图 |
| `plot_curves.preflight` | `handlers/plot_curves.py` | 跑前预检列名匹配 |
| `plot_curves.save_preset` | `handlers/plot_curves.py` | 保存预设 |
| `plot_curves.delete_preset` | `handlers/plot_curves.py` | 删除预设 |
| `plot_curves.rename_preset` | `handlers/plot_curves.py` | 重命名预设 |
| `plot_curves.copy_preset` | `handlers/plot_curves.py` | 复制预设 |
| `pdf_tools.merge` | `handlers/pdf_tools.py` | PDF 合并 |
| `pdf_tools.split_per_page` | `handlers/pdf_tools.py` | 按页拆分 |
| `pdf_tools.split_by_ranges` | `handlers/pdf_tools.py` | 按范围拆分 |
| `pdf_tools.inspect` | `handlers/pdf_tools.py` | 预览（页数+大小） |
| `word2pdf.convert` | `handlers/word2pdf.py` | Word→PDF 批量 |
| `word2pdf.inspect` | `handlers/word2pdf.py` | 预览（段落数+页数+大小） |

### C# sidecar（默认路由）

| 方法 | 文件 | 用途 |
|------|------|------|
| `leeb.run` | `Handlers/LeebHandlers.cs` | 里氏硬度全流程（读+算+返 report_table_data） |
| `leeb.preview_excel` | `Handlers/LeebHandlers.cs` | Excel 前 N 行预览 |
| `doc.ping` | `Handlers/DocHandlers.cs` | C# 链路验证 |
| `doc.version` | `Handlers/DocHandlers.cs` | C# 版本信息 |
| `xlsx.write_leeb_report_table` | `Handlers/XlsxHandlers.cs` | 写里氏报告插入表 |

### 未实现（预留）

| 方法 | 计划 |
|------|------|
| `doc.compose_report` | T5.5 Step 3：Word 变量替换 + xlsx 嵌入 + 图片嵌入 |
| `calc.core_drilling.*` | 钻芯法切 C# |
| `calc.rebound.*` | 回弹法切 C# |

## C# 项目结构

```
dotnet/civ-doc/
├── Program.cs                  入口：UTF-8 stdin/stdout → JsonRpcServer.RunAsync()
├── civ-doc.csproj              net9.0, ClosedXML 0.105, Microsoft.Data.Sqlite 10.0
├── NuGet.config                华为云镜像 + nuget.org fallback
├── Server/JsonRpcServer.cs     Dispatcher + 行循环（与 Python server.py 同协议）
├── Handlers/
│   ├── DocHandlers.cs          doc.ping / doc.version
│   ├── XlsxHandlers.cs         xlsx.write_leeb_report_table
│   └── LeebHandlers.cs         leeb.run / leeb.preview_excel
├── Calc/Leeb/
│   ├── LeebDomain.cs           数据契约 records（对应旧 Python LeebHardness* dataclass）
│   ├── LeebMath.cs             查表/插值/截尾平均（与 Python 等价）
│   ├── LeebExcelReader.cs      ClosedXML 读 leeb 输入（合并单元格+每构件3行）
│   └── LeebCalculator.cs       INSP-001 钢材里氏计算（steel/batch/workbook）
├── StandardsDb/StandardsDb.cs  只读 SQLite（Python sidecar 启动时 seed）
└── ReportTables/LeebReportTable.cs  14 列报告插入表（ClosedXML）
```

## 前端工具页规范

4 个工具页统一范式：

```
tools/<tool>/
├── index.ts           导出 { Provider, Page, SettingsForm }
├── types.ts           类型定义
├── controller.tsx     状态管理（useContext + Provider）
├── Page.tsx           主界面（中间预览 + 调用 controller）
└── SettingsForm.tsx   右侧参数区
```

### RPC 调用模板

```tsx
// ✅ 正确：run() 返回结果
const handleRun = useCallback(async () => {
    const res = await c.run();  // Promise<RunRes | null>
    if (res) {
        appendOutput?.(`完成：${res.summary}`);
    }
}, [c, appendOutput]);

// ❌ 错误：run() 不返回值，靠闭包读 c.result
const handleRun = useCallback(async () => {
    await c.run();
    if (c.result) { ... }  // 陈旧闭包！c.result 永远是 null
}, [c, appendOutput]);
```

**当前状态**：`data_processing` 已正确实现，`plot_curves`/`pdf_tools`/`word2pdf` 待修。

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

# 每步完成：独立提交（不用 emoji）
git add -A && git commit -m "feat: xxx"
```

阶段结束→更新 `.ai/CONTEXT.md`；里程碑完成→更新 `.ai/PROGRESS.md`。

## 中国镜像

| 工具 | 配置位置 | 镜像 |
|------|---------|------|
| Cargo | `frontend/src-tauri/.cargo/config.toml` | 字节 `rsproxy.cn` |
| rustup | shell env | `RUSTUP_DIST_SERVER=https://rsproxy.cn` |
| NuGet | `dotnet/civ-doc/NuGet.config` | 华为云 + nuget.org fallback |
| npm | 暂未配 | 必要时 `registry.npmmirror.com` |
| pip/uv | 暂未配 | 必要时 `mirrors.aliyun.com/pypi/simple` |

## 已知技术债

| 问题 | 位置 | 严重度 |
|------|------|--------|
| Tauri sidecar 崩溃不自动重启 | `sidecar.rs` | 🔴 |
| `rpc.ts` 无校验的 `as T` 强转 | `frontend/src/lib/rpc.ts` | 🟠 |
| `IconBtn` 在两处重复定义 | `plot_curves/Page.tsx` + `pdf_tools/Page.tsx` | 🟡 |
| 空壳文件 `core/steel_hardness.py` | `src/civ_core/core/` | 🟡 |
| `design_fb_min` 死参数（Python 旧代码） | `core/calc_functions.py` | 🟡 |
| 常量在 `calc_schema.py` 和 `calc_functions.py` 各定义一份 | Python | 🟡 |
