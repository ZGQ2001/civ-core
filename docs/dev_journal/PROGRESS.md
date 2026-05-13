# 开发日志

> 本文件由 AI 维护，用户可读可改。 每次任务结束后，AI 负责更新此文档（表述 AI 友好） 。
> **AI 启动时只需读”顶部摘要”区段**即可知道做什么。

-----

## 📌 顶部摘要（必读）

**当前状态：** P1 + P1.5-Step1/2/3「点交互闭环」已交付（2026-05-13，commits `d81df09`/`1750f25`/`1fb24ce`/`31f33d4`/`e003b5c`）。**295 测试通过**（+38 新覆盖单行切换 / 叠加渲染 / hit-test 反算 / hover 信号）；ruff 0；healthcheck 9 项全 ✅。

plot_curves 模块功能闭环：
- 左栏：QScrollArea 包六分组风琴参数面板（预设选择 / 数据源(含 sheet) / 曲线定义 / 坐标轴 / 样式(含 X/Y 对数刻度) / 输出）
- 右栏：垂直 QSplitter [预览顶部工具栏(▶ 生成全部曲线 PNG + **☑️ 叠加对比**) + 实时预览图 / 底栏 Tab(日志 + 数据源)]
- 曲线编辑器：ComboBox 单行选曲线 + 5 按钮工具栏；按"基础 / 样式 / 数据点"分子段；4 种图类型（折线/散点/柱状/阶梯）；marker 显示「■ 方块」等人话
- **预览 ↔ 数据源双向联动**：点表格行 → 预览切到该行（单行）或高亮该根（叠加）；叠加模式下 hover 任一曲线 → 表格自动滚到对应行

**当前任务：** 无 in-progress。P1.5-Step1/2/3 已完成；可选 Step 4（单行 hover tooltip）未做。

**下一步（候选，等用户拍板）：**
1. **P1.5 剩余项**：① 单行模式 hover tooltip（X 列名/值 + Y 列名/值，使用频率低，建议跳过）；② 实时预览的撤销/重做；③ CurvesEditor 的"图形化拖点"；④ 双 Y 轴 / 误差棒图等更多土木图类型
2. **P2（旧代码清理）**：`io/` → `infra_io/` 完成（部分已迁），消除 41 个 pyright 报错（`body_format.py` / `table_format.py` / `sort_photos.py` / `renumber_photos.py`），删除 `02_Core/` / `04_Config/` / `99_old_code/` / `tests/test_cross_ref_fix.py`；旧的 `preset_list.py` / `preset_form_panel.py` / `preview_pane.py` 也归 P2（L-3b 已不再使用，但还未删）
3. **P3（新工具接入）**：`word2pdf` / `auto_filler` / `bracket_normalize` 三个工具

