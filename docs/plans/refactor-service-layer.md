# Refactor Plan: Service Layer for plot_curves

**Author:** Cecilia  
**Date:** 2026-05-25  
**Scope:** `api/handlers/plot_curves.py` only（其余 handler 在往 C# 迁移，不碰）

## 问题

`plot_curves.py` handler 是目前 Python sidecar 唯一保留的业务模块（matplotlib 无可替代），但耦合有问题：

```
api/handlers/plot_curves.py
  ├── from civ_core.core.plot_curves import ...         ← ✅ 正确：handler → core
  ├── from civ_core.infra_io.preset_manager import ...  ← ⚠ 4 处 lazy import
  ├── from civ_core.infra_io.excel_reader import ...    ← ⚠ 3 处 lazy import
  └── from civ_core.infra_io.chart_writer import ...    ← ⚠ 2 处 lazy import
```

每个 handler 函数体内有自己的 `from civ_core.infra_io.xxx import ...`。一共 9 处散落在 7 个函数里。mock IO 做测试要 monkeypatch 9 个点。

**且 CLAUDE.md 明确要求**：`api/handlers/ 禁直接做计算 → 调 core/`。虽然没明说"禁直接调 infra_io"，但依赖方向 `frontend → Tauri → sidecar → core/infra_io/domain` 里 handler 调 infra_io 是允许的（它是 sidecar 边界）。问题不在方向，在**散落**。

## 方案

加一层 `services/plot_curves_service.py`，集中所有 IO 导入：

```
api/handlers/plot_curves.py
  └── from civ_core.services.plot_curves_service import ...  ← 1 处 top-level import

services/plot_curves_service.py
  ├── from civ_core.infra_io.preset_manager import ...  ← 集中在此
  ├── from civ_core.infra_io.excel_reader import ...
  └── from civ_core.infra_io.chart_writer import ...
```

改动量：新建 2 个文件，改 1 个文件。零行为变更。每步独立 commit，跑测试验证。

---

## Step 1 — 新建 `services/__init__.py`

```
mkdir src/civ_core/services
```

```python
"""services：业务服务层 — API handlers 和 infra_io 之间的薄 facade。

本层不包含业务逻辑（那是 core/ 的职责），纯做 IO 导入集中 + 类型适配。
当前只有 plot_curves_service，因为其余 handler 在往 C# sidecar 迁移。

依赖方向：handler → service → infra_io
"""
```

验证：`uv run python -c "from civ_core.services import plot_curves_service"` 应该报 `ModuleNotFoundError`（还没建）

commit: `refactor: add services package init`

---

## Step 2 — 新建 `services/plot_curves_service.py`

```python
"""plot_curves service：集中 plot_curves handler 所需的 infra_io 导入。

本模块不包含任何业务逻辑。它只是把散落在 api/handlers/plot_curves.py
各个函数里的 lazy import 集中到一个地方。
"""

from __future__ import annotations

from civ_core.infra_io.chart_writer import render_plot_to_bytes
from civ_core.infra_io.excel_reader import get_column_headers, read_rows, read_sheet_names
from civ_core.infra_io.preset_manager import (
    PresetSource,
    copy_system_to_user,
    delete_user_preset,
    load_merged_presets,
    rename_user_preset,
    save_user_preset,
)

__all__ = [
    # preset operations
    "PresetSource",
    "copy_system_to_user",
    "delete_user_preset",
    "load_merged_presets",
    "rename_user_preset",
    "save_user_preset",
    # excel operations
    "get_column_headers",
    "read_rows",
    "read_sheet_names",
    # chart operations
    "render_plot_to_bytes",
]
```

验证：`uv run python -c "from civ_core.services.plot_curves_service import load_merged_presets; print(type(load_merged_presets))"`

commit: `refactor: add plot_curves_service with centralized IO imports`

---

## Step 3 — 改 `api/handlers/plot_curves.py`

**顶部新增一个 import**（接在现有 `from civ_core.core.plot_curves import ...` 后面）：

```python
from civ_core.services.plot_curves_service import (
    PresetSource,
    copy_system_to_user,
    delete_user_preset,
    get_column_headers,
    load_merged_presets,
    read_rows,
    read_sheet_names,
    rename_user_preset,
    render_plot_to_bytes,
    save_user_preset,
)
```

**删掉 4 处函数体内的 lazy import：**

| 函数 | 删掉的行 |
|------|---------|
| `list_presets()` | `from civ_core.infra_io.preset_manager import PresetSource, load_merged_presets` |
| `list_sheets()` | `from civ_core.infra_io.excel_reader import read_sheet_names` |
| `list_headers()` | `from civ_core.infra_io.excel_reader import get_column_headers` |
| `render_preview()` | `from civ_core.infra_io.chart_writer import render_plot_to_bytes` 和 `from civ_core.infra_io.excel_reader import read_rows` |
| `save_preset()` | `from civ_core.infra_io.preset_manager import save_user_preset` |
| `delete_preset()` | `from civ_core.infra_io.preset_manager import delete_user_preset` |
| `rename_preset()` | `from civ_core.infra_io.preset_manager import rename_user_preset` |
| `copy_preset()` | `from civ_core.infra_io.preset_manager import copy_system_to_user` |

验证：`uv run pytest tests/ -v -k "plot_curves" --tb=short`

commit: `refactor: rewire plot_curves handler to services layer`

---

## Before / After

```
BEFORE                              AFTER
======                              =====
api/handlers/plot_curves.py         api/handlers/plot_curves.py
  ├── 1 top-level import (core)       ├── 1 top-level import (core)
  └── 4 lazy imports (infra_io)       └── 1 top-level import (services)
      scattered in 7 functions            ↓
                                      services/plot_curves_service.py
                                        ├── preset_manager
                                        ├── excel_reader
                                        └── chart_writer
```

- **Handler fan-out**: 4 infra_io modules → 1 service module
- **Mock surface**: 9 scattered points → 1 module
- **新增文件**: 2
- **修改文件**: 1
- **行为变更**: 零
