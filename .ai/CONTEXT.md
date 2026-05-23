# 工作上下文

> **角色**：当前焦点、UX 缺口、用户偏好。**每会话更新**，时效性强。
> **维护**：AI 每次会话结束时更新。里程碑级变动记 PROGRESS.md，这里不重复。
> **配套**：`CLAUDE.md`（宪法）| `RULES.md`（规范）| `PROGRESS.md`（里程碑）

---

## 当前焦点（2026-05-23）

**4 个工具全部接 ShellContext.activatedFile**：文件树双击对应扩展名自动灌入当前工具。下一步：报告生成工具页（T5.5 Step 3）。

- 锚杆全套：C# Calc/Anchor 7 文件（Domain/Math/Calculator/Standards/Columns/ExcelReader/TemplateWriter）+ 2 ReportTables + 3 RPC（anchor.run / list_batches / generate_template）+ 前端 calcType=anchor 子 form（规范下拉 + 生成模板按钮 + 按批次参数卡片）。C# 65 xUnit（64 通过 + 1 skip）；TS 0 错。
- 锚杆参数 UX 重做：每批一张可折叠卡片，每字段中文名 + 变量符号 + input + 单位 suffix + hint —— 字母不再裸露。
- ShellContext（`frontend/src/lib/shell.ts`）：全局壳能力（appendOutput / activeToolId / activatedFile）。Provider 内 useShell()，RightPanel 里的操作也能写底部日志面板。
- 文件树双击 .xlsx/.xls/.docx/.doc/.pdf 联动当前工具（目前只 data_processing 接 xlsx）。Shift+双击 = 强制系统打开（逃生口）。
- **capability bug**：`dialog:allow-save` 漏授权 → 所有 saveDialog() 静默被拒（"点了没反应"）。已加 `dialog:allow-save`。
- FileTree 由用户重构为 VSCode 风扁平渲染 + 右键菜单 + in-place 编辑 + 剪贴板 + 删除回收站 + 焦点自动 refetch（720+ 行）。

**Python 剩余职责**：workspace/files/plot_curves/pdf_tools/word2pdf + seeds standards.db

---

## 下一步候选（按价值排）

1. **报告生成工具页（T5.5 Step 3）** — 新 ActivityBar 项，doc.compose_report（变量替换 + xlsx 嵌入 + 图片嵌入）。模板填充归此阶段（不在计算阶段做）。
2. **钻芯/回弹切 C#** — data_processing calcType 下拉再加项
3. **T6 打包** — PyInstaller + dotnet publish + Tauri externalBin
4. **App.tsx 拆 useShellState hook** — 当前 270+ 行嵌套 4 个 Provider，重构降低复杂度

---

## 用户偏好

| 偏好 | 来源日期 |
|------|---------|
| 不要 JSON 编辑器——用 form | 2026-05-21 |
| 中间预览区 + 右侧参数区，统一交互范式 | 2026-05-21 |
| 全局禁 emoji（UI/commit/AI 文档） | 2026-05-21 |
| 大需求分多次 commit，每次独立验收 | 2026-05-21 |
| 以后代码都用 C#（Python 已交付的不动） | 2026-05-22 |
| 文档对 AI 友好、易于维护、不需要用户写专业内容 | 2026-05-22 |
| UI 任何操作必须可观察，禁黑盒——每个 onClick 入口先 appendOutput 一行 | 2026-05-22 |
| 字段命名要让非编程用户看得懂——中文名 + 变量符号 + 单位 + 一句话 hint 同行展示 | 2026-05-22 |

---

## UX 缺口