**遗留问题：**
- `tests/test_cross_ref_fix.py` 引用旧的 `civ_core.models.schema`，已知 stale，已写到 pyproject.toml addopts 默认 ignore（待 02_Core 整体迁移完成后删除）
- 41 个 pyright 报错全在未迁移的旧代码中，新代码零报错
- 旧 Qt QSettings 键名（applicationName=`CivilAuto`）已废，下次启动 GUI 两栏宽度 / 窗口几何会回到默认一次
- 旧用户存的三栏 splitter_sizes（list[3]）会在首次启动被识别为长度异常 → 回退默认 [600, 400]（一次性丢弃，后续拖动即覆盖）
- `preset_list.py` / `preset_form_panel.py` / `preview_pane.py` 三个旧组件已不被 view 使用但暂留（test_preset_list_buttons / test_preset_form_panel / test_preview_pane 还在测它们 + healthcheck 第 7 项仍依赖 PreviewPane）；P2 阶段一并清理

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
- ~~预设编辑器迁移（`old_code/02_Core/curve_template_editor.py`，673 行 tkinter）~~ → **合并入下方 L-3a**（2026-05-08 与用户对齐方案 B：避免先在 Pivot Tab 实装再搬运到风琴面板）
- **P1/UI 重构：双栏布局 + 实时预览 + 数据源 Tab + curves 可视化编辑器（完成 plot_curves 模块可用性交付）**

  **目标**：把当前"三栏 + 切 Tab"的形态改成"左控右图 + 底栏多 Tab"，参数改完即时看到曲线变化，土木使用者直接照业务流程从上到下填表即可出图。

  **L-1：布局重构（三栏 → 两栏）**
  - 删除 `plot_center_pane.py` 的 Pivot+QStackedWidget 双 Tab 结构
  - 主视图改为 QSplitter 水平两栏：
    - **右栏（实时预览区）**：单图大图渲染，参数变化后自动重绘当前选中预设的代表数据；保留缩略图（多数据/批量出图时）
    - **左栏（参数面板）**：风琴式折叠（QToolBox 或 qfluentwidgets `ExpandLayout`+`SettingCardGroup`）
  - QSettings 持久化键名沿用现有 `splitter_sizes`，但维度从 3 → 2；首次启动给安全默认值（如 `[600, 400]`）
  - 涉及文件：`ui/views/plot_curves_view.py`、`ui/components/plot_center_pane.py`（删除或改造）

  **L-2：实时渲染管线（防抖 + DataFrame 缓存）**
  - 新建 `ui/components/live_preview_pane.py`：`set_preset(entry)` / `set_data_source(path)` / `request_redraw()`，内部用 `QTimer.singleShot(300ms)` 做防抖，多次 `valueChanged` 合并成一次重绘
  - 新建 `core/data_cache.py`：`ExcelDataCache` 单例，按 `(path, mtime)` 缓存 DataFrame（实际用 `dict[str, list[dict]]`，遵守 CLAUDE.md 禁 pandas 约定，存 openpyxl 读出的纯 dict 列表）；切预设时只重读映射规则不重读 Excel
  - 参数面板每个控件的 `valueChanged` / `editingFinished` → 发 `preset_param_changed(field, value)` → view 层节流后调 `live_preview_pane.request_redraw()`
  - 渲染走 worker 线程（沿用现有 `core.plot_curves`），但出图改成"渲到内存 BytesIO → QPixmap"，避免反复落盘
  - 多数据/批量出图按钮单独保留（沿用旧的 worker→PNG 流程）

  **L-3：参数面板风琴式重排**（拆 L-3a + L-3b 两步交付）

  - **L-3a：curves 可视化编辑器**（吸收原"预设编辑器迁移"任务）
    - 参考实现：`old_code/02_Core/curve_template_editor.py`（tkinter 673 行，含完整业务逻辑）
    - 新建 `ui/components/curves_editor.py`：
      - 上半：曲线列表（QListWidget）+ 右侧 `[+ 加曲线] [复制] [删除] [上移] [下移]`
      - 下半（选中曲线时显示）：name LineEdit / color 调色板按钮（弹 QColorDialog，支持 6 个常用色快选）/ marker QComboBox（`s o ^ v D x * +`）/ linewidth + markersize 用 L-3b 的滑块输入组合 / points 子表格（fixed_axis 单选 x/y、fixed_value DoubleSpinBox、var_column QComboBox 联动 Excel 表头）
    - Excel 表头挂载：复用 L-2 的 `ExcelDataCache`，从当前选中的数据源 Excel 读出表头列表喂给 var_column 的 ComboBox（不挂载时退化为可编辑 LineEdit）
    - 与 `preset_form_panel.py` 的 curves JSON 文本框替换：`current_data()` 返回的 curves 字段从文本解析改为编辑器序列化结果
    - 测试：`tests/test_curves_editor.py`（增删/重排曲线、点序列编辑、Excel 表头联动、序列化往返）

  - **L-3b：风琴面板外壳 + 其它分组**
    - 新建 `ui/components/preset_accordion_panel.py`，按土木出图业务流程分组（自上而下）：
      1. **预设选择**（永远置顶不可折叠）：QComboBox 下拉列表 + 「最近使用」的 3 个置顶项（QSettings 存 `recent_presets` 字符串列表）+ 列表底部 `[+新建] [复制] [删除]` 三按钮
      2. **数据源**：Excel 路径 + 表头行号 + ID 列名
      3. **曲线定义**（curves）：装 L-3a 做好的 `CurvesEditor`
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
  - L-1 布局骨架 → L-2 渲染管线 → **L-3a curves 编辑器 → L-3b 风琴外壳** → L-4 数据源 Tab → L-5 测试收尾

  **不在本轮范围（登记 P1.5）**：
  - 实时预览的"撤销/重做"
  - 数据源 Tab 的列编辑（只读展示已够用）
  - curves 编辑器的"图形化拖点"（先做表格式编辑，拖点交互优先级最低）

  **路径校正备注**：第 248 行旧文本里 `old_code_02_Core/curve_template_editor.py` 是渲染层显示问题，磁盘真实路径 `old_code/02_Core/curve_template_editor.py`

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

