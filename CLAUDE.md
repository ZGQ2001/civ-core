## 项目说明

项目名称 `civ-core` 中文名：`筑核`
由无编程经验的土木检测行业从业人员利用AI辅助编程的土木工程检测行业内业报告自动化辅助工具。  接收Excel/CSV/Word，自动化完成数据格式化、规范评定、图表生成、Word 报告填充、以及其他相关的工具。适配windows系统。
**内部自用，非商业分发。**

---

## 工作流

1. 会话开始 `git add . && git commit -m "chore: 会话开始检查点"`读取 → `docs/dev_journal/PROGRESS.md` **顶部摘要部分**（需要细节时才读 PROGRESS.md 其余部分）→ 向我报告：当前状态 / 待处理任务 / 下一步具体动作→ 确认本次任务后再动手
2. 单步骤执行 `git add . && git commit -m "feat: 完成 xxx"  # 描述实际内容`
3. 文件的新增/修改 → 必须先编写并运行对应 pytest 拦截边界条件（此时必报错） → 再编写业务代码使其通过 → 运行 ruff check . 拦截规范错误 → 执行 scripts/healthcheck.py 冒烟自检。
4. 会话结束（用户说"好了/结束/下次继续"）追加更新 `PROGRESS.md`

---

## 概念定义

| 术语           | 含义                                                                                                        |
| ------------ | --------------------------------------------------------------------------------------------------------- |
| 配置（config）   | 运行时参数：Excel 路径、输出目录、表头行号等                                                                                 |
| 预设（preset）   | 业务参数（曲线轴范围/颜色/阈值等）；系统预设在 `presets/`（只读），用户预设在 `~/.civ-core/presets/`               |
| 模版（template） | 结构固定、内容待填充的 docx/xlsx，存于 `templates/`，与预设系统**完全无关**                                                       |

---

## 目录构造

| 目录                          | 角色                          | 操作规则                                        |
| --------------------------- | --------------------------- | ------------------------------------------- |
| `src/civ_core/domain/`      | 数据契约（dataclass）             | 纯 Python，零外部依赖                              |
| `src/civ_core/core/`        | 业务逻辑                        | 禁止直接读写文件；IO 通过 `infra_io/` 传入               |
| `src/civ_core/infra_io/`    | 文件读写 / COM / 预设管理           | 与 `core/` 解耦；UI 不直接调用                       |
| `src/civ_core/ui/`          | PySide6 界面层                 | 禁止调用 openpyxl / python-docx 等 IO 库          |
| `src/civ_core/configs/`     | 配置加载（`loader.py`）           | `lru_cache` 单例，`AppConfig` frozen          |
| `src/civ_core/utils/`       | 日志 / 异常 / 路径 / COM 入口       | 无业务逻辑，可被任意层引用                               |
| `src/civ_core/apps/`        | 启动胶水（`bootstrap.py`）        | 装配 QApplication + 主窗口                       |
| `presets/`                  | 系统预设（静态只读）                  | **禁止程序运行时写入**                               |
| `tests/fixtures/presets/`   | 开发期测试预设                     | 仅 DEV_MODE 下使用，随仓库但不打包                      |
| `scripts/`                  | 辅助脚本（`healthcheck.py`）      | 每次验收必跑                                      |
| `templates/`                | 报告模板（docx/xlsx 空白模板）        | 不是预设；docxtpl 填充用                            | 
| `docs/civil_kb/`            | 文档资料（Markdown 格式）            | 包含土木工程各种计算公式和规范要求                          |

---

## 架构分层

依赖方向：**UI → Core → Infra IO → Domain → Utils/Configs**，禁止反向 import。

- `domain/` 只放 dataclass + `__post_init__` 校验，零外部依赖
- `core/` 入参/出参全部是 dataclass，禁止 `open/read/write`
- `infra_io/` 是唯一的 IO 边界（Excel/Word COM/预设/原子写）
- `ui/` 只发 Signal、不直接调 IO 库；路径由外部传入

---

## 关键入口

