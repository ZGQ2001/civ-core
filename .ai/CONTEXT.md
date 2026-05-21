# 工作上下文

> 由 AI 维护，跨会话快速进入状态用。**职责分工**：PROGRESS.md = 里程碑/计划/已交付清单（粗粒度）；CONTEXT.md = 当前正在做什么、用户最近偏好、待补 UX、设计妥协（细粒度，时效性强，可频繁覆盖）。

---

## 当前焦点（2026-05-21）

**T5 工具页统一交互范式（中间预览 + 右侧参数）— 1/3 已完成（leeb）**。pdf_tools / word2pdf 待迁。

布局：`ActivityBar | SideBar(全高) | (Editor + 底部输出 Panel) | RightPanel(全高，tab 化)`。

leeb_hardness 工具页（已对齐 plot_curves 范式）：
- 三件套：`controller.tsx`（Provider + useLeeb hook）/ `Page.tsx`（顶部条 + 中间表格预览 + 底部结果）/ `SettingsForm.tsx`（右侧调参：输出路径 + 默认角度）
- 顶部条：选 Excel / Sheet 下拉（preview_excel 一并返）/ 表头行 / 开始计算按钮
- 中间预览：前 50 行表格（深色斑马纹、表头 sticky、`previewShownRows / previewTotalRows` 提示）
- 后端新加 `leeb.preview_excel(path, sheet, header_row, max_rows)` —— sheets + headers + rows + total_rows，4 个 pytest 覆盖
- 公共组件抽：`tools/_shared/forms.tsx`（Field / Picker / ResetBtn / RunBtn）—— 之前耦合在 LeebHardnessTool.tsx 末尾被 pdf/word2pdf 跨文件 import

plot_curves 工具页（中间预览 + 右侧参数 范式）：

plot_curves 工具页（中间预览 + 右侧参数 范式）：
- 顶部操作行：Excel / Sheet 下拉（自动拉 list_sheets）/ 表头行 / 曲线 dropdown（业务 UI 命名"曲线"，code 还叫 preset）/ 曲线按钮组（新建 / 复制 / 重命名 / 删除 / 保存或另存为）/ 跑
- 行号工具条：上一行 / 下一行 / 跳转到第 N 行（number input，blur/Enter 提交）/ 「数据对照」开关
- 预览图：实时（300ms debounce）；图上方工具条；下方按需弹出"数据对照"条带
- 数据对照条带：**只显示图引用的列**（id_column + curves[].points[].var_column），pill 风、横向滚动、一行高
- 右侧 RightPanel tab 化：「调参」（4 sub-tab：基础 / X 轴 / Y 轴 / 曲线，单曲线 form + 数据点子表）+「AI 助手」（占位）

曲线管理（一预设 = 一曲线）：
- list_presets 多返 sources（system/user）；前端按 `[内置]` / `[我的]` 标签区分
- CRUD：save / delete / rename / copy；内置曲线保存时强制弹"另存为"
- 新建曲线时默认模板已带 curves[0]，进 form 无空状态困惑
- form 中删了「曲线名称」字段 + 删了「新增曲线」/「删除曲线」按钮（一预设一曲线原则）

修过的关键 bug：
- 数据对照永远空：原用 `job.output_path.stem` 反查 row 的 id，但 stem 是 `filename_template` 格式化后的全文件名，永远配不上裸 id。改用 BuildSummary 的"跳过行号"集合反推保留行，按 row_index 直接索引。
- 原生控件白底：index.css 加 `html { color-scheme: dark }`，让 number 微调箭头 / color picker / range 槽位都按深色渲染

**屎山清理**：scripts/_*.py 7 个一次性脚本已删（commit 5d6ce79）。其他没积压。

**文档结构**：AI 维护的 PROGRESS.md / CONTEXT.md 已在 `.ai/`（隐藏目录，约定同 `.github/.cursor/.vscode/`）。CLAUDE.md 已同步新文档位置 + RightPanel 布局 + emoji 禁令 + handler `__all__` 强约束。

---

## 下一步候选（按价值排）

1. **T6 打包**：PyInstaller 把 Python sidecar 打成 exe + Tauri `tauri:build` 出安装包
2. **pdf/word2pdf 加输入预览 + 参数挪 RightPanel**（leeb 已完成）：剩 2 个工具的预览分别是「已选 PDF 列表 + 页数」「已选 Word 列表 + 页数估算」；后端各加 `pdf_tools.inspect` / `word2pdf.inspect` RPC
3. **AI 助手 tab 真接通**：当前是占位；接 Anthropic SDK，能看到当前工具 + 工作区上下文，调 RPC 跑工具
4. **Command Palette (Ctrl+P)**：键盘快速触发任何动作（切预设、运行工具、跳文件）
5. **EditorArea Tab 化**：每个工具一个 tab，可关闭可切换（VSCode 多文件 tab 风）
6. **流式进度**：plot_curves 跑大批量时无 N/M 反馈（协议升级方案见妥协项）
7. **数据对照交互升级**：点 cell 高亮曲线上对应点（hit-test，`chart_writer.render_plot_with_hittest` 已有底座）
8. **Toast 通知**：把现在的 alert() 换成右下角 toast

---

## 用户偏好（最近表达，写代码时遵循）

