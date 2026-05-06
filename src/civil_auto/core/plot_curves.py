"""绘曲线图工具核心业务逻辑（纯参数 / 无 IO / 无 UI）。

职责切分（v2.3 总纲）：
  本模块只负责"模板 + 数据行 → PlotJob 列表"的纯计算，以及顶层 orchestrator
  把 IO 串起来。具体分工：
    • Excel 读取：infra_io.excel_reader.read_rows / get_column_headers
    • PNG 落盘：infra_io.chart_writer.render_plot_to_png
              （内部走 file_manager.atomic_writer，自带占用预检 + 原子替换）
    • 模板 JSON：默认读 cfg.paths.curve_templates（即 ./templates/plot_curves/curve_templates.json）
                 也支持显式传 templates_path（测试 / 自定义模板库）

旧版 plot_curves.py 里的 UI 流程（_main / _request_params / _generate_example_flow）
已剥离，将于第二阶段在 ui/windows/plot_curves_view.py 用 PySide6 重做。
旧版的 generate_example_excel 依赖 pandas（CLAUDE.md 总纲禁用），暂不迁移；
若 UI 需要"生成示例"按钮，第二阶段用 openpyxl 重写到 ui/components/。

异常约定（与 ExcelReadError / FileBusyError 保持一致）：
  PlotCurvesError —— 业务异常，带 hint 字段供 UI 三段式提示直接展示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from civil_auto.config.loader import load_config
from civil_auto.domain.schema import AxisSpec, CurveSeries, PlotJob
from civil_auto.infra_io.chart_writer import render_plot_to_png
from civil_auto.infra_io.excel_reader import read_rows
from civil_auto.infra_io.file_manager import FileBusyError, FileWriteError
from civil_auto.utils.logger import compute_file_sha256, get_logger, write_audit_entry

log = get_logger(__name__)
_TOOL_NAME = "plot_curves"  # 审计条目里的 tool 字段


# ──────────────────────────────────────────────────────────────────
# 异常
# ──────────────────────────────────────────────────────────────────
class PlotCurvesError(RuntimeError):
    """绘曲线图业务异常。hint 字段用于 UI 三段式提示（定位→原因→建议）。"""

    hint: str

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


# ──────────────────────────────────────────────────────────────────
# 模块 1：模板加载与列名解析（纯计算）
# ──────────────────────────────────────────────────────────────────
def load_templates(templates_path: Path | str | None = None) -> dict[str, Any]:
    """加载曲线模板库 JSON。

    templates_path=None 时读 cfg.paths.curve_templates（即
    ./templates/plot_curves/curve_templates.json）；显式传路径则直接读那个文件
    （测试 / 自定义模板库）。
    """
    if templates_path is None:
        cfg = load_config()
        path = cfg.paths.curve_templates
    else:
        path = Path(templates_path)

    if not path.is_file():
        raise PlotCurvesError(
            f"曲线模板库不存在：{path}",
            hint=(
                "请检查 config.toml 的 paths.curve_templates 是否正确，"
                "或将模板 JSON 放到该路径下。"
            ),
        )

    import json  # 延迟导入

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise PlotCurvesError(
            f"模板库 JSON 解析失败（{path.name}）：{e}",
            hint=f"路径：{path}，请检查 JSON 语法。",
        ) from e


def get_template_names(templates: dict[str, Any]) -> list[str]:
    """筛掉以 _ 开头的注释字段，返回真实模板名列表。"""
    return [k for k in templates.keys() if not k.startswith("_")]


def _axis_spec_from_dict(d: dict[str, Any]) -> AxisSpec:
    """JSON 的 {label, range} → AxisSpec。range 兼容 list / null。"""
    rng = d.get("range")
    if rng is None:
        return AxisSpec(label=d["label"], range=None)
    return AxisSpec(
        label=d["label"],
        range=(float(rng[0]), float(rng[1]), float(rng[2])),
    )


def _normalize_col(name: str) -> str:
    """列名标准化：去所有空白（含全角 \\u3000）+ 转小写，用于宽松匹配。

    Excel 多行表头经常出现 "15.0kN(0.1Nd)位移读数" vs "15.0kN (0.1Nd) 位移读数"
    这种细微差，肉眼一致但字符串不等。把空白全部抹掉再比就稳了。
    """
    return re.sub(r"[\s　]+", "", str(name)).lower()


def resolve_columns(
    template: dict[str, Any], available_cols: list[str]
) -> tuple[dict[str, str], list[str]]:
    """把模板里的所有 var_column / id_column 映射到 Excel 实际列名。

    返回 (resolved, missing)：
        resolved = {模板列名: Excel 实际列名}
        missing  = 模板需要但 Excel 表头里找不到的列名列表
    匹配策略：精确匹配优先 → 退化到「去空白 + 小写」容差匹配。
    """
    norm_to_actual: dict[str, str] = {_normalize_col(c): c for c in available_cols}

    needed: list[str] = [template["id_column"]]
    for curve in template.get("curves", []):
        for pt in curve.get("points", []):
            if pt.get("var_column") and pt["var_column"] not in needed:
                needed.append(pt["var_column"])

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for col in needed:
        if col in available_cols:
            resolved[col] = col
        else:
            actual = norm_to_actual.get(_normalize_col(col))
            if actual:
                resolved[col] = actual
            else:
                missing.append(col)
    return resolved, missing


# ──────────────────────────────────────────────────────────────────
# 模块 2：构造 PlotJob 列表（纯计算）
# ──────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class BuildSummary:
    """build_jobs 的副产品：跳过了哪些行、为什么。

    UI 层可以拿这个去渲染"已跳过 N 行（点开看明细）"。
    """

    total_rows: int
    skipped_empty_id: list[int]  # 1-based 行号
    skipped_bad_data: list[tuple[int, str]]  # (1-based 行号, 标识值)


def _series_from_template(
    curve_def: dict[str, Any],
    row: dict[str, Any],
    col_map: dict[str, str],
) -> CurveSeries | None:
    """模板曲线定义 + 一行 Excel → CurveSeries。

    任一点缺数据则整条曲线返回 None；调用方据此跳过该行。
    fixed_axis='y' 表示 y 是模板写死的常量（如载荷 60kN），x 从 Excel 列读；
    'x' 反之。
    """
    xs: list[float] = []
    ys: list[float] = []
    for pt in curve_def["points"]:
        template_col = pt["var_column"]
        actual_col = col_map.get(template_col, template_col)
        if actual_col not in row:
            log.warning("列 %r 在 Excel 中找不到（已尝试空白容差匹配）", template_col)
            return None
        raw = row[actual_col]
        try:
            var_value = float(raw)
        except (TypeError, ValueError):
            log.warning("列 %r 的值不是数字: %r", actual_col, raw)
            return None

        if pt["fixed_axis"] == "y":
            ys.append(float(pt["fixed_value"]))
            xs.append(var_value)
        elif pt["fixed_axis"] == "x":
            xs.append(float(pt["fixed_value"]))
            ys.append(var_value)
        else:
            raise PlotCurvesError(
                f"模板 fixed_axis 必须是 'x' 或 'y'，得到 {pt['fixed_axis']!r}",
                hint="检查 curve_templates.json 里对应曲线点的 fixed_axis 字段。",
            )

    return CurveSeries(
        name=curve_def["name"],
        xs=xs,
        ys=ys,
        color=curve_def.get("color", "#1F4FE0"),
        marker=curve_def.get("marker", "s"),
        linewidth=curve_def.get("linewidth", 2.0),
        markersize=curve_def.get("markersize", 7.0),
    )


def build_jobs(
    template: dict[str, Any],
    rows: list[dict[str, Any]],
    output_dir: Path | str,
) -> tuple[list[PlotJob], BuildSummary]:
    """模板 + 数据行 → (PlotJob 列表, BuildSummary)。

    与旧版差异：
      • 缺列时直接抛 PlotCurvesError（带 hint），不再静默返回空列表
        —— 调用方应在 build_jobs 之前调 preflight_check 拦下
      • 跳过的行汇总到 BuildSummary，由调用方决定提示方式
      • output_dir 用 Path 拼接（不再用 os.path.join）
    """
    out_dir = Path(output_dir)
    available_cols = list(rows[0].keys()) if rows else []

    col_map, missing = resolve_columns(template, available_cols)
    if missing:
        raise PlotCurvesError(
            f"模板需要的 {len(missing)} 个列在 Excel 表头中找不到：{missing}",
            hint=(
                "请先调 preflight_check 拿详细诊断；"
                "或用[曲线模板编辑器]修正列名后重试。"
            ),
        )

    id_col_actual = col_map[template["id_column"]]
    fname_tpl = template["filename_template"]
    title_tpl = template["title_template"]
    x_axis = _axis_spec_from_dict(template["x_axis"])
    y_axis = _axis_spec_from_dict(template["y_axis"])

    jobs: list[PlotJob] = []
    skipped_empty_id: list[int] = []
    skipped_bad_data: list[tuple[int, str]] = []

    for idx, row in enumerate(rows, start=1):
        raw_id = row.get(id_col_actual)
        # NaN（float 自比不等）和 None 都视为空标识
        if raw_id is None or (isinstance(raw_id, float) and raw_id != raw_id):
            log.warning("第 %d 行标识列为空，跳过。", idx)
            skipped_empty_id.append(idx)
            continue

        if isinstance(raw_id, float) and raw_id.is_integer():
            id_str = str(int(raw_id))
        else:
            id_str = str(raw_id).strip()

        series_list: list[CurveSeries] = []
        skip_row = False
        for curve_def in template["curves"]:
            s = _series_from_template(curve_def, row, col_map)
            if s is None:
                log.warning(
                    "第 %d 行 (%s=%s) 数据不完整，跳过此行。",
                    idx,
                    template["id_column"],
                    id_str,
                )
                skipped_bad_data.append((idx, id_str))
                skip_row = True
                break
            series_list.append(s)
        if skip_row:
            continue

        jobs.append(
            PlotJob(
                title=title_tpl.format(id=id_str),
                output_path=out_dir / fname_tpl.format(id=id_str),
                x_axis=x_axis,
                y_axis=y_axis,
                series=series_list,
            )
        )

    summary = BuildSummary(
        total_rows=len(rows),
        skipped_empty_id=skipped_empty_id,
        skipped_bad_data=skipped_bad_data,
    )
    return jobs, summary


# ──────────────────────────────────────────────────────────────────
# 模块 3：预检（纯计算，给 UI / CLI 出"对用户友好"的诊断报告）
# ──────────────────────────────────────────────────────────────────
def preflight_check(
    template: dict[str, Any], excel_columns: list[str]
) -> tuple[bool, str]:
    """跑批量前体检：检查 Excel 表头是否覆盖模板需要的所有列。

    返回 (是否通过, 多行诊断文本)。文本可直接喂给 UI 的 InfoBar 详情区或 CLI 输出。
    """
    col_map, missing = resolve_columns(template, excel_columns)
    needed_total = len(col_map) + len(missing)
    n_ok = len(col_map)

    lines: list[str] = []
    lines.append(
        f"📋 模板需 {needed_total} 列；已匹配 {n_ok}，缺失 {len(missing)}。\n"
    )

    if col_map:
        lines.append("✅ 已匹配的列（左=模板，右=Excel 实际）:")
        for tpl_col, actual in col_map.items():
            tag = "  (容差匹配)" if tpl_col != actual else ""
            lines.append(f"   • {tpl_col!r:50s} → {actual!r}{tag}")
        lines.append("")

    if missing:
        lines.append("❌ 模板需要但 Excel 找不到的列:")
        for m in missing:
            lines.append(f"   • {m!r}")
        lines.append("")
        lines.append("Excel 实际表头供参考:")
        for c in excel_columns:
            lines.append(f"   - {c!r}")
        lines.append("")
        lines.append("→ 请打开 [曲线模板编辑器] 把这些列名改成与 Excel 一致。")

    ok = len(missing) == 0
    return ok, "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
# 模块 4：顶层 orchestrator（串起 IO；本身不直接读写文件）
# ──────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class RunResult:
    """run_plot_curves 的最终结果。

    written        成功落盘的 PNG 路径列表
    failed         失败的 (PlotJob, 异常) 列表 —— 单张失败不影响后续
    summary        构造阶段跳过行的汇总
    """

    written: list[Path]
    failed: list[tuple[PlotJob, Exception]]
    summary: BuildSummary


def run_plot_curves(
    excel_path: Path | str,
    sheet_name: str | None,
    template_name: str,
    output_dir: Path | str,
    *,
    templates_path: Path | str | None = None,
    header_row: int = 1,
) -> RunResult:
    """工具入口：读 Excel → 套模板 → 批量出 PNG。

    本函数本身不调用任何 open/read/write，全部 IO 委派给 infra_io：
      excel_reader.read_rows  —— 读 Excel
      chart_writer.render_plot_to_png  —— 写 PNG（atomic_writer 兜底）

    参数：
      excel_path     数据 Excel 路径
      sheet_name     None=取第一个 sheet
      template_name  curve_templates.json 里的模板键
      output_dir     PNG 输出目录（不存在会被 atomic_writer 自动 mkdir -p）
      templates_path 自定义模板库 JSON 路径，None=走 config.loader.load_legacy_json
      header_row     表头所在行（1-based），缺省 1
    """
    excel = Path(excel_path)
    out_dir = Path(output_dir)

    # 审计基础字段：在任何可能 raise 的逻辑前先准备好，
    # 这样异常分支也能写出一条完整的 failed 审计条目。
    # SHA256 在 Excel 真正能读到时再算（如果文件不存在，下游 read_rows 会抛 ExcelReadError，
    # 那时 input_sha256 留 None 反映"没读到"是更忠实的事实）。
    input_sha: str | None = None
    audit_extra: dict[str, Any] = {
        "sheet": sheet_name,
        "template": template_name,
        "header_row": header_row,
    }

    try:
        # 先算 SHA256：尽量早算，让任何分支（含模板缺失等业务异常）的 failed 审计都能带上指纹。
        # 文件不存在 / 不可读时跳过；下游 read_rows 会以 ExcelReadError 给用户准确提示。
        if excel.is_file():
            input_sha = compute_file_sha256(excel)

        log.info("📂 加载模板库")
        templates = load_templates(templates_path)
        if template_name not in templates:
            raise PlotCurvesError(
                f"模板 {template_name!r} 不存在",
                hint=f"可用模板：{get_template_names(templates)}",
            )
        template = templates[template_name]
        log.info("   ↳ 选用模板: %s", template_name)

        log.info("📊 读取 Excel: %s  Sheet: %s", excel, sheet_name or "<默认第一个>")
        rows = read_rows(excel, sheet_name, header_row=header_row)
        log.info("   ↳ 共 %d 行数据", len(rows))
        if not rows:
            raise PlotCurvesError(
                "Excel 没有可读取的数据行",
                hint=(
                    f"路径：{excel}\n"
                    f"Sheet：{sheet_name or '<默认>'}\n"
                    f"header_row={header_row}\n"
                    "请确认 sheet 名、表头位置和数据是否正确。"
                ),
            )

        log.info("🔨 构建绘图任务...")
        jobs, summary = build_jobs(template, rows, out_dir)
        log.info(
            "   ↳ 有效任务 %d 个（跳过空行 %d，跳过缺数据行 %d）",
            len(jobs),
            len(summary.skipped_empty_id),
            len(summary.skipped_bad_data),
        )

        log.info("📁 输出目录: %s", out_dir)
        written: list[Path] = []
        failed: list[tuple[PlotJob, Exception]] = []

        for i, job in enumerate(jobs, start=1):
            try:
                written.append(render_plot_to_png(job))
                if i % 10 == 0 or i == len(jobs):
                    log.info("   ↳ 进度 %d/%d: %s", i, len(jobs), job.output_path.name)
            except (FileBusyError, FileWriteError) as e:
                log.error("   ❌ 第 %d 张失败（IO）: %s — %s", i, job.output_path.name, e)
                failed.append((job, e))
            except Exception as e:
                log.error(
                    "   ❌ 第 %d 张失败: %s — %s", i, job.output_path.name, e,
                    exc_info=True,
                )
                failed.append((job, e))

        log.info(
            "🎉 完成：成功 %d / 任务 %d / 失败 %d",
            len(written),
            len(jobs),
            len(failed),
        )

        # 审计：成功 / 部分成功
        status = "ok" if not failed else "partial"
        write_audit_entry(
            _TOOL_NAME,
            status=status,
            input_path=excel,
            input_sha256=input_sha,
            output_dir=out_dir,
            extra={
                **audit_extra,
                "total_jobs": len(jobs),
                "written_count": len(written),
                "failed_count": len(failed),
                "skipped_empty_id": len(summary.skipped_empty_id),
                "skipped_bad_data": len(summary.skipped_bad_data),
                "written": [str(p) for p in written],
                "failed": [
                    {"path": str(j.output_path), "error": f"{type(e).__name__}: {e}"}
                    for j, e in failed
                ],
            },
        )
        return RunResult(written=written, failed=failed, summary=summary)

    except Exception as e:
        # 审计：整批失败（找不到模板 / Excel 读取失败 / Sheet 空 / build_jobs 缺列等）
        write_audit_entry(
            _TOOL_NAME,
            status="failed",
            input_path=excel,
            input_sha256=input_sha,
            output_dir=out_dir,
            extra={**audit_extra, "error": f"{type(e).__name__}: {e}"},
        )
        raise