| 模块                              | 职责                                                          |
| ------------------------------- | ----------------------------------------------------------- |
| `domain/schema.py`              | PlotJob / CurveSeries / AxisSpec / PlotRunSettings 四个契约      |
| `core/plot_curves.py`           | Excel → PlotJob 列表 → 批量出图主流程                                |
| `core/data_cache.py`            | `ExcelDataCache` 单例（按 path+sheet+mtime 缓存）                  |
| `infra_io/preset_manager.py`    | 双路径预设加载 + 写入 API（save/delete/copy）                          |
| `infra_io/chart_writer.py`      | `write_plot`（落盘）/ `render_plot_to_bytes`（实时预览用）              |
| `infra_io/file_manager.py`      | `atomic_writer` 上下文管理器                                      |
| `configs/loader.py`             | `load_config()` 唯一入口；frozen dataclass                       |
| `utils/exceptions.py`           | 四档异常基类（见下方）                                                |
| `utils/logger.py`               | `get_logger()` + `QtLogBridge`（跨线程信号桥）                      |
| `utils/word_com.py`             | **所有 COM 调用集中点**，`try/finally` 确保进程释放                       |
| `ui/windows/plot_curves_view.py` | 主视图：左参数面板 + 右实时预览 + 底栏 Tab                                |
| `scripts/healthcheck.py`        | 9 项冒烟检查；退出码 0=全通 / 1=有失败                                   |

---

## 领域模型

```
PlotJob:        title, output_path, x_axis: AxisSpec, y_axis: AxisSpec,
                series: list[CurveSeries], grid, legend_loc
CurveSeries:    name, xs, ys, color(#RGB), marker, linewidth, markersize,
                plot_type ∈ {"line","scatter","bar","step"}
AxisSpec:       label, range=(min,max,step)|None, log: bool
PlotRunSettings:input_path, sheet_name, preset_name, output_dir, header_row
                （UI 绑定对象，允许字段为 None；真正校验在"生成"按钮触发）
```

---

## 预设系统

```
presets/<tool>/curve_presets.json          系统（只读，git 维护）
~/.civ-core/presets/<tool>/...             用户（可写；dev.enabled=true 时改读 tests/fixtures/presets/）
     ↓ load_merged_presets()
PresetEntry 有序列表：系统遍历 → 同名被用户覆盖 → 用户独有项追加
```

写入 API（仅写用户预设，走 `atomic_writer`）：`save_user_preset` / `delete_user_preset` / `copy_system_to_user`
`PresetSource.SYSTEM` 在 UI 显示 🔒（禁删/可复制）；`USER` 显示 ✏️（可编辑/删除）。

---

## 异常体系

四档继承 `CivCoreError`：`ConfigError` / `InputError` / `BusinessError` / `InfraIOError`
具体子类（按需用）：`ColumnNotFoundError` / `EmptyDataError` / `WordHostNotRunning` / `DocumentUnsaved` / `TemplateMissing` / `FileLockedError` / `FileWriteError` / `ComUnavailable`
三段式格式：`[location] cause\n修复建议：hint`（location/hint 可选）

---

## 项目当前阶段（2026-05-14 起锁定）

**模式：维护现有 + 添加新功能**。不再做旧代码迁移大重构 —— `old_code/` / `99_old_code/`、未被引用的旧 UI 组件（`preset_list.py` / `preset_form_panel.py` / `preview_pane.py`）、stale 测试（`tests/test_cross_ref_fix.py`）、41 个 pyright 报错全部就地保留作为参考。

具体规则：
- **新功能** → 直接在 `src/civ_core/` 新架构（domain/core/infra_io/ui）下写，按 CLAUDE.md 的分层 + 工作流
- **维护 / bugfix** → 只动 `src/civ_core/` 当前正在用的代码；遇到旧代码报错 / 警告，不要"顺手"清理，除非用户明确要求
- **删除旧代码** → 必须经用户明确允许（"删 X 文件"）才能动；不主动建议清理
- **测试 / lint** → `pyproject.toml addopts` 已 ignore 已知的 stale 测试，pyright 旧代码红线已知忽略；新代码必须零 ruff / pytest 全过

---

## 已知技术债

绝大部分技术债已就地接受为现状（见上节）。仅记录"有可能影响新功能开发"的活跃项：

