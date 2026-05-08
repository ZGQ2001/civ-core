# 开发日志

> 本文件由 AI 维护，用户可读可改。 每次任务结束后，AI 负责更新此文档（表述 AI 友好） 。
> **AI 启动时只需读”顶部摘要”区段**即可知道做什么。

-----

## 📌 顶部摘要（必读）

**当前状态：** T-0~T-4 完成 + P1/QSplitter 宽度记忆 + P1/预览区 + P1/pytest-qt + P1/日志面板 完成；项目更名 `civil-auto-workspace` → `civ-core`（筑核）已落地（commit `a6fe1f9`）；181 测试通过；healthcheck 8 项全 ✅。

**当前任务：** P1（候选：完整 curves 编辑器）—— 等用户对齐具体子任务范围

**下一步：**
1. **用户侧待办**：① GitHub 仓库重命名 `Civil-Auto-Workspace` → `civ-core`（Settings 页或 `gh repo rename`）；② 关闭会话后手工 `Rename-Item D:\CodeProjects\Civil_Auto_Workspace civ-core` + `uv sync`；详见会话历史 2026-05-08
2. AI 侧：等用户在新路径重开会话后，更新 `git remote set-url` 并对齐 P1 子任务

**遗留问题：**
- `tests/test_cross_ref_fix.py` 引用旧的 `civ_core.models.schema`，已知 stale，已写到 pyproject.toml addopts 默认 ignore（待 02_Core 整体迁移完成后删除）
- 41 个 pyright 报错全在未迁移的旧代码中，新代码零报错
- 旧 Qt QSettings 键名（applicationName=`CivilAuto`）已废，下次启动 GUI 三栏宽度/窗口几何会回到默认一次

---
### 可用指令（动态更新）

```bash
uv run python -m civ_core.main                        # 启动 GUI
uv run python -m civ_core.main --list-presets         # 列出预设（系统+用户合并）
uv run python -m civ_core.main --tool plot_curves \
    --input data/raw/sample.xlsx \
    --preset 锚杆荷载-位移曲线 \
    --output data/output/曲线图                          # CLI 出图
uv run python -m pytest                                 # 跑测试（pytest 配置已 ignore stale 测试）
uv run ruff check .                                     # lint（每次 step 完成后必跑）
uv run ruff check --fix .                               # lint 自动修
uv run python scripts/healthcheck.py                    # 健康检查（每次验收后必跑）

# 切换 DEV_MODE：编辑 config.toml [dev].enabled = true，
# 用户预设会改读 tests/fixtures/presets/plot_curves/curve_presets.json
```

-----

## 📋 当前任务详情：预设系统完整实现

### T-0：命名统一 ✅ 已完成（2026-05-07）

按 11 步推进，每步一个 commit：

| Step | 改动                                                                       | Commit |
| ---- | ------------------------------------------------------------------------ | ------- |
| 1    | `git mv templates/plot_curves/curve_templates.json → presets/plot_curves/curve_presets.json`，建 `tests/fixtures/presets/.gitkeep` | `186b832` |
| 2    | `config.toml`：`curve_templates` 键 → `curve_presets`                       | `42b4f36` |
| 3    | `configs/loader.py`：`PathsConfig.curve_templates` → `curve_presets`      | `ebe55f6` |
| 4    | `core/plot_curves.py`：`load_templates`/`get_template_names`/`_series_from_template` → `_presets`，参数 `template_name`/`templates_path` → `preset_name`/`presets_path` | `e9898d0` |
| 5    | `domain/schema.py`：`PlotRunSettings.template_name` → `preset_name`        | `0c2ad04` |
| 6    | `git mv template_list.py → preset_list.py`；`TemplateListPane` → `PresetListPane`，信号/方法/UI 文字同步 | `d9ae868` |
| 7    | `plot_settings_panel.py`：`set_template_name` → `set_preset_name`，`_template_label` → `_preset_label`，"当前模板" → "当前预设" | `1f112fa` |
| 8    | `plot_curves_view.py`：`template_pane` → `preset_pane`，`_on_template_selected` → `_on_preset_selected`，worker 改用 `preset_name` | `12c1276` |
| 9    | `main.py` CLI：`--template`/`--templates-path`/`--list-templates` → `--preset`/`--presets-path`/`--list-presets` | `328a517` |
| 10   | 验收：grep 通过；27 测试通过；`--list-presets` 输出正常；`--list-templates` 已弃用       | —         |
| 11   | 更新本文档                                                                  | （本次提交）  |

