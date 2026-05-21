# 工作上下文

> **角色**：当前焦点、UX 缺口、用户偏好。**每会话更新**，时效性强。
> **维护**：AI 每次会话结束时更新。里程碑级变动记 PROGRESS.md，这里不重复。
> **配套**：`CLAUDE.md`（宪法）| `RULES.md`（规范）| `PROGRESS.md`（里程碑）

---

## 当前焦点（2026-05-22）

**T5.5 Step 4 完成**：leeb 整套迁 C#。

- C# sidecar 已接管 leeb.run / leeb.preview_excel / xlsx.write_leeb_report_table
- Python 端 6 文件已删（handler/leeb_excel/calc_leeb_* + 4 个测试文件）
- SidecarRouter 路由默认 C#，Python 白名单
- C# 41 个 xUnit 测试（40 通过，1 Skip 真实数据集成）
- Python 283 pytest 全过
- C# 数值与 Python 黄金值完全一致（comp_fb_min_avg=512）

**Python 剩余职责**：workspace/files/plot_curves/pdf_tools/word2pdf + seeds standards.db

---

## 下一步候选（按价值排）

1. **修复 3 个前端 stale closure**：plot_curves/pdf_tools/word2pdf 的 `handleRun` 闭包陈旧
2. **T5.5 Step 3：报告生成工具页** — 新 ActivityBar 项，doc.compose_report（变量替换 + xlsx 嵌入 + 图片嵌入）
3. **Tauri sidecar 加超时 + 自动重启** — read_line 加 tokio::time::timeout，崩溃自动 respawn
4. **钻芯/回弹切 C#** — data_processing calcType 下拉加新项
5. **T6 打包** — PyInstaller + dotnet publish + Tauri externalBin

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

---

## UX 缺口

- ~~底部 Panel 关闭后无 toggle~~ → StatusBar「面板」按钮 + Ctrl+J
- ~~plot_curves 调曲线只能编辑 JSON~~ → RightPanel form + 实时预览
- ~~预设无法新建/重命名/删除~~ → CRUD 全套
- ~~leeb/pdf/word2pdf 工具页没用范式~~ → 已迁
- **3 个工具 handleRun 陈旧闭包** → 底部输出面板永不触发（🔴）
- `data_processing` OpenXML 切 C# 后合并单元格已解决；前端不变
- data_processing calcType 下拉只 1 项——等加钻芯/回弹就自然了
- word2pdf pages 字段只在 Word 保存过的 docx 有——显示「N 段」即可
- 流式进度未做——协议升级方案：JSON-RPC notification → Tauri event
- `App.tsx` 比较胖（200+ 行）+ 嵌套 4 个 Provider——可考虑 `useShellState` hook
- 「新建标准结构」用 `window.prompt`——后续换自定义 modal+toast
- plot_curves 数据对照表格 cell 暂不能跳到曲线上对应点

---

## 会话历史

### [2026-05-22] AI 上下文文件重构

将 CLAUDE.md（10846 字）砍到宪法级（3788 字节），新增 `.ai/RULES.md`（编码规范+技术债+RPC清单）、`dotnet/CLAUDE.md`（C# 域规则）、`frontend/CLAUDE.md`（前端域规则）。PROGRESS.md 和 CONTEXT.md 重写，职责明确分离，无过期内容。

### [2026-05-20] UI 技术栈转型 + 旧代码大清理

删旧 Qt UI（30+ 源文件 + 20 个 UI 测试 + pyside6/qfluentwidgets/pytest-qt 三个依赖）。保留全部业务底座。

### [2026-05-19] 删项目看板 + INSP-001/002 计算底座交付

### [2026-05-14] 主管线定调：画图✅ → 计算✅ → 数据生成⏳ → 报告填充⏳ → Word 报告⏳
