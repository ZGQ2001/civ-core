# 项目宪法

> 本文件是项目稳定不变的规则与约束，由用户维护。  
> 进度、任务、决策见 `docs/dev_journal/PROGRESS.md`（AI 维护）。

-----

## 启动协议（每次新会话必须执行）

1. 读取 `docs/dev_journal/PROGRESS.md` **顶部摘要部分**（约 30 行）
2. 向用户报告：当前状态 / 待处理任务 / 下一步具体动作
3. 等用户确认本次任务后再动手
4. 会话结束（用户说”好了/结束/下次继续”）追加更新 `PROGRESS.md`

只在需要细节时才读 PROGRESS.md 的中部和底部，节省 token。

-----

## 项目是什么

 土木工程内业报告自动化辅助工具（道路桥梁/房屋检测鉴定）。  
接收仪器导出或人为编辑的 Excel/CSV，自动化完成数据格式化、规范评定、图表生成、Word 报告填充、以及其他相关的工具。
**内部自用，非商业分发。**

-----

## 概念定义

| 术语         | 含义                                               |
| ---------- | ------------------------------------------------ |
| 配置（config） | 运行时参数：Excel 路径、输出目录、表头行号等                        |
| 预设（preset） | 一组预先定义好的业务参数：曲线轴范围、颜色、阈值等                        |
| 系统预设       | 随程序发布的只读预设，存于 `presets/`，开发者维护                   |
| 用户预设       | 用户自定义的可写预设，存于 `~/.civil_auto_workspace/presets/` |

**严禁将”预设”、**设置**称为”模板”**——代码、注释、UI 文字、文件名、CLI 参数全部使用 `preset`，用户可自定义的设置使用`config`, 禁用 `template`。

-----

## 各目录的角色

| 目录                        | 角色              | 操作规则                   |
| ------------------------- | --------------- | ---------------------- |
| `02_Core/`                | 旧版业务逻辑          | 只读参考，读懂后用新架构重写         |
| `src/civil_auto/`         | 新架构主目录          | 所有新代码写在这里              |
| `presets/`                | 系统预设（静态只读）      | **禁止程序运行时写入**          |
| `tests/fixtures/presets/` | 开发期测试预设         | 仅 DEV_MODE 下使用，随仓库但不打包 |
| `04_Config/`              | 旧版 JSON 配置      | 只读参考，待迁移后删除            |
| `05_JSA/`                 | WPS 宏           | 不动                     |
| `06_Report_Template/`     | Word/Excel 报告模板 | 历史遗留模版，待迁移             |
| `99_old_code/`            | 历史遗存            | 不读、不动、不参考              |

-----

## 硬性禁止

### 禁止引入的库

- `pandas`、`numpy`（matplotlib 传递依赖除外）
- `pydantic`（统一用 dataclass + `__post_init__`）
- `requests`（无 HTTP 需求时）

### 禁止的写法

```python
# ❌                                      ✅
base_dir + "/output/" + f              →  base_dir / "output" / f
except: pass                           →  except Err as e: logger.error(...); raise
threshold = 0.85                       →  config["evaluation"]["threshold"]
subprocess.run(f"python {s}")          →  subprocess.run(["python", str(s)])
def fn(data: dict)                     →  def fn(job: PlotJob)
```

### 架构红线

- `core/` 不得直接读写文件
- `ui/` 不得调用 openpyxl、python-docx 等 IO 库
- 新代码禁止 `import civil_auto.io.*` 或 `civil_auto.models.*`
- `presets/` 目录禁止程序运行时写入
- 代码、注释、UI 文字禁止使用 `template` 指代预设概念

-----

## 已锁定技术决策

| 维度     | 决策                                                |
| ------ | ------------------------------------------------- |
| Python | 3.12+                                             |
| UI     | PySide6 + qfluentwidgets                          |
| Excel  | openpyxl                                          |
| Word 主 | docxtpl + python-docx                             |
| Word 辅 | pywin32 COM，仅限：域刷新、目录更新、转 PDF、格式精修                |
| 配置     | `config.toml`（读：`tomllib`；写：`tomli-w`）            |
| 数据契约   | `@dataclass` + `__post_init__`（强制执行类型转换与合法性检查）    |
| 日志     | 标准库 `logging`，`ZoneInfo("Asia/Shanghai")`         |
| 路径     | 全部 `pathlib.Path`                                 |
| 文件读写   | 显式 `encoding='utf-8'`输入流（读取仪器数据）先试 UTF-8，失败则转 GBK |
| 类型检查   | Pylance Basic 零红线（新代码）                            |
| 包管理    | `uv`，禁止 `pip install`                             |

-----

## COM 使用约束

**允许：** 域代码刷新、目录重建、Word 转 PDF、最终格式精修  
**禁止：** 模板变量替换（用 docxtpl）、表格批量插入、图片插入  
**封装：** 所有 COM 调用集中在 `infra_io/word_com.py`，`try/finally` 确保进程释放

-----

## 工具链

```bash
uv add <package>        # 安装依赖
uv add --dev <package>  # 安装开发依赖
uv run python ...       # 运行代码
ruff check .            # 代码检查
uv run pytest           # 测试
```

-----

## Git 安全协议

**用户不具备手动修复代码的能力，git 是唯一的回退手段，必须严格执行。**

### 会话开始时

执行一次提交，保存当前干净状态：

```bash
git add . && git commit -m "chore: 会话开始检查点"
```

### 每完成一个步骤并通过验收后

立即提交，再继续下一步：

```bash
git add . && git commit -m "feat: 完成 T-0 命名统一"  # 描述实际内容
```

**禁止连续完成多个步骤后才提交。** 每步一个 commit，粒度不得更大。

### 出现问题需要回退时

告知用户执行：

```bash
git log --oneline -5   # 查看最近提交
git reset --hard <commit_hash>  # 回退到指定提交
```

-----

## 健康检查

项目根目录维护 `scripts/healthcheck.py`，由 Claude Code 负责随功能迭代同步更新。

用户每次验收后运行：

```bash
uv run python scripts/healthcheck.py
```

输出格式为**纯中文通过/失败**，不暴露技术细节：

```
✅ 配置文件加载正常
✅ 系统预设读取正常（共 3 个）
✅ CLI 出图功能正常
✅ GUI 启动正常
❌ 用户预设目录无法创建 → 请检查磁盘权限
```

新增功能时，同步在 `healthcheck.py` 中加入对应检查项。

-----

## 上下文管理

- 单次会话 token 用量接近 40% 时，主动提醒用户开新会话
- 提醒前必须先更新 `PROGRESS.md`，确保进度不丢失
- 新会话开始时用户执行 `/clear` 清除旧上下文

-----

## 交付规范

- 严禁一次性输出所有代码，按步骤交付
- 每个文件交付后等待验收，通过后再继续
- 代码必须带中文注释，说明”为什么这么做”
- 遇到规范与实际代码冲突，停下来说明，不要自行决定
- 每次会话结束必须更新 `docs/dev_journal/PROGRESS.md`