**保留 `template` 命名的位置（不属于"预设"概念）：**
1. `paths.templates`（`./templates`，docx/xlsx 报告模板中心）
2. `utils/exceptions.py: TemplateMissing`（docx/xlsx 报告模板缺失异常）
3. `core/auto_filler_core.py: handright.Template`（第三方库类）
4. JSON 字段 `filename_template` / `title_template`（含 `{id}` 占位的字面字符串模板）

**验收结果：** `grep -i template src/` 仅剩上述 4 类预定保留项；`pytest`（除 stale 旧测试）27 通过；CLI `--list-presets` 工作正常。

-----

### T-1：preset_manager.py（双路径加载 + 顶层合并）✅ 已完成（2026-05-07）

按 8 步推进，每步一个 commit：

| Step | 改动 | Commit |
| ---- | --- | ------- |
| 1 | 登记 stale 测试到 P2 待办 | `31da156` |
| 2 | `config.toml` 加 `[dev]` 段（默认 enabled=false） | `b1aa81f` |
| 3 | `loader.py` 加 `DevConfig` + 派生 `paths.user_presets_dir`；自动 mkdir | `0795ac8` |
| 4 | 新建 `infra_io/preset_manager.py`：`load_merged_presets` / `PresetEntry` / `PresetSource` / 严格读 + 宽松读 | `0bfb9eb` |
| 5 | `core/plot_curves.py:load_presets` 默认走 `load_merged_presets_as_dict`，显式 `presets_path` 仍单文件直读 | `d794b2c` |
| 6 | 新增 `tests/test_preset_manager.py`（23 用例：合并语义 / 兜底 / DEV 路径切换） | `373431f` |
| 7 | 新增 fixture 用户预设 `tests/fixtures/presets/plot_curves/curve_presets.json` + 手动合并验收 | `fcb3ceb` |
| 8 | 更新 PROGRESS.md | （本次） |

**实现的合并语义（顶层名字 key 级，不递归到内部字段）：**

```
presets/plot_curves/curve_presets.json   （系统，只读）
~/.civ-core/presets/plot_curves/curve_presets.json   （用户，可写）
            ↓                                  ↓
            └────── 顶层合并 ──────────────────┘
                        ↓
                  PresetEntry 列表
（系统按原序遍历 → 同名被用户覆盖时保留位置且 source=USER → 用户独有的追加到末尾）
```

**dev.enabled 切换（验证通过）：**
- `true`  → 用户预设走 `tests/fixtures/presets/plot_curves/curve_presets.json`（仓库内，git 管理）
- `false` → 用户预设走 `~/.civ-core/presets/plot_curves/curve_presets.json`（用户家目录）
- 用户目录不存在自动 mkdir（loader 兜底）；用户文件不存在 → 当空字典处理，不抛

**硬性要求兑现：**
- ✅ 用户目录不存在 → 静默创建（`_resolve_paths` 内 mkdir parents=True exist_ok=True）
- ✅ 用户预设文件不存在 → 用系统预设兜底（`_read_json_lenient` 返空 dict）
- ✅ 用户预设 JSON 坏 → log warning 后兜底返空，不让用户改坏自己的预设搞挂程序
- ✅ 系统预设缺失 / 坏 → 抛 PresetError（致命，必须修）
- ✅ 禁止运行时写入 `presets/`（preset_manager 只读，写入留给 T-4 编辑器）

**API：**
```python
load_merged_presets(tool="plot_curves") -> list[PresetEntry]
load_merged_presets_as_dict(tool="plot_curves") -> dict[str, dict]
get_system_presets_path(tool="plot_curves") -> Path
get_user_presets_path(tool="plot_curves") -> Path
```