### [2026-05-12] P1 实跑反馈 + UX 重构 + 多图类型支持

实际跑 GUI 后用户给出 13 项整改 + 多个增强要求，按一个大方向 + 多次微调推进：

**主体 UX 重构（commit `8101dc3`）**
- 主水平 splitter + 右栏垂直 splitter：底栏 Tab 不再横跨整宽，
  只在右栏下方占位；左栏参数面板独享全高
- 预览顶部工具栏取代底部 action_bar：生成按钮紧邻预览图，
  文案"▶ 生成全部曲线 PNG"
- 右栏垂直比例持久化新键 `plot_curves/right_splitter_sizes`
- PresetAccordionPanel 包 QScrollArea：超出时垂直滚动
- 末尾 addStretch(1) 推所有分组贴顶（修原 addStretch(0) 无效）
- 分组 SizePolicy 改 Maximum：折叠时只占标题高度
- 数据源分组新增 sheet ComboBox：选 Excel 后自动 read_sheet_names；
  data_source_changed 信号 arity 升级 Signal(object, object) = (path, sheet)
- 长字段（Excel 路径 / 输出目录）改"标签独占一行 + 控件另一行"
- Sheet + 表头行号用 QGridLayout 2 列横向
- 坐标轴 X/Y 拆两块；输出分组所有字段纵向标签+控件
- CurvesEditor 删除 _color_indicator 大色块；快选按钮加 3px 黑边高亮当前色
- _points_table.setMinimumHeight(200)
- LivePreviewPane 去 minimum size 360x220；LogPanel 去边框去 margin

**CurvesEditor 列表 → ComboBox（commit `ff71474`）**
- QListWidget 大块列表 → ComboBox 单行下拉（与"预设选择"统一）
  节省约 140px 垂直空间
- 删除 `item.setForeground(QColor(curve_color))` 强染色，解决深色主题
  下蓝字+黑底对比度差
- 曲线颜色用 12×12 QIcon 色块装饰 ComboBox item，文字保留主题色
- 工具按钮 (+ ⧉ × ↑ ↓) 改横向同行
- 修正 qfluentwidgets.ComboBox.addItem(text, icon=...) 参数顺序

**按钮文字可见 + 语义澄清（commit `85a3d7b`）**
- ToolButton 默认 IconOnly → QPushButton + setFixedWidth(32) 符号可见
- 加显式"曲线"标签 + 编辑器顶部提示文字「下方为「当前预设里的曲线」
  —— 新增/删除等操作只影响当前预设」澄清预设/曲线父子语义
- 工具按钮 tooltip 强调"仅影响当前预设"

**多图类型 + marker 人话 + 对数刻度（commit `4afacff`）**
- CurveSeries.plot_type 字段，4 种：line / scatter / bar / step
  chart_writer._draw_series 按 type 调度到 ax.plot/scatter/bar/step
- marker ComboBox 显示「■ 方块」「● 圆」「▲ 上三角」等人话，
  matplotlib code 通过 userData 携带；存盘仍是 "s" 等 code
- CurvesEditor 内部按"基础 / 样式 / 数据点"三组小标题区隔
- AxisSpec.log 字段；「样式」分组新增 X/Y 对数刻度 CheckBox；
  chart_writer 处理 ax.set_xscale/yscale("log")
