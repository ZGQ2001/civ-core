## 项目说明

由无编程经验的土木检测行业从业人员利用AI辅助编程的土木工程检测行业内业报告自动化辅助工具。  接收Excel/CSV/Word，自动化完成数据格式化、规范评定、图表生成、Word 报告填充、以及其他相关的工具。适配windows系统。
**内部自用，非商业分发。**

-----

## 概念定义

| 术语           | 含义                                                                                                        |
| ------------ | --------------------------------------------------------------------------------------------------------- |
| 配置（config）   | 运行时参数：Excel 路径、输出目录、表头行号等                                                                                 |
| 预设（preset）   | 一组预先定义好的业务参数：曲线轴范围、颜色、阈值等，随程序发布的只读预设，存于 `presets/`，开发者维护，用户自定义的可写预设，存于 `~/.civ-core/presets/` |
| 模版（template） | 结构固定，内容待填充的文件                                                                                             |

---

## 目录构造

| 目录                        | 角色                 | 操作规则                   |
| ------------------------- | ------------------ | ---------------------- |
| `02_Core/`                | 旧版业务逻辑，未io/ui/业务分离 | 参考，待迁移后删除              |
| `src/civ_core/`         | 新架构主目录             | 所有新代码写在这里              |
| `presets/`                | 系统预设（静态只读）         | **禁止程序运行时写入**          |
| `tests/fixtures/presets/` | 开发期测试预设            | 仅 DEV_MODE 下使用，随仓库但不打包 |
| `04_Config/`              | 旧版 JSON 配置         | 参考，待迁移后删除              |
| `05_JSA/`                 | WPS 宏              | 参考，不动                  |
| `06_Report_Template/`     | Word/Excel 报告模板    | 参考，待迁移后删除              |
| `99_old_code/`            | 历史遗存               | 不读、不动、不参考              |

-----
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

## 工作流

1. 会话开始 `git add . && git commit -m "chore: 会话开始检查点"`读取 → `docs/dev_journal/PROGRESS.md` **顶部摘要部分**（需要细节时才读 PROGRESS.md 其余部分）→ 向我报告：当前状态 / 待处理任务 / 下一步具体动作→ 确认本次任务后再动手
2. 单步骤执行 `git add . && git commit -m "feat: 完成 xxx"  # 描述实际内容`
3. 文件的新增/修改 → 必须先编写并运行对应 pytest 拦截边界条件（此时必报错） → 再编写业务代码使其通过 → 运行 ruff check . 拦截规范错误 → 执行 scripts/healthcheck.py 冒烟自检。
4. 会话结束（用户说”好了/结束/下次继续”）追加更新 `PROGRESS.md`
---
## 禁止必须对照表

| 禁止                                                  | 必须                                                                                                    |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| 一次性输出所有代码                                           | 步骤交付，等待验收，通过后继续                                                                                            |
| 无注释，全英文                                             | 必须带中文注释，说明为什么这么做                                                                                      |
| 自行决定规范与代码冲突                                         | 向用户说明                                                                                                 |
| 凭直觉优化                                               | 先profile                                                                                              |
| 错误信息只报错                                             | 用异常 + 错误带上下文                                                                                          |
| `core/` 直接读写文件，`ui/` 调用 openpyxl、python-docx 等 IO 库 | 业务/IO/UI 分离                                                                                           |
| `presets/` 目录程序运行时写入                                | 运行时保持只读状态，修改预设只能修改用户预设                                                                                |
| 模板变量替换、表格批量插入、图片插入使用 COM<br>                        | 用 docxtpl，域代码刷新、目录重建、Word 转 PDF、最终格式精修使用 COM，所有 COM 调用集中在 `infra_io/word_com.py`，`try/finally` 确保进程释放 |
| 引入 `pandas`、`numpy` 、`pydantic` <br> 、`requests`库   | 统一用 dataclass + `__post_init__`，有 ，HTTP 需求时、matplotlib 传递依赖可引用                                        |
| 大文件 / 大数据一次性读如 ： `data = f.read()` 把整个 10G 文件读进内存   | 用 generator / iterator / chunked read ，SQL 用 server-side cursor，pandas 用 chunksize                    |
| Core 函数直接修改 UI 组件状态或弹出 QFileDialog                  | 使用信号（Signal）或回调函数传递进度；IO 路径由外部（UI 或 Config）传入 pathlib.Path 对象                                         |

### 禁止的写法

```python
# ❌                                      ✅
base_dir + "/output/" + f              →  base_dir / "output" / f
except: pass                           →  except Err as e: logger.error(...); raise
threshold = 0.85                       →  config["evaluation"]["threshold"]
subprocess.run(f"python {s}")          →  subprocess.run(["python", str(s)])
def fn(data: dict)                     →  def fn(job: PlotJob)
```