-----

### T-2：config/loader.py 更新（已被 T-1/3 吸收）

`user_presets_dir` 派生字段、按 `dev.enabled` 切换路径、自动 mkdir，全部在 T-1 Step 3
（commit `0795ac8`）已完成。本步骤剩余工作量为零，可直接进 T-3。

-----

### T-3：主流程接入 ✅ 已完成（2026-05-07）

| Step | 改动 | Commit |
| ---- | --- | ------- |
| 1-3  | `ui/components/preset_list.py` 改用 `load_merged_presets("plot_curves")`，列表项前缀 🔒/✏️ 图标，UserRole 改存整张 PresetEntry，新增 `selected_preset_entry()` API；状态行 `"系统 N ・ 我的 M"`；异常面切到 `PresetError` | `87a771f` |
| 4    | 验收：50 测试通过、`--list-presets` 正常、模块 import 无误 | — |
| 5    | 更新 PROGRESS.md | （本次） |

**注意**：`core/plot_curves.py` 在 T-1/5 已经接入 `load_merged_presets_as_dict`，本步骤只需补 UI 侧。

**`_on_current_changed` 的隐患修复**：原代码 `name = current.text()` 在加了图标前缀后会拿到 `"🔒 锚杆荷载-位移曲线"` 这种带前缀字符串，T-3 改成从 `PresetEntry.name` 读，保证发出的信号是真预设名。这个坑写完留个心眼是值得的。

-----

### T-4：预设管理 UI 重设计 ✅ 已完成（2026-05-07）

按 6 步推进，每步一个 commit（含 Step 0 = CI 修复 + healthcheck 补漏）：

| Step | 改动                                                                                       | Commit       |
| ---- | ----------------------------------------------------------------------------------------- | ------------ |
| 0a   | `pyproject.toml addopts` 默认 `--ignore=tests/test_cross_ref_fix.py`，CI 不再因 stale 测试中断 | `55ee90e`    |
| 1    | `infra_io/preset_manager.py` 加 3 个写入 API（`save_user_preset` / `delete_user_preset` / `copy_system_to_user`），全走 `atomic_writer`；测试 +20 用例 | `4c976db`    |
| 2    | 新建 `ui/components/preset_form_panel.py`：「预设设置」表单，`set_entry` / `current_data` / `set_read_only` / `dirty_changed` 四件套；`_RangeRow` 处理 `[min,max,step]` ↔ `null`；curves 字段先用 JSON 文本框 | `dd170fc`    |
| 3    | 新建 `ui/components/plot_center_pane.py`：Pivot + QStackedWidget 双 Tab；改 `plot_curves_view.py` 把中栏从 `PlotSettingsPanel` 换成 `PlotCenterPane`，选预设时联动 `form_panel.set_entry` + 切到「预设设置」Tab | `8b3488a`    |
| 4    | `preset_list.py` 加底部按钮组 [+新建][复制][删除]；`_NameInputDialog`（MessageBoxBase 派生）；`refresh(select_name=...)`；按钮态按 source 联动；`+新建` 经 `new_preset_requested` 信号通知 view | `a20cf04`    |
| 0b   | 新建 `scripts/healthcheck.py`（项目宪法补漏）：5 个检查项覆盖配置/系统预设读/用户预设写/CLI/GUI；输出纯中文 ✅/❌ | `9905520`    |
| 5    | `preset_form_panel.py` 加底部按钮三态（系统 → [复制为我的]；用户 → [保存修改][重置]；新建 → [保存为我的预设][取消]）；非 dirty 时保存按钮禁用；`plot_curves_view.py` 加 4 个槽 + 静态 `_validate_preset_form`；测试 +30 用例 | `fcb052a`    |
| 6    | 验收 + 更新本文档                                                                            | （本次提交）  |

**交付的交互规则（与 T-4 设计稿一致）：**