- PlotJob.grid / legend_loc 字段；preset.style.grid / style.legend
  → chart_writer 直接读 job 字段（job 优先于参数）
- 老预设缺新字段时默认 line / grid=True / log=False（向后兼容）

**CI 测试时序修复（本次）**
- tests/test_live_preview_pane.py::test_pending_path_followup_render
  在 CI 上偶发失败：runs+=1 后到 ready 信号回主线程之间有跨线程
  延迟，第一个 assert 通过时 _is_rendering 可能还没复位
- 修复：在断言 _is_rendering=False 前用 qtbot.waitUntil 多等一轮

**累计验收：244 passed（181 → 237 → 244）/ ruff 0 / healthcheck 9/9 ✅**

**涉及文件：**
- src/civ_core/domain/schema.py（CurveSeries.plot_type、AxisSpec.log、PlotJob.grid/legend_loc）
- src/civ_core/core/plot_curves.py（透传 plot_type / style.* 到 PlotJob）
- src/civ_core/infra_io/chart_writer.py（_draw_series 按 type 调度 + 对数刻度 + 图级样式）
- src/civ_core/ui/components/{preset_accordion_panel,curves_editor,live_preview_pane,log_panel}.py
- src/civ_core/ui/windows/plot_curves_view.py（主水平 + 右栏垂直 splitter + 预览顶工具栏）
- tests/{test_curves_editor,test_chart_writer_bytes,test_preset_accordion_panel,test_splitter_persistence,test_live_preview_pane}.py

**遗留（→ P1.5）：**
- 鼠标悬停曲线点 → 表格联动（需 PNG 坐标反向映射 + hit-testing worker）
- highlight_row 渲染时图上突出标记
- 实时预览的撤销/重做
- 双 Y 轴 / 误差棒图等更多图类型

### [2026-05-12] P1/UI 重构 L-1 → L-5 全部交付

**完成内容：**

**L-1（commit `72d9585`）三栏 → 两栏 QSplitter 骨架**
- 删除 `plot_center_pane.py` + `test_plot_center_pane.py`
- 新增占位 `live_preview_pane.py` / `preset_accordion_panel.py`
- `plot_curves_view.py` 改两栏：左 PresetAccordionPanel / 右 LivePreviewPane，默认 sizes `[600, 400]`
- `_restore_splitter_sizes` 长度校验从 3 改为 2，老用户的 list[3] 会被识别为损坏 → 回退默认（一次性丢弃）
- `_validate_preset_form` 保留为纯静态方法（L-3b save flow 仍要用，19 个测试用例覆盖）
- 测试 176 → ruff 0 → healthcheck 8 项全 ✅

**L-2（commit `d23eba7`）实时渲染管线：防抖 + 缓存 + BytesIO 渲染**
- `core/data_cache.py` `ExcelDataCache` 单例：按 `(resolved_path, sheet, header_row, mtime_ns)` 缓存 `read_rows` 结果；mtime 自动失效
- `infra_io/chart_writer.py` 抽 `_configure_axes` + 新增 `render_plot_to_bytes`（不走 atomic_writer，dpi 默认 100，渲到 `BytesIO`）
- `live_preview_pane.py` 真实实装：
  - 接口 `set_preset` / `set_data_source` / `request_redraw`
  - `QTimer.singleShot(300ms)` 防抖；连点滑块合并成一次重绘
  - Worker 串行（pyplot 全局状态多线程不安全）；pending 兜底 last-write-wins
  - generation token 丢弃过期 worker 结果
  - 失败友善降级：缺数据源 / 缺预设 / 列名不匹配 → QLabel 提示
- 测试 +17 → 193

**L-3a（commit `b83d581`）CurvesEditor 曲线可视化编辑器**
- 新建 `ui/components/curves_editor.py`（迁移并精简 `old_code/02_Core/curve_template_editor.py` 中的曲线编辑部分；模板列表归 L-3b）
- 组件结构：上半 QListWidget + 工具栏 `[+ ⧉ × ↑ ↓]`；下半 name / color / marker / linewidth / markersize + 点序列 QTableWidget
- 颜色：6 个快选 + QColorDialog；marker ComboBox（s o ^ v D x * +）；删除曲线 MessageBox 二次确认
- Excel 表头联动：`set_excel_headers` 后 var_column 由 `QLineEdit` 升级为 `qfluentwidgets.ComboBox`
- 深拷贝边界：`set_curves` / `curves()` 双向深拷贝，外部 mutate 不污染编辑器
- `changed` 信号：编辑后发出；`_render_form` 用 `_suppress_signals` 抑制误发
- 测试 +17 → 210

