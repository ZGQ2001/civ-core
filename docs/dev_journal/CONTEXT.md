# 工作上下文

> 由 AI 维护，跨会话快速进入状态用。**职责分工**：PROGRESS.md = 里程碑/计划/已交付清单（粗粒度）；CONTEXT.md = 当前正在做什么、用户最近偏好、待补 UX、设计妥协（细粒度，时效性强，可频繁覆盖）。

---

## 🎯 当前焦点（2026-05-21）

**T5 全员闭环 + plot_curves 体验抛光完成。** 工具页主区：sheet / 表头行 / 预设 / 实时预览图 / 多行翻页 / 「查看本行原始数据」折叠表（高亮预设引用的列）；底部 Panel 「工具设置」拆 4 tab（基础 / X 轴 / Y 轴 / 曲线样式），全部 form 无 JSON。其他工具页（leeb/pdf/word2pdf）已端到端通。

**屎山清理**：scripts/_*.py 7 个一次性脚本已删（commit 5d6ce79）。其他没积压。

**下一步候选**（按价值排）：
1. **T6 打包**：PyInstaller 把 Python sidecar 打成 exe + Tauri `tauri:build` 出安装包
2. **leeb/pdf/word2pdf 也用 Context lift state**：参数页可以放底部 Panel（统一交互范式），但代价是 4× 重构
3. **plot_curves 多曲线 form**：当前只暴露第 1 条曲线样式；多曲线需 tabs 或 accordion
4. **流式进度**：plot_curves 跑大批量时无反馈（协议升级方案见妥协项）
5. **数据对照交互升级**：点 cell 高亮曲线上对应点（hit-test，chart_writer 里 render_plot_with_hittest 已有）

---

## 🤝 用户偏好（最近表达，写代码时遵循）

| 偏好 | 来源（会话日期） |
|---|---|
| 不要 JSON 编辑器 — 给不懂编程的人用 form | 2026-05-21 |
| 复刻 VSCode 视觉细节（双色状态栏、底部 Panel、Explorer toggle、Activity Bar 招牌指示条） | 2026-05-21 |
| 调参面板放底部 Panel，预览图放工具页主区 | 2026-05-21 |
| 大需求允许分多次 commit，每次 commit 都能独立验收 | 2026-05-21 |
| commit 后必须 TS / ruff / pytest / healthcheck 全过才能继续 | CLAUDE.md 工作流 |

---

## 🧩 已知 UX 待补 / 妥协项（小条目，按优先级）

- ~~底部 Panel 关闭后无 toggle 入口~~ → 已修：StatusBar「面板」按钮 + Ctrl+J
- ~~plot_curves 调曲线只能编辑 JSON~~ → 已改：底部 Panel form 表单 + 实时预览
- ~~BottomPanel「工具设置」Tab 当前是空提示~~ → 已接：plot_curves 时显示 SettingsForm
- plot_curves form 只暴露**第 1 条曲线**样式；多曲线预设要改其他曲线得后续做 tabs/accordion（form 已拆 4 tab：基础/X 轴/Y 轴/曲线样式）
- plot_curves form **不暴露 `points`**（嵌套数组，复杂；高级用户直接编辑 JSON 预设文件）
- 数据对照表格在预览图下方折叠区，高亮预设引用的列；点 cell 暂不能跳到曲线上对应点
- leeb / pdf / word2pdf 工具页**没有用 Context lift state**，参数在工具页内（不在底部 Panel）—— 如果用户要求统一交互范式，每个工具都要做 Context 改造
- 「刷新」「全部折叠」共用 refreshKey 整树重挂，丢失 expanded 状态（VSCode refresh 应保留）
- 「新建标准结构」用 `window.prompt` 输项目名（样式不可控）；后续换自定义 modal
- 流式进度未做（plot_curves 跑大批量时无 N/M 反馈）—— 协议升级方案：sidecar stdout 写 JSON-RPC notification，Rust 转发 Tauri event，前端 listen

---

## 🔌 RPC 方法清单（前端调用时对照）

| 方法 | 用途 |
|---|---|
| `ping` / `version` | 桥联自测 |
| `workspace.{last,set,clear,create_standard}` | 工作区记忆 + 新建标准骨架 |
| `files.{list_dir,exists}` | Explorer 文件树 |
| `plot_curves.{list_presets,run,preflight,render_preview}` | 绘曲线图；render_preview 给前端实时预览（PNG base64） |
| `leeb.run` | 里氏硬度 INSP-001 |
| `pdf_tools.{merge,split_per_page,split_by_ranges}` | PDF 合并/拆分 |
| `word2pdf.convert` | Word→PDF 批量（COM） |

⚠️ 新加 RPC 方法必须在 handler 模块加 `__all__` 白名单 — 否则顶部 import 的 Path/dataclass 会被 `register_module` 误暴露成 RPC 方法（已在 server.py 修过这个 bug，但行为依赖 `__all__`）。

---

## 🧪 验收清单（每次 commit 前过一遍）

```bash
cd frontend && npx tsc -b --noEmit        # TS 类型
uv run --frozen ruff check .              # Python lint
uv run --frozen pytest -q                 # 测试（当前 309 passed）
uv run --frozen python scripts/healthcheck.py  # 6 项冒烟
```

只动前端时仅前 1 项必跑；改了 Python 必跑全部 4 项。

---

## 📝 维护规则

- 每会话开始读这个文件 → 接续上次焦点
- 完成一个细粒度阶段就更新「当前焦点」下一步
- 用户表达新偏好就加到「用户偏好」表
- 妥协项做完了就划掉（`~~xxx~~`），新妥协项加到底部
- 大里程碑（T5/T6/T7 这种）完成后写入 PROGRESS.md 的「已交付」表；这里不重复
