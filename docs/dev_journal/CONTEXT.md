# 工作上下文

> 由 AI 维护，跨会话快速进入状态用。**职责分工**：PROGRESS.md = 里程碑/计划/已交付清单（粗粒度）；CONTEXT.md = 当前正在做什么、用户最近偏好、待补 UX、设计妥协（细粒度，时效性强，可频繁覆盖）。

---

## 🎯 当前焦点（2026-05-21）

**T5 收尾 + UI 抛光。** T5.1-5.4 四个工具页（plot_curves / leeb / pdf / word2pdf）端到端已通；当前在修 UI 妥协项 + plot_curves 做实时预览 + form 调参。

**下一步具体动作**：
1. 后端加 `plot_curves.render_preview(preset_dict, excel_path, sheet, header_row) -> {png_base64}`，复用 `chart_writer.render_plot_to_bytes`
2. 前端 plot_curves 工具页改造为「上预览 + 下 form 调参」（底部 Panel 接管参数面板）
3. form 字段：title_template、x/y axis label+range、curves[0] color/linewidth/markersize/marker；不暴露 points（嵌套数组，留高级用户编辑 JSON）

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

- ~~底部 Panel 关闭后无 toggle 入口~~ → batch 1 修
- ~~plot_curves 调曲线只能编辑 JSON~~ → batch 3 改 form + 实时预览
- 「刷新」「全部折叠」共用 refreshKey 整树重挂，丢失 expanded 状态（VSCode refresh 应保留）
- 「新建标准结构」用 `window.prompt` 输项目名（样式不可控）；后续换自定义 modal
- 流式进度未做（plot_curves 跑大批量时无 N/M 反馈）—— 协议升级方案：sidecar stdout 写 JSON-RPC notification，Rust 转发 Tauri event，前端 listen
- BottomPanel「工具设置」Tab 当前是空提示；plot_curves 调参（batch 3）会接管这个 Tab，让其他工具也能用同样位置放参数

---

## 🔌 RPC 方法清单（前端调用时对照）

| 方法 | 用途 |
|---|---|
| `ping` / `version` | 桥联自测 |
| `workspace.{last,set,clear,create_standard}` | 工作区记忆 + 新建标准骨架 |
| `files.{list_dir,exists}` | Explorer 文件树 |
| `plot_curves.{list_presets,run,preflight}` | 绘曲线图（list_presets 含 details 字段） |
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