**L-3b（commit `9949352`）PresetAccordionPanel 六分组 + view 实时联动**
- 新建 `ui/components/preset_accordion_panel.py`，六分组自上而下：
  1. 预设选择（不可折叠）：ComboBox 含最近使用「★」置顶 + `[+新建/复制/删除/保存]`
  2. 数据源：Excel 路径 / 表头行号 / 输出目录
  3. 曲线定义：装 L-3a CurvesEditor
  4. 坐标轴：X/Y 标签 + `_RangeTrio`（min/max/step + 启用开关）
  5. 样式：网格 + 图例位置
  6. 输出：filename_template / title_template / DPI（`_SliderInputRow` 滑块+输入）/ 标识列名
- 私有控件 `_CollapsibleSection`（自写折叠分组）/ `_SliderInputRow` / `_RangeTrio`
- 信号 `preset_changed(dict)` / `data_source_changed(object)` / `request_redraw_signal()`
- `current_preset_data()` / `current_run_settings()` 聚合 form 字段
- 最近使用预设 5 条 QSettings 滚动列表（去重 + 提前）；`_make_settings` 工厂方法供测试 monkeypatch
- 系统预设禁删（MessageBox 提示）；用户预设删除走 preset_manager + 二次确认
- view 接线：preset_changed → live_preview.set_preset；data_source_changed → live_preview.set_data_source；request_redraw_signal → live_preview.request_redraw；`_current_run_settings` 改从面板取真实值
- 测试 +12 → 222

**L-4（commit `ed02de1`，与 L-5 合并）底栏 Tab 面板 + 简化双向高亮**
- 新建 `ui/components/data_source_pane.py`：QTableView + QStandardItemModel，按 `id_column + curves[*].points[*].var_column` 去重收齐显示列，preset 缺时兜底前 3 列；点击行 emit `row_highlighted(int)`；`highlight_row` 反向调用用 `_suppress_emit` 防回路；None/NaN 单元格渲染为空
- 新建 `ui/components/bottom_tab_panel.py`：LogPanel + DataSourcePane 整合到 QStackedWidget；工具栏整体 toggle + Pivot 切换；LogPanel 自身 toggle 按钮隐藏避免双重折叠
- `live_preview_pane.py` 新增 `highlight_row(idx)` 占位实装（仅记内部索引 + 更新提示文字，图上画突出标记留 P1.5）
- `plot_curves_view.py`：LogPanel 替换为 BottomTabPanel（保留 `view.log_panel` 别名向后兼容）；新增 `_refresh_data_source_pane`（从 ExcelDataCache 拿 rows 喂表格）；折叠态持久化 QSettings 键 `plot_curves/bottom_panel_collapsed`
- 简化部分：「鼠标悬停曲线点 → 表格高亮」未做，登记到 P1.5（需要 PNG 坐标反向映射 + 单独的 hit-testing worker）

**L-5（与 L-4 合并到 commit `ed02de1`）测试 + healthcheck 收尾**
- `tests/test_data_source_pane.py` 新增 9 项：列过滤 / 兜底 / 去重 / 行选中信号 / 反向高亮防回路 / 越界 / clear / None NaN
- `scripts/healthcheck.py` 新增第 9 项 `_check_bottom_tab_panel`：列过滤 round-trip + Tab 切换 + 折叠态切换
- `_check_gui_constructible` 子组件清单同步：preset_accordion_panel / live_preview_pane / bottom_panel / data_source_pane
- 测试 +9 → 231