- 单击预设 → 自动切到「预设设置」Tab，所有字段联动刷新
- 🔒 系统预设 → 表单只读 + 单按钮 [复制为我的预设]（与左栏底部「复制」按钮等价）
- ✏️ 我的预设 → 表单可编辑 + [保存修改][重置]，dirty 检测控制保存按钮启用
- [+新建] → 切「预设设置」Tab + 字段清空 + [保存为我的预设][取消]

**保存校验（一次性返回所有问题，黄色 InfoBar 列出）：**
- name 非空 + 不以下划线开头
- id_column / 文件名模板 / 标题模板 / 轴标签 非空
- filename_template 必含 `{id}`
- range 非 null 时 `min < max && step > 0`
- curves 是 list；若 JSON 解析失败标记被识别就直接拒；每条至少有 name

**保存语义：** `save_user_preset(name, data)` 是 upsert（同名覆盖）。
- 用户预设态改 name 后保存 = 新增一条用户预设（旧的不动）= "另存为"
- 用户预设态保持 name 保存 = 覆盖原条目
- 新建态 name 与系统预设同名 = 用户预设覆盖系统预设（合并语义自动接管）

**不在本轮范围（已登记 P1 待办）：**
- 完整可视化 curves 编辑器（迁 02_Core/curve_template_editor.py）
- 预览区（缩略图列表 + 单击放大）

-----

### P1/QSplitter 宽度记忆 ✅ 已完成（2026-05-07）

| Step | 改动 | Commit |
| ---- | --- | ------- |
| 1 | `plot_curves_view.py` 加 QSettings 持久化（`_make_settings` / `_restore_splitter_sizes` / `_on_splitter_moved`）；`splitter.splitterMoved` 信号触发即时写盘；非数字 / 长度 ≠ 3 / 含 0 都回退默认；新增 `tests/test_splitter_persistence.py` 8 用例 | `3646f72` |
| 2 | `scripts/healthcheck.py` 加第 6 项「布局记忆功能正常」（独立探针 key，不污染用户保存的拖动状态）；更新 PROGRESS.md | `90f86b8` |

**存储位置（Qt native，无需我们管理路径）：**
- Windows  `HKCU\Software\ZGQ\CivCore`
- Linux    `~/.config/ZGQ/CivCore.conf`
- macOS    `~/Library/Preferences/com.ZGQ.CivCore.plist`

-----

### P1/预览区 ✅ 已完成（2026-05-07）

| Step | 改动 | Commit |
| ---- | --- | ------- |
| 1 | 新建 `ui/components/preview_pane.py`：QSplitter 垂直分割（大图区 + 缩略图列表）；ListWidget IconMode 96×96 缩略图；QLabel 大图等比缩放、resize 自动重缩放；同步加载 PNG，加载失败兜底；测试 +13 用例 | `2d00109` |
| 2 | `plot_curves_view.py` 把右栏 `_PanePlaceholder` 换成 `PreviewPane`；接 worker `started`→`clear()` / `finished`→`set_results(written)`；删掉无用的 `_PanePlaceholder` 类；healthcheck 加第 7 项「预览区功能正常」+ 现有 GUI 检查项加预览区存在性断言；更新本文档 | （本次） |

**用户体验：**
- 出图开始时 → 缩略图列表清空，立刻反馈"开始新一轮"
- 完成后 → 缩略图列出全部 PNG，默认选中第一张大图查看
- 单击其它缩略图 → 大图自动切换；resize 窗口大图自动重缩放
- 部分失败时仍展示成功的图（坏图不阻塞）

**不在本轮范围（待后续）：**
- 双击缩略图打开系统默认查看器（更高保真）
- 历史出图记录（用户目前只能手工去 output 目录翻老图）

-----

### P1/pytest-qt + 日志面板 ✅ 已完成（2026-05-07）