- **P1.5-③ 图形化拖点编辑**（推迟到未来）：要做须把渲染从 `Agg → PNG → QLabel` 换成 `FigureCanvasQTAgg`，会改动渲染管线 + 撤销栈 + 预览防抖，归到独立"渲染管线重构"专项
- **P3 剩余工具**：`auto_filler`（待规划）/ `bracket_normalize`（待规划）—— 都是新功能，不依赖旧代码迁移

---

## 已锁定技术决策

| 维度     | 决策                                             |
| ------ | ---------------------------------------------- |
| Python | 3.12+                                          |
| UI     | PySide6 + qfluentwidgets                       |
| Excel  | openpyxl                                       |
| Word 主 | docxtpl + python-docx                          |
| Word 辅 | pywin32 COM，仅限：域刷新、目录更新、转 PDF、格式精修             |
| 配置     | `config.toml`（读：`tomllib`；写：`tomli-w`）         |
| 数据契约   | `@dataclass` + `__post_init__`（强制执行类型转换与合法性检查） |
| 日志     | 标准库 `logging`，`ZoneInfo("Asia/Shanghai")`      |
| 路径     | 全部 `pathlib.Path`                              |
| 文件读写   | 显式 `encoding='utf-8'` ，失败则转 GBK                |
| 类型检查   | Pylance Basic 零红线，ruff                         |
| 包管理    | `uv`，禁止 `pip install`                          |

---

## 工具链

```bash
uv add <package>                          # 安装依赖（禁止 pip install）
uv run python -m civ_core.main            # 启动 GUI
uv run python -m civ_core.main --list-presets    # 列出预设
uv run python -m civ_core.main --tool plot_curves --input <xlsx> --preset <名> --output <dir>
uv run ruff check .                       # lint（每步完成后必跑）
uv run pytest                             # 测试（addopts 已 ignore stale 测试）
uv run python scripts/healthcheck.py      # 9 项冒烟（每次验收必跑）

# DEV_MODE：config.toml → [dev] enabled = true，用户预设改读 tests/fixtures/presets/
```

---
## 禁止必须对照表

| 禁止                                                  | 必须                                                                                                    |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| 无任何通知就开始修改代码                                           | 提出方案，不确定提问，等待验收，通过后继续                                                                                            |
| 无注释，全英文                                             | 必须带中文注释，说明为什么这么做                                                                                      |
| 自行决定规范与代码冲突                                         | 向用户说明                                                                                                 |
| 凭直觉优化                                               | 先profile                                                                                              |
| 错误信息只报错                                             | 用异常 + 错误带上下文                                                                                          |
| `core/` 直接读写文件，`ui/` 调用 openpyxl、python-docx 等 IO 库 | 业务/IO/UI 分离                                                                                           |
| `presets/` 目录程序运行时写入                                | 运行时保持只读状态，修改预设只能修改用户预设                                                                                |
| 模板变量替换、表格批量插入、图片插入使用 COM<br>                        | 用 docxtpl，域代码刷新、目录重建、Word 转 PDF、最终格式精修使用 COM，所有 COM 调用集中在 `utils/word_com.py`，`try/finally` 确保进程释放 |
| 引入 `pandas`、`numpy` 、`pydantic` <br> 、`requests`库   | 统一用 dataclass + `__post_init__`，HTTP 需求时、matplotlib 传递依赖可引用                                          |
| 大文件 / 大数据一次性读如 ： `data = f.read()` 把整个 10G 文件读进内存   | 用 generator / iterator / chunked read ，SQL 用 server-side cursor，pandas 用 chunksize                    |
| Core 函数直接修改 UI 组件状态或弹出 QFileDialog                  | 使用信号（Signal）或回调函数传递进度；IO 路径由外部（UI 或 Config）传入 pathlib.Path 对象                                         |

### 禁止的写法

```python
# ❌                                      ✅
base_dir + "/output/" + f              →  base_dir / "output" / f
except: pass                           →  except Err as e: logger.error(...); raise
threshold = 0.85                       →  config["evaluation"]["threshold"]
subprocess.run(f"python {s}")          →  subprocess.run(["python", str(s)])
def fn(data: dict)                     →  def fn(job: PlotJob)
重复定义同一样式/常量/魔法值            →  唯一源（dataclass / config / 枚举），引用不复制
```