**累计变化：**
- 测试：181 → 231（+50；含 L-2 +17 / L-3a +17 / L-3b +12 / L-5 +9，扣除 L-1 删的 5 个 test_plot_center_pane）
- healthcheck：8 → 9 项（新增"底栏 Tab 面板"）
- 新增模块：`core/data_cache.py` / `ui/components/{curves_editor,preset_accordion_panel,live_preview_pane(重写),data_source_pane,bottom_tab_panel}.py`
- 删除模块：`ui/components/plot_center_pane.py` + 对应测试
- 文件改动：`infra_io/chart_writer.py`（抽 _configure_axes + render_plot_to_bytes）/ `scripts/healthcheck.py`（第 5 / 9 项）/ `ui/windows/plot_curves_view.py`（两栏 + L-4 接线）

**涉及文件：**
- 新增：`src/civ_core/core/data_cache.py`
- 新增：`src/civ_core/ui/components/{live_preview_pane,preset_accordion_panel,curves_editor,data_source_pane,bottom_tab_panel}.py`
- 新增：`tests/{test_data_cache,test_chart_writer_bytes,test_live_preview_pane,test_curves_editor,test_preset_accordion_panel,test_data_source_pane}.py`
- 修改：`src/civ_core/infra_io/chart_writer.py` / `src/civ_core/ui/windows/plot_curves_view.py` / `scripts/healthcheck.py` / `tests/test_splitter_persistence.py`
- 删除：`src/civ_core/ui/components/plot_center_pane.py` / `tests/test_plot_center_pane.py`

**遗留问题（→ P1.5）：**
- 鼠标悬停曲线点 → 表格滚到该行：需要 PNG → 数据坐标反向映射 + 单独的 hit-testing worker（与已登记的"图形化拖点"同类）
- LivePreviewPane.highlight_row 当前只更新提示文字，图上画突出标记的渲染部分
- 实时预览的"撤销/重做"
- CurvesEditor 的"图形化拖点"

**下一步（下次会话直接接续）：**
- 待用户拍板：① P1.5 收尾 / ② P2 旧代码清理（含删 `preset_list.py` / `preset_form_panel.py` / `preview_pane.py` 三个 view 已不用的旧组件 + healthcheck 第 7 项 PreviewPane → DataSourcePane 替换）/ ③ P3 新工具接入

### [2026-05-08] P1/UI 重构计划落定 + 预设编辑器迁移合并入 L-3a

**完成内容：**
- 与用户对齐 P1/UI 重构整体计划（L-1 布局重构 / L-2 实时渲染 + DataFrame 缓存 / L-3a curves 可视化编辑器 / L-3b 风琴面板外壳 / L-4 底栏数据源 Tab + 双向高亮 / L-5 测试 + healthcheck 第 9 项）
- 决策合并：原 P1「预设编辑器迁移」（针对 `old_code/02_Core/curve_template_editor.py` 673 行 tkinter）作为独立任务**取消**，吸收为 L-3a 子步——理由：若先在现有 `preset_form_panel.py`（中栏 Pivot 第二 Tab）实装可视化编辑器，L-1 拆三栏时还要整体搬到 L-3b 风琴面板的「曲线定义」分组里，等于做两遍
- PROGRESS.md 顶部摘要、P1 待办积压区、L-3 章节均同步更新；下次会话直接从 L-1 起步

**涉及文件：**
- `docs/dev_journal/PROGRESS.md`（仅本文件）

**遗留问题：**
- 无（L-1 起步前不需要任何前置准备；CLAUDE.md 工作流照常：先 pytest 拦截边界 → 业务代码 → ruff → healthcheck → commit）

**下一步（下次会话直接接续）：**
1. L-1 Step 1：拆 `plot_curves_view.py` 三栏 → 两栏 QSplitter（左：占位 LivePreviewPane / 右：占位 PresetAccordionPanel），splitter_sizes 维度 3→2，迁移 QSettings 键名
2. L-1 Step 2：删除 `plot_center_pane.py`（Pivot 双 Tab 不再需要）；旧的 `preset_list.py` + `preset_form_panel.py` 暂留作 L-3b 时拆解吸收
3. L-1 Step 3：测试 + healthcheck，验收

-----

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