| Step | 改动 | Commit |
| ---- | --- | ------- |
| 1 | `[dependency-groups].dev` 加 `pytest-qt>=4.4`；`uv sync` 拉到 4.5.0 | `9a3d0a4` |
| 2 | 新建 `ui/components/log_panel.py` LogPanel 折叠面板（QPlainTextEdit + appendHtml 上色 + setMaximumBlockCount(1000) 自动丢老 + 工具栏：折叠 / 级别筛选 / 自动滚动 / 清空）；测试 +24 用例（首次用 qtbot fixture） | `d467348` |
| 3 | `plot_curves_view.py` 在 outer VBox 末尾接 LogPanel + 构造时通过 `get_qt_bridge()` 自取信号桥；`bootstrap.py` 更新 outdated comment；healthcheck 加第 8 项「日志面板功能正常」（QtLogBridge round-trip 探针）+ GUI 检查加 `log_panel` 存在断言；更新 PROGRESS.md | （本次） |

**用户体验：**
- 默认折叠：开屏看不到日志，工具栏占一行（约 36px 高）
- 点 ▶ 展开：QPlainTextEdit 显示按级别上色的最近 1000 条
- 默认 INFO 以上，DEBUG 噪音不出现；用户可改"全部"看 DEBUG
- 自动滚动可关，便于回看历史；清空按钮一键归零
- worker 线程 log.info() 也能出现在面板（QtLogBridge 跨线程队列连接）

**架构闭环：**
`logger.info(...)` → root logger
  ├→ console handler  ─── 控制台彩色输出
  ├→ RotatingFileHandler ─ logs/app.log 落盘
  └→ _QtSignalHandler ─── QtLogBridge.record_emitted ─→ LogPanel.on_record

-----

## 📦 待办积压

### P1：绘曲线图 GUI 收尾