| 偏好 | 来源（会话日期） |
|---|---|
| 不要 JSON 编辑器 — 给不懂编程的人用 form | 2026-05-21 |
| 复刻 VSCode 视觉细节（双色状态栏、SideBar 全高、底部 Panel、Explorer toggle、RightPanel tab 化） | 2026-05-21 |
| 中间上部预览区、右侧参数区，统一交互范式 | 2026-05-21 |
| AI 助手未来常驻 RightPanel，和工具调参共享 tab 栏 | 2026-05-21 |
| 一预设 = 一曲线（form 不展示曲线名字段，数据保留） | 2026-05-21 |
| 全局禁 emoji（UI / commit / AI 文档），Python 旧代码 emoji 按"不动旧代码"暂留 | 2026-05-21 |
| 大需求允许分多次 commit，每次 commit 都能独立验收 | 2026-05-21 |
| commit 后必须 TS / ruff / pytest / healthcheck 全过才能继续 | CLAUDE.md 工作流 |

---

## 已知 UX 待补 / 妥协项

- ~~底部 Panel 关闭后无 toggle 入口~~ → StatusBar「面板」按钮 + Ctrl+J
- ~~plot_curves 调曲线只能编辑 JSON~~ → 已改：RightPanel form + 实时预览
- ~~BottomPanel「工具设置」Tab 空提示~~ → 已挪到 RightPanel
- ~~预设无法新建 / 重命名 / 删除~~ → CRUD 全套 + 顶部按钮组完成
- ~~没有数据点增删 form~~ → CurvesTab 全量 accordion + PointsEditor 完成
- ~~RightPanel 没 tab，没法预留 agent~~ → 已 tab 化，agent 占位 tab 已加
- ~~UI 散布 emoji~~ → 前端 UI 已清；Python CLI / log / 注释里按"不动旧代码"暂留
- ~~`leeb` 工具页没用 RightPanel + 中间预览范式~~ → 已迁
- `pdf/word2pdf` 工具页**还没用 RightPanel + 中间预览范式**，参数和操作都堆在 EditorArea 主区 — 候选 #2
- `points` 字段编辑要求用户懂 fixed_axis 概念（X 固定 vs Y 固定），不懂的人可能困惑 — 未来可加示意图或更友好的"按位置选点"
- 「刷新」「全部折叠」共用 refreshKey 整树重挂，丢失 expanded 状态（VSCode refresh 应保留）
- 「新建标准结构」/ 预设 CRUD 用 `window.prompt` / `confirm`（样式不可控）— 后续换自定义 modal + toast
- 流式进度未做 — 协议升级方案：sidecar stdout 写 JSON-RPC notification，Rust 转发 Tauri event，前端 listen
- 数据对照表格点 cell 暂不能跳到曲线上对应点（已有 hit-test 底座 `render_plot_with_hittest`，留候选 #7）
- `App.tsx` 比较胖（200+ 行）；如果再加面板或 agent 状态可考虑拆个 `useShellState` hook

---

## RPC 方法清单（前端调用时对照）

| 方法 | 用途 |
|---|---|
| `ping` / `version` | 桥联自测 |
| `workspace.{last,set,clear,create_standard}` | 工作区记忆 + 新建标准骨架 |
| `files.{list_dir,exists}` | Explorer 文件树 |
| `plot_curves.list_presets` | 返回 `{presets, default, details, sources}` 含全 JSON + 来源 |
| `plot_curves.list_sheets` | 选 Excel 后拉 sheet dropdown |
| `plot_curves.render_preview` | preset_dict + 行号 → 实时 PNG base64 + row_data |
| `plot_curves.run` | 批量出图；preset_override 覆盖预设跑 |
| `plot_curves.preflight` | 跑前预检列名匹配 |
| `plot_curves.save_preset` / `delete_preset` / `rename_preset` / `copy_preset` | 用户预设 CRUD |
| `leeb.run` | 里氏硬度 INSP-001 |
| `leeb.preview_excel` | leeb 工具页前 N 行表格预览（含 sheets + headers + rows + total_rows） |
| `pdf_tools.{merge,split_per_page,split_by_ranges}` | PDF 合并/拆分 |
| `word2pdf.convert` | Word→PDF 批量（COM） |

**新加 RPC 必须在 handler 模块加 `__all__` 白名单** — 否则顶部 import 的 Path/dataclass 会被 `register_module` 误暴露成 RPC 方法（已在 server.py 修过这个 bug，但行为依赖 `__all__`）。

---

## 验收清单（每次 commit 前过一遍）

```bash
cd frontend && npx tsc -b --noEmit        # TS 类型
uv run --frozen ruff check .              # Python lint
uv run --frozen pytest -q                 # 测试（当前 315 passed）
uv run --frozen python scripts/healthcheck.py  # 6 项冒烟
```

只动前端时仅前 1 项必跑；改了 Python 必跑全部 4 项。

---

## 维护规则

- 每会话开始读这个文件 → 接续上次焦点
- 完成一个细粒度阶段就更新「当前焦点」下一步
- 用户表达新偏好就加到「用户偏好」表
- 妥协项做完了就划掉（`~~xxx~~`），新妥协项加到底部
- 大里程碑（T5/T6/T7 这种）完成后写入 PROGRESS.md 的「已交付」表；这里不重复
- 不用 emoji