- ~~底部 Panel 关闭后无 toggle~~ → StatusBar「面板」按钮 + Ctrl+J
- ~~plot_curves 调曲线只能编辑 JSON~~ → RightPanel form + 实时预览
- ~~预设无法新建/重命名/删除~~ → CRUD 全套
- ~~leeb/pdf/word2pdf 工具页没用范式~~ → 已迁
- ~~3 个工具 handleRun 陈旧闭包~~ → 已修（395f05e）
- ~~data_processing calcType 下拉只 1 项~~ → 已加锚杆抗拔（2 项）；等加钻芯/回弹
- ~~锚杆参数表横排 + 裸字母 P/Lf/La/A/E~~ → 已改纵向卡片（中文名 + 单位 + hint）
- ~~RightPanel 内操作无日志反馈~~ → ShellContext + 入口 appendOutput
- ~~点击「生成模板」无反应~~ → 加 dialog:allow-save capability
- ~~文件树双击只 openPath~~ → 双击 xlsx/pdf/docx 自动灌给对应工具
- ~~其他 3 个工具未接 shell.activatedFile~~ → 4 个工具全接（plot_curves/data_processing 收 .xlsx，pdf_tools 收 .pdf 按 mode 分支，word2pdf 收 .docx/.doc 追加去重）
- `data_processing` OpenXML 切 C# 后合并单元格已解决；前端不变
- word2pdf pages 字段只在 Word 保存过的 docx 有——显示「N 段」即可
- 流式进度未做——协议升级方案：JSON-RPC notification → Tauri event
- `App.tsx` 比较胖（270+ 行）+ 嵌套 4 个 Provider——可考虑 `useShellState` hook
- 「新建标准结构」用 `window.prompt`——后续换自定义 modal+toast
- plot_curves 数据对照表格 cell 暂不能跳到曲线上对应点

---

## 会话历史

### [2026-05-23] pdf_tools / word2pdf 接 ShellContext.activatedFile

两个 controller 加 `useShell` + activatedFile useEffect。pdf_tools 按 mode 分支（merge 追加去重、split 覆盖），mode 用 modeRef 防陈旧闭包；word2pdf 追加到 inputs 去重。每个入口先 `appendOutput` 写日志。锚杆数据 sheet 验收通过，模板填充归到「报告生成」阶段（docs/plans/2026-05-29-template-editor.md），计算阶段不再做。

### [2026-05-22] 锚杆抗拔上线 + UX 可观察性补齐

锚杆抗拔（GB 50086-2015）4 commit：C# 计算底座（11 xUnit）→ Excel 读/模板生成/报告表写入（+9 xUnit）→ 3 个 RPC（+4 xUnit）→ 前端 calcType=anchor 子 form。

UX 修复 3 commit：参数表纵向卡片重做、ShellContext 全局可观察性、文件树双击联动、`dialog:allow-save` capability 修复（根因：Tauri 2 显式白名单，saveDialog 未授权被静默拒）。

用户后续重构 FileTree 为 VSCode 风扁平渲染（980 行：右键菜单 + in-place 编辑 + 剪贴板 + 删除回收站 + 焦点 refetch + diff），SideBar 拆 refreshNonce/collapseNonce 双触发，App 默认工具改 data_processing 排首位。后端 `files.py` 加 create_file/create_folder/rename/delete（回收站，send2trash）/copy/move/reveal 共 7 个 RPC，Windows 文件名校验。App 全局拦截 webview 网页式行为：原生 contextmenu / F5 / Ctrl+R / Ctrl+P / Ctrl+S / 文件拖入导航，保留 F12 开发者工具。

### [2026-05-22] AI 上下文文件重构

将 CLAUDE.md（10846 字）砍到宪法级（3788 字节），新增 `.ai/RULES.md`（编码规范+技术债+RPC清单）、`dotnet/CLAUDE.md`（C# 域规则）、`frontend/CLAUDE.md`（前端域规则）。PROGRESS.md 和 CONTEXT.md 重写，职责明确分离，无过期内容。

### [2026-05-20] UI 技术栈转型 + 旧代码大清理

删旧 Qt UI（30+ 源文件 + 20 个 UI 测试 + pyside6/qfluentwidgets/pytest-qt 三个依赖）。保留全部业务底座。

### [2026-05-19] 删项目看板 + INSP-001/002 计算底座交付

### [2026-05-14] 主管线定调：画图✅ → 计算✅ → 数据生成⏳ → 报告填充⏳ → Word 报告⏳