- ~~QSplitter 宽度记忆（QSettings 持久化）~~ ✅ 完成（`3646f72` + `90f86b8`）
- ~~预览区实现（缩略图列表 + 单击放大）~~ ✅ 完成（`2d00109` + `6c7e43d`）
- ~~pytest-qt 装到 `[dependency-groups].dev`~~ ✅ 完成（`9a3d0a4`）
- ~~日志面板接入（`QtLogBridge` 已就绪，连 UI 槽）~~ ✅ 完成（`d467348` + 本次）
- 预设编辑器迁移（`old_code_02_Core/curve_template_editor.py`）—— T-4 已用 JSON 文本框临时替代，后续做完整可视化编辑器
- **P1/UI 重构：双栏布局 + 实时预览 + 数据源 Tab（完成 plot_curves 模块可用性交付）**

  **目标**：把当前"三栏 + 切 Tab"的形态改成"左图右控 + 底栏多 Tab"，参数改完即时看到曲线变化，土木使用者直接照业务流程从上到下填表即可出图。

  **L-1：布局重构（三栏 → 两栏）**
  - 删除 `plot_center_pane.py` 的 Pivot+QStackedWidget 双 Tab 结构
  - 主视图改为 QSplitter 水平两栏：
    - **左栏（实时预览区）**：单图大图渲染，参数变化后自动重绘当前选中预设的代表数据；保留缩略图（多数据/批量出图时）
    - **右栏（参数面板）**：风琴式折叠（QToolBox 或 qfluentwidgets `ExpandLayout`+`SettingCardGroup`）
  - QSettings 持久化键名沿用现有 `splitter_sizes`，但维度从 3 → 2；首次启动给安全默认值（如 `[600, 400]`）
  - 涉及文件：`ui/views/plot_curves_view.py`、`ui/components/plot_center_pane.py`（删除或改造）

  **L-2：实时渲染管线（防抖 + DataFrame 缓存）**
  - 新建 `ui/components/live_preview_pane.py`：`set_preset(entry)` / `set_data_source(path)` / `request_redraw()`，内部用 `QTimer.singleShot(300ms)` 做防抖，多次 `valueChanged` 合并成一次重绘
  - 新建 `core/data_cache.py`：`ExcelDataCache` 单例，按 `(path, mtime)` 缓存 DataFrame（实际用 `dict[str, list[dict]]`，遵守 CLAUDE.md 禁 pandas 约定，存 openpyxl 读出的纯 dict 列表）；切预设时只重读映射规则不重读 Excel
  - 参数面板每个控件的 `valueChanged` / `editingFinished` → 发 `preset_param_changed(field, value)` → view 层节流后调 `live_preview_pane.request_redraw()`
  - 渲染走 worker 线程（沿用现有 `core.plot_curves`），但出图改成"渲到内存 BytesIO → QPixmap"，避免反复落盘
  - 多数据/批量出图按钮单独保留（沿用旧的 worker→PNG 流程）

  **L-3：参数面板风琴式重排**
  - 新建 `ui/components/preset_accordion_panel.py`，按土木出图业务流程分组（自上而下）：
    1. **预设选择**（永远置顶不可折叠）：QComboBox 下拉列表 + 「最近使用」的 3 个置顶项（QSettings 存 `recent_presets` 字符串列表）+ 列表底部 `[+新建] [复制] [删除]` 三按钮
    2. **数据源**：Excel 路径 + 表头行号 + ID 列名
    3. **曲线定义**（curves）：每条曲线 X/Y 列、颜色、标签
    4. **坐标轴**：X/Y 轴范围（min/max/step）、轴标签、刻度
    5. **样式**：图例位置、网格、线宽
    6. **输出**：文件名模板、标题模板、DPI
  - 数值类参数（轴范围、DPI、线宽等）一律「滑块 + QSpinBox/QLineEdit」联动组合（封装成 `_SliderInputRow` 复用控件）
  - 删除按钮二次确认：用 `qfluentwidgets.MessageBox`（不要原生 QMessageBox）；按钮文案明确写要删的预设名
  - 系统预设可编辑：保存时走 `copy_system_to_user(name)`（preset_manager.py 已有 API），下次启动用户预设自动覆盖；UI 不再显示 🔒/✏️ 区分，但状态行显示「来源：系统/我的，保存后将存为我的预设」

  **L-4：底栏新增「数据源」Tab + 与曲线双向高亮**
  - 改造 `ui/components/log_panel.py` 为 `BottomTabPanel`（折叠面板内嵌 QTabWidget）
    - Tab 1：日志（沿用现有 LogPanel 内容）
    - Tab 2：数据源（新增）
  - 新建 `ui/components/data_source_pane.py`：QTableView + QStandardItemModel；`set_preset_and_data(entry, rows)` 时按 `entry` 的 `id_column` + `curves[*].x_column` + `curves[*].y_column` 过滤出"关键映射列"，其它列隐藏
  - 双向高亮联动：
    - 点击表格行 → 发 `row_highlighted(int)` → live_preview 在曲线上画标记点
    - 鼠标悬停曲线点 → live_preview 发 `curve_point_hovered(row_index)` → 表格滚动到该行并高亮
  - 折叠/展开状态写入 QSettings（沿用现有 LogPanel 的持久化键）

  **L-5：测试 + healthcheck 补漏**
  - `tests/test_data_cache.py`：相同 (path, mtime) 命中缓存，mtime 变更触发重读
  - `tests/test_live_preview_pane.py`：300ms 内连发 5 次 valueChanged 只触发 1 次重绘（用 `qtbot.wait`）
  - `tests/test_preset_accordion_panel.py`：滑块⇄输入框双向联动；删除按钮弹二次确认对话框；系统预设保存后落到用户预设目录
  - `tests/test_data_source_pane.py`：列过滤正确、双向高亮信号连通
  - `scripts/healthcheck.py` 加第 9 项「实时预览 + 数据源 Tab 功能正常」

  **拆分推进建议**（按 T-x 模式逐步交付，每步一个 commit）：
  - L-1 布局骨架 → L-2 渲染管线 → L-3 参数面板 → L-4 数据源 Tab → L-5 测试收尾

  **不在本轮范围（登记 P1.5）**：
  - 完整可视化 curves 编辑器（仍走 T-4 遗留任务）
  - 实时预览的"撤销/重做"
  - 数据源 Tab 的列编辑（只读展示已够用）

### P2：旧代码清理

