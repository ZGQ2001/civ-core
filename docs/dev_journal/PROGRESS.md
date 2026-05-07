# 开发日志

> 本文件由 AI 维护，用户可读可改。 每次任务结束后，AI 负责更新此文档（表述 AI 友好） 。
> **AI 启动时只需读”顶部摘要”区段**（前 30 行左右）即可知道做什么，节省 token。

-----

## 📌 顶部摘要（必读）

**当前状态：** 第一阶段（核心层 7 步）+ 第二阶段（UI 层 6 步）全部完成，绘曲线图工具 CLI 和 GUI 双轨可用。

**当前任务：** T-0 命名统一（template → preset），未开始

**下一步：** 执行 T-0，将所有 `template` 命名改为 `preset`

**遗留问题：** 41 个 pyright 报错全在未迁移的旧代码中，新代码零报错

---
### 可用指令（动态更新）

```bash
uv run python -m civil_auto.main                        # 启动 GUI
uv run python -m civil_auto.main --list-templates       # 列出所有预设（T-0 后改为 --list-presets）
uv run python -m civil_auto.main --tool plot_curves \
    --input data/raw/sample.xlsx \
    --template 锚杆荷载-位移曲线 \
    --output data/output/曲线图                          # CLI 出图
```

-----

## 📋 当前任务详情：预设系统完整实现

### T-0：命名统一（先执行）

| 操作    | 旧                                | 新                              |
| ----- | -------------------------------- | ------------------------------ |
| 目录    | `templates/plot_curves/`         | `presets/plot_curves/`         |
| 文件    | `curve_templates.json`           | `curve_presets.json`           |
| 组件    | `ui/components/template_list.py` | `ui/components/preset_list.py` |
| 配置键   | `paths.curve_templates`          | `paths.curve_presets`          |
| UI 文字 | “模板列表”、“当前模板”                    | “预设列表”、“当前预设”                  |
| CLI   | `--list-templates`               | `--list-presets`               |

**验收：** `grep -r "template" src/` 仅剩历史性注释，无代码引用。

-----

### T-1：preset_manager.py（双路径加载 + 深合并）

新建 `infra_io/preset_manager.py`：

```
系统预设（只读）              用户设置（可写）
presets/plot_curves/         ~/.civil_auto_workspace/configs/
└── curve_presets.json       └── curve_configs.json
        ↓                            ↓
        └────── 深合并 ──────────────┘
                    ↓
            运行时预设列表
（同名：用户覆盖系统；异名：追加）
```

**DEV_MODE：**

```toml
# config.toml
[dev]
enabled = true
user_presets_dir = "tests/fixtures/presets"
```

- `dev.enabled = true`：用户预设写入 `tests/fixtures/presets/`（在仓库，git 管理）
- `dev.enabled = false`：用户预设写入 `~/.civil_auto_workspace/presets/`

**硬性要求：**

- 用户目录不存在 → 静默创建
- 用户预设文件不存在 → 用系统预设兜底，不抛异常
- 禁止运行时写入 `presets/`

-----

### T-2：config/loader.py 更新

新增 `user_presets_dir`，根据 `dev.enabled` 自动切换路径。

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