# 开发日志

> 本文件由 AI 维护，用户可读可改。 每次任务结束后，AI 负责更新此文档（表述 AI 友好） 。
> **AI 启动时只需读”顶部摘要”区段**（前 30 行左右）即可知道做什么，节省 token。

-----

## 📌 顶部摘要（必读）

**当前状态：** T-0 命名统一 + T-1 preset_manager（双路径合并）已完成；50 测试通过。

**当前任务：** T-2 `config/loader.py` 联动收尾（如有），或直接进 T-3 主流程接入

**下一步：** 检查 T-2 是否还有遗漏（loader.py 在 T-1 已加 DevConfig+user_presets_dir，可能 T-2 工作量已被吸收），与用户确认后进 T-3：让 `ui/components/preset_list.py` 改用 `load_merged_presets()` 显示 🔒/✏️ 来源图标

**遗留问题：**
- `tests/test_cross_ref_fix.py` 引用旧的 `civil_auto.models.schema`，已知 stale，跑测试时用 `--ignore` 跳过（已登记到 P2）
- 41 个 pyright 报错全在未迁移的旧代码中，新代码零报错

---
### 可用指令（动态更新）

```bash
uv run python -m civil_auto.main                        # 启动 GUI
uv run python -m civil_auto.main --list-presets         # 列出预设（系统+用户合并）
uv run python -m civil_auto.main --tool plot_curves \
    --input data/raw/sample.xlsx \
    --preset 锚杆荷载-位移曲线 \
    --output data/output/曲线图                          # CLI 出图
uv run python -m pytest --ignore=tests/test_cross_ref_fix.py  # 跑测试（跳过 stale 旧测试）

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
~/.civil_auto_workspace/presets/plot_curves/curve_presets.json   （用户，可写）
            ↓                                  ↓
            └────── 顶层合并 ──────────────────┘
                        ↓
                  PresetEntry 列表
（系统按原序遍历 → 同名被用户覆盖时保留位置且 source=USER → 用户独有的追加到末尾）
```

**dev.enabled 切换（验证通过）：**
- `true`  → 用户预设走 `tests/fixtures/presets/plot_curves/curve_presets.json`（仓库内，git 管理）
- `false` → 用户预设走 `~/.civil_auto_workspace/presets/plot_curves/curve_presets.json`（用户家目录）
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

### T-3：主流程接入

`core/plot_curves.py` 和 `ui/components/preset_list.py` 改用 `load_merged_presets()`。

-----

### T-4：预设管理 UI 重设计（中间面板 Pivot 双 Tab）

```
┌──────────────┬──────────────────────────────────┬──────────────┐
│ 预设列表      │  绘图参数  │  预设设置  ←Pivot   │   预览区     │
│              │                                  │              │
│ 📦 系统预设  │  绘图参数 tab：当前已有内容        │              │
│ 🔒 锚杆荷载  │                                  │              │
│ 🔒 回弹曲线  │  预设设置 tab：                   │              │
│ ──────────── │    预设名称  [_______]            │              │
│ ✏️ 我的预设  │    X 轴标签  [_______]            │              │
│  自定义锚杆  │    Y 轴范围  [min] ~ [max]        │              │
│              │    阈值线    ● 开 [_____]         │              │
│ [+新建][复制]│    曲线颜色  [色块]               │              │
│       [删除] │                                  │              │
│              │  🔒系统预设：只读 [复制为我的预设] │              │
│              │  ✏️我的预设：[保存修改] [重置]    │              │
└──────────────┴──────────────────────────────────┴──────────────┘
```

**交互规则：**

- 单击预设 → 自动切到”预设设置” tab，参数联动刷新
- 系统预设 → 只读 + “复制为我的预设”按钮
- 我的预设 → 可编辑 + “保存修改”和”重置”
- `[+新建]` → 切到”预设设置” tab，字段清空，等待填写

-----

### T-5：测试

- `tests/fixtures/presets/curve_presets.json`（开发测试预设数据）
- `tests/test_preset_manager.py`（覆盖兜底、同名覆盖、异名追加、DEV 路径切换）

-----

## 📦 待办积压

### P1：绘曲线图 GUI 收尾

- QSplitter 宽度记忆（QSettings 持久化）
- 日志面板接入（`QtLogBridge` 已就绪，连 UI 槽）
- 预览区实现（缩略图列表 + 单击放大）
- 预设编辑器迁移（`02_Core/curve_template_editor.py`）

### P2：旧代码清理

- `io/` → `infra_io/`
- 消除 41 个 pyright 报错（`body_format.py`、`table_format.py`、`sort_photos.py`、`renumber_photos.py`）
- 删除 `02_Core/`、`04_Config/`、`99_old_code/`
- 清理 `tests/test_cross_ref_fix.py`（引用旧路径 `civil_auto.models.schema`，目前实际在 `civil_auto.domain.schema`，跑测试要 `--ignore` 跳过）

### P3：新工具接入（工具数 > 1 时启用）

`word2pdf`、`auto_filler`、`bracket_normalize`

### P4：插件化架构（工具数 > 3 时启用）

动态加载、工具注册表、数据链路联动

-----

## 🧠 关键架构决策记录

|决策           |内容                                                   |原因                     |
|-------------|-----------------------------------------------------|-----------------------|
|预设 vs 模板     |统一叫”预设（preset）”，禁叫”模板”                               |本项目提供的是预设配置，不是空白模板框架   |
|双路径预设        |系统在 `presets/`，用户在 `~/.civil_auto_workspace/presets/`|防止软件更新覆盖用户数据           |
|DEV_MODE     |`dev.enabled=true` 时用户预设写入 `tests/fixtures/presets/` |测试数据留仓库管理，打包不带 `tests/`|
|`presets/` 只读|程序运行时禁止写入                                            |静态资源原则，开发者通过 git 维护    |
|预设 UI 分区     |系统预设（🔒只读）与我的预设（✏️可编辑）视觉分区                             |避免用户误操作                |
|用户新建预设       |支持从零新建，不强制复制系统预设                                     |用户可能有完全自定义的需求          |
|文档分层         |CLAUDE.md（用户维护，规则）+ PROGRESS.md（AI 维护，状态）            |职责分离，节省 token          |

-----

## 🗂️ 会话历史

> 当本节超过 50 条记录或文件总长超过 800 行时，归档到 `PROGRESS_ARCHIVE.md`，本节只保留最近 10 条。

-----

### [初始化] 项目基线 + 架构决策

**完成内容：**

- 第一阶段 7 步完成，CLI 可用
- 第二阶段 6 步完成，GUI 绘曲线图全链路跑通
- 确定预设系统架构、命名规范、UI 交互方案
- 完成 CLAUDE.md / PROGRESS.md 职责分层

**遗留问题：** template 旧命名待清理（T-0）

**下一步：** 执行 T-0

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