- ~~项目更名 `civil-auto-workspace` → `civ-core`（中文名：`筑核`）~~ ✅ 完成（`a6fe1f9`，2026-05-08）
- `io/` → `infra_io/`
- 消除 41 个 pyright 报错（`body_format.py`、`table_format.py`、`sort_photos.py`、`renumber_photos.py`）
- 删除 `02_Core/`、`04_Config/`、`99_old_code/`
- 删除 `tests/test_cross_ref_fix.py`（引用旧路径 `civ_core.models.schema`，目前 pyproject.toml 已默认 ignore；02_Core 全迁完后整文件删除）

### P3：新工具接入（工具数 > 1 时启用）

`word2pdf`、`auto_filler`、`bracket_normalize`

### P4：插件化架构（工具数 > 3 时启用）

动态加载、工具注册表、数据链路联动

-----

## 🧠 关键架构决策记录

|决策           |内容                                                   |原因                     |
|-------------|-----------------------------------------------------|-----------------------|
|预设 vs 模板     |统一叫”预设（preset）”，禁叫”模板”                               |本项目提供的是预设配置，不是空白模板框架   |
|双路径预设        |系统在 `presets/`，用户在 `~/.civ-core/presets/`|防止软件更新覆盖用户数据           |
|DEV_MODE     |`dev.enabled=true` 时用户预设写入 `tests/fixtures/presets/` |测试数据留仓库管理，打包不带 `tests/`|
|`presets/` 只读|程序运行时禁止写入                                            |静态资源原则，开发者通过 git 维护    |
|预设 UI 分区     |系统预设（🔒只读）与我的预设（✏️可编辑）视觉分区                             |避免用户误操作                |
|用户新建预设       |支持从零新建，不强制复制系统预设                                     |用户可能有完全自定义的需求          |
|文档分层         |CLAUDE.md（用户维护，规则）+ PROGRESS.md（AI 维护，状态）            |职责分离，节省 token          |

-----

## 🗂️ 会话历史

> 当本节超过 50 条记录或文件总长超过 800 行时，归档到 `PROGRESS_ARCHIVE.md`，本节只保留最近 10 条。

### [2026-05-08] 项目更名 civil-auto-workspace → civ-core（筑核）

**完成内容：**
- `git mv src/civil_auto/ → src/civ_core/`（保留历史）
- 全量替换 5 种字符串变体，共 53 个文件：`civil_auto`→`civ_core`、`civil-auto-workspace`→`civ-core`、`Civil_Auto_Workspace`→`civ-core`、`.civil_auto_workspace`→`.civ-core`、`CivilAuto[Error]`→`CivCore[Error]`
- `pyproject.toml` `name`/`scripts`/`package-data` 同步；`uv.lock` 重生成；`uv sync` 重装
- README 标题改成「筑核 (civ-core) v0.2.3-dev」；config.toml/healthcheck/setup_env.bat 横幅同步
- 校验：181 测试通过、ruff 通过、healthcheck 8/8

**涉及文件：** 53 个（全部代码、测试、脚本、文档、配置；详见 `git show a6fe1f9 --stat`）

**遗留问题：**
- GitHub 端仓库名仍是 `Civil-Auto-Workspace`（push 通过 301 重定向走通），需用户手动改名为 `civ-core`
- 本地父目录 `D:\CodeProjects\Civil_Auto_Workspace` 仍未改，需用户在会话结束后 `Rename-Item ... civ-core` + 删 `.venv` + `uv sync`
- Qt QSettings applicationName 已改 `CivilAuto`→`CivCore`，下次启动 GUI 窗口几何/三栏宽度会回到默认一次（无害）

**下一步：** 等用户完成 GitHub 重命名 + 本地目录重命名 + 在新路径重开会话；然后 `git remote set-url origin git@github.com:ZGQ2001/civ-core.git` 收尾，再对齐 P1 子任务

-----

<!-- 新会话记录追加模板：

### [YYYY-MM-DD] 标题

**完成内容：**
-

**涉及文件：**
-

**遗留问题：**
-

**下一步：**

-->