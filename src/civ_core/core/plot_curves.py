"""绘曲线图工具核心业务逻辑（纯参数 / 无 IO / 无 UI）。

职责切分（v2.3 总纲）：
  本模块只负责"预设 + 数据行 → PlotJob 列表"的纯计算，以及顶层 orchestrator
  把 IO 串起来。具体分工：
    • Excel 读取：infra_io.excel_reader.read_rows / get_column_headers
    • PNG 落盘：infra_io.chart_writer.render_plot_to_png
              （内部走 file_manager.atomic_writer，自带占用预检 + 原子替换）
    • 预设 JSON：默认读 cfg.paths.curve_presets（即 ./presets/plot_curves/curve_presets.json）
                 也支持显式传 presets_path（测试 / 自定义预设库）

旧版 plot_curves.py 里的 UI 流程（_main / _request_params / _generate_example_flow）
已剥离，将于第二阶段在 ui/windows/plot_curves_view.py 用 PySide6 重做。
旧版的 generate_example_excel 依赖 pandas（CLAUDE.md 总纲禁用），暂不迁移；
若 UI 需要"生成示例"按钮，第二阶段用 openpyxl 重写到 ui/components/。

异常约定（与 ExcelReadError / FileBusyError 保持一致）：
  PlotCurvesError —— 业务异常，带 hint 字段供 UI 三段式提示直接展示。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from civ_core.domain.schema import AxisSpec, CurveSeries, PlotJob
from civ_core.infra_io.chart_writer import render_plot_to_png
from civ_core.infra_io.excel_reader import read_rows
from civ_core.infra_io.file_manager import FileBusyError, FileWriteError
from civ_core.utils.logger import compute_file_sha256, get_logger, write_audit_entry

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
# 模块 1：预设加载与列名解析（纯计算）
# ──────────────────────────────────────────────────────────────────
def load_presets(presets_path: Path | str | None = None) -> dict[str, Any]:
    """加载曲线预设库（合并系统 + 用户）。

    两种调用模式：
      • presets_path=None（生产路径）
            走 preset_manager.load_merged_presets_as_dict("plot_curves")
            返回的是"系统预设 + 用户预设"合并后的扁平字典 {预设名: data}
            - 系统预设：cfg.paths.curve_presets
            - 用户预设：cfg.paths.user_presets_dir / plot_curves/curve_presets.json
            - 合并语义见 infra_io.preset_manager._merge
      • presets_path 显式传入（测试 / CLI --presets-path）
            直接读该文件，不走合并逻辑。这条路径是给"我就要用这个 JSON 跑一次"的
            场景留的，比如单元测试用 fixtures，或者 CLI 调试自定义预设库。

    异常：
      • presets_path=None 时由 preset_manager 抛 PresetError；这里转成 PlotCurvesError
        以保持 core 层异常面统一（UI / CLI 三段式提示用 PlotCurvesError 解析）
      • presets_path 显式传入时，文件缺失 / JSON 错直接抛 PlotCurvesError
    """
    # 模式一：默认路径 → 走合并管线
    if presets_path is None:
        # 延迟 import：避免循环引用（preset_manager 也走 load_config）
        from civ_core.infra_io.preset_manager import (
            PresetError,
            load_merged_presets_as_dict,
        )

        try:
            return load_merged_presets_as_dict("plot_curves")
        except PresetError as e:
            # 转成 PlotCurvesError 让上层（UI/CLI）统一三段式提示
            raise PlotCurvesError(str(e), hint=e.hint) from e

    # 模式二：显式路径 → 单文件直读（不合并用户预设）
    path = Path(presets_path)
    if not path.is_file():
        raise PlotCurvesError(
            f"曲线预设库不存在：{path}",
            hint=(
                "请检查路径是否正确，或将预设 JSON 放到该路径下。"
                "（如果想用默认路径 + 用户预设合并，去掉 --presets-path / presets_path 参数即可）"
            ),
        )

    import json  # 延迟导入

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise PlotCurvesError(
            f"预设库 JSON 解析失败（{path.name}）：{e}",
            hint=f"路径：{path}，请检查 JSON 语法。",
        ) from e


def get_preset_names(presets: dict[str, Any]) -> list[str]:
    """筛掉以 _ 开头的注释字段，返回真实预设名列表。"""
    return [k for k in presets.keys() if not k.startswith("_")]


def _axis_spec_from_dict(d: dict[str, Any]) -> AxisSpec:
    """JSON 的 {label, range, log} → AxisSpec。range 兼容 list / null；log 默认 False。"""
    rng = d.get("range")
    log = bool(d.get("log", False))
    if rng is None:
        return AxisSpec(label=d["label"], range=None, log=log)
    return AxisSpec(
        label=d["label"],
        range=(float(rng[0]), float(rng[1]), float(rng[2])),
        log=log,
    )


def _normalize_col(name: str) -> str:
    """列名标准化：去所有空白（含全角 \\u3000）+ 转小写，用于宽松匹配。

    Excel 多行表头经常出现 "15.0kN(0.1Nd)位移读数" vs "15.0kN (0.1Nd) 位移读数"
    这种细微差，肉眼一致但字符串不等。把空白全部抹掉再比就稳了。
    """
    return re.sub(r"[\s　]+", "", str(name)).lower()


def resolve_columns(
    preset: dict[str, Any], available_cols: list[str]
) -> tuple[dict[str, str], list[str]]:
    """把预设里的所有 var_column / id_column 映射到 Excel 实际列名。

    返回 (resolved, missing)：
        resolved = {预设列名: Excel 实际列名}
        missing  = 预设需要但 Excel 表头里找不到的列名列表
    匹配策略：精确匹配优先 → 退化到「去空白 + 小写」容差匹配。
    """
    norm_to_actual: dict[str, str] = {_normalize_col(c): c for c in available_cols}

    needed: list[str] = [preset["id_column"]]
    for curve in preset.get("curves", []):
        for pt in curve.get("points", []):
            if pt.get("var_column") and pt["var_column"] not in needed:
                needed.append(pt["var_column"])
            # P1.5-④ 误差棒：err_column 也参与列名解析
            if pt.get("err_column") and pt["err_column"] not in needed:
                needed.append(pt["err_column"])

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


def _series_from_preset(
    curve_def: dict[str, Any],
    row: dict[str, Any],
    col_map: dict[str, str],
) -> CurveSeries | None:
    """预设曲线定义 + 一行 Excel → CurveSeries。

    任一点缺数据则整条曲线返回 None；调用方据此跳过该行。
    fixed_axis='y' 表示 y 是预设写死的常量（如载荷 60kN），x 从 Excel 列读；
    'x' 反之。

    P1.5-④ 新字段：
      curve_def["y_axis"]          : "primary"|"secondary"（默认 primary）
      curve_def["points"][j].err_column : 该点 ±y 误差来源列（可选）
        - 任一点配置了 err_column → 整条曲线 y_err 非空
        - 缺该列或非数字 → 该点误差填 0（不导致整曲线无效）
    """
    xs: list[float] = []
    ys: list[float] = []
    y_err_buf: list[float] = []
    has_any_err = False
    for pt in curve_def["points"]:
        # preset_col 是预设里写的列名引用，actual_col 是 Excel 实际表头（容差匹配后的结果）
        preset_col = pt["var_column"]
        actual_col = col_map.get(preset_col, preset_col)
        if actual_col not in row:
            log.warning("列 %r 在 Excel 中找不到（已尝试空白容差匹配）", preset_col)
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
                f"预设 fixed_axis 必须是 'x' 或 'y'，得到 {pt['fixed_axis']!r}",
                hint="检查 curve_presets.json 里对应曲线点的 fixed_axis 字段。",
            )

        # 误差：每点都收一个；不配 / 缺列 / 非数字 → 填 0
        err_col_preset = pt.get("err_column")
        if err_col_preset:
            err_actual = col_map.get(err_col_preset, err_col_preset)
            if err_actual in row:
                try:
                    e = float(row[err_actual])
                    if e < 0:
                        e = 0.0
                    y_err_buf.append(e)
                    has_any_err = True
                except (TypeError, ValueError):
                    y_err_buf.append(0.0)
            else:
                y_err_buf.append(0.0)
        else:
            y_err_buf.append(0.0)

    return CurveSeries(
        name=curve_def["name"],
        xs=xs,
        ys=ys,
        color=curve_def.get("color", "#1F4FE0"),
        marker=curve_def.get("marker", "s"),
        linewidth=curve_def.get("linewidth", 2.0),
        markersize=curve_def.get("markersize", 7.0),
        plot_type=curve_def.get("plot_type", "line"),
        y_axis=curve_def.get("y_axis", "primary"),
        y_err=(y_err_buf if has_any_err else None),
    )


def build_jobs(
    preset: dict[str, Any],
    rows: list[dict[str, Any]],
    output_dir: Path | str,
) -> tuple[list[PlotJob], BuildSummary]:
    """预设 + 数据行 → (PlotJob 列表, BuildSummary)。

    与旧版差异：
      • 缺列时直接抛 PlotCurvesError（带 hint），不再静默返回空列表
        —— 调用方应在 build_jobs 之前调 preflight_check 拦下
      • 跳过的行汇总到 BuildSummary，由调用方决定提示方式
      • output_dir 用 Path 拼接（不再用 os.path.join）

    注意：JSON 字段名 filename_template / title_template 是字面意义的"字符串模板"
    （含 {id} 占位符），与"预设"概念无关，因此保留 template 命名。
    """
    out_dir = Path(output_dir)
    available_cols = list(rows[0].keys()) if rows else []

    col_map, missing = resolve_columns(preset, available_cols)
    if missing:
        raise PlotCurvesError(
            f"预设需要的 {len(missing)} 个列在 Excel 表头中找不到：{missing}",
            hint=("请先调 preflight_check 拿详细诊断；或用[曲线预设编辑器]修正列名后重试。"),
        )

    id_col_actual = col_map[preset["id_column"]]
    fname_tpl = preset["filename_template"]  # 字面字符串模板，保留 template 命名
    title_tpl = preset["title_template"]  # 同上
    x_axis = _axis_spec_from_dict(preset["x_axis"])
    y_axis = _axis_spec_from_dict(preset["y_axis"])
    # P1.5-④ 双 Y 轴：预设可选 y_axis2；缺省 / None → 单 Y 轴
    y_axis2_dict = preset.get("y_axis2")
    y_axis2 = _axis_spec_from_dict(y_axis2_dict) if y_axis2_dict is not None else None
    # 图级样式：preset["style"] 可能不存在（旧预设）→ 默认 grid=True / 无 legend
    style = preset.get("style") or {}
    grid = bool(style.get("grid", True))
    legend_loc = style.get("legend")

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
        for curve_def in preset["curves"]:
            s = _series_from_preset(curve_def, row, col_map)
            if s is None:
                log.warning(
                    "第 %d 行 (%s=%s) 数据不完整，跳过此行。",
                    idx,
                    preset["id_column"],
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
                grid=grid,
                legend_loc=legend_loc,
                y_axis2=y_axis2,
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
def preflight_check(preset: dict[str, Any], excel_columns: list[str]) -> tuple[bool, str]:
    """跑批量前体检：检查 Excel 表头是否覆盖预设需要的所有列。

    返回 (是否通过, 多行诊断文本)。文本可直接喂给 UI 的 InfoBar 详情区或 CLI 输出。
    """
    col_map, missing = resolve_columns(preset, excel_columns)
    needed_total = len(col_map) + len(missing)
    n_ok = len(col_map)

    lines: list[str] = []
    lines.append(f"📋 预设需 {needed_total} 列；已匹配 {n_ok}，缺失 {len(missing)}。\n")

    if col_map:
        lines.append("✅ 已匹配的列（左=预设，右=Excel 实际）:")
        for preset_col, actual in col_map.items():
            tag = "  (容差匹配)" if preset_col != actual else ""
            lines.append(f"   • {preset_col!r:50s} → {actual!r}{tag}")
        lines.append("")

    if missing:
        lines.append("❌ 预设需要但 Excel 找不到的列:")
        for m in missing:
            lines.append(f"   • {m!r}")
        lines.append("")
        lines.append("Excel 实际表头供参考:")
        for c in excel_columns:
            lines.append(f"   - {c!r}")
        lines.append("")
        lines.append("→ 请打开 [曲线预设编辑器] 把这些列名改成与 Excel 一致。")

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


_SUPPORTED_OUTPUT_FORMATS = frozenset({"svg", "png", "jpg", "jpeg"})


def _override_output_format(preset: dict[str, Any], fmt: str) -> dict[str, Any]:
    """临时把 preset['filename_template'] 的后缀换成 .fmt（不修改原 dict）。

    用于"用户选了输出格式但没编辑预设"的快捷路径——避免把"我现在想出 PNG"
    这种临时偏好持久化到预设文件里。
    """
    fmt_norm = fmt.strip().lower().lstrip(".")
    if fmt_norm not in _SUPPORTED_OUTPUT_FORMATS:
        raise PlotCurvesError(
            f"不支持的输出格式 {fmt!r}",
            hint=f"支持的格式：{sorted(_SUPPORTED_OUTPUT_FORMATS)}",
        )
    new_preset = dict(preset)
    tpl = new_preset.get("filename_template", "{id}.svg")
    # 用 Path 的 with_suffix 处理 —— 不依赖原 tpl 的后缀写法
    new_preset["filename_template"] = str(Path(tpl).with_suffix(f".{fmt_norm}"))
    return new_preset


def run_plot_curves(
    excel_path: Path | str,
    sheet_name: str | None,
    preset_name: str,
    output_dir: Path | str,
    *,
    presets_path: Path | str | None = None,
    header_row: int = 1,
    progress_cb: Callable[[int, int], None] | None = None,
    preset_override: dict[str, Any] | None = None,
    output_format: str | None = None,
) -> RunResult:
    """工具入口：读 Excel → 套预设 → 批量出 PNG。

    本函数本身不调用任何 open/read/write，全部 IO 委派给 infra_io：
      excel_reader.read_rows  —— 读 Excel
      chart_writer.render_plot_to_png  —— 写 PNG（atomic_writer 兜底）

    参数：
      excel_path     数据 Excel 路径
      sheet_name     None=取第一个 sheet
      preset_name    curve_presets.json 里的预设键
      output_dir     PNG 输出目录（不存在会被 atomic_writer 自动 mkdir -p）
      presets_path   自定义预设库 JSON 路径，None=读 cfg.paths.curve_presets
      header_row     表头所在行（1-based），缺省 1
      progress_cb    可选回调 (done, total)，每张图渲染后调一次。
                     UI 用它把进度信号发回主线程；CLI/脚本可不传，默认 no-op。
                     回调内任何异常都会被吞，不打断批量。
      preset_override 完整覆盖选中的预设字典（UI"工具设置"Tab 编辑后传进来）。
                     None=用预设库里的原始预设；给值=完全替换，不做 merge
                     （UI 拿的是完整预设 JSON，编辑回传也是完整 JSON，无歧义）。
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
        "preset": preset_name,
        "header_row": header_row,
        "output_format_override": output_format,
    }

    try:
        # 先算 SHA256：尽量早算，让任何分支（含预设缺失等业务异常）的 failed 审计都能带上指纹。
        # 文件不存在 / 不可读时跳过；下游 read_rows 会以 ExcelReadError 给用户准确提示。
        if excel.is_file():
            input_sha = compute_file_sha256(excel)

        log.info("📂 加载预设库")
        presets = load_presets(presets_path)
        if preset_name not in presets:
            raise PlotCurvesError(
                f"预设 {preset_name!r} 不存在",
                hint=f"可用预设：{get_preset_names(presets)}",
            )
        preset = preset_override if preset_override is not None else presets[preset_name]
        if preset_override is not None:
            log.info("   ↳ 选用预设: %s（UI 编辑覆盖）", preset_name)
        else:
            log.info("   ↳ 选用预设: %s", preset_name)
        # output_format（如有）：临时换 filename_template 后缀，不写回预设库
        if output_format:
            preset = _override_output_format(preset, output_format)
            log.info("   ↳ 输出格式覆盖为: %s", output_format)

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
        jobs, summary = build_jobs(preset, rows, out_dir)
        log.info(
            "   ↳ 有效任务 %d 个（跳过空行 %d，跳过缺数据行 %d）",
            len(jobs),
            len(summary.skipped_empty_id),
            len(summary.skipped_bad_data),
        )

        log.info("📁 输出目录: %s", out_dir)
        written: list[Path] = []
        failed: list[tuple[PlotJob, Exception]] = []

        total_jobs = len(jobs)
        for i, job in enumerate(jobs, start=1):
            try:
                written.append(render_plot_to_png(job))
                if i % 10 == 0 or i == total_jobs:
                    log.info("   ↳ 进度 %d/%d: %s", i, total_jobs, job.output_path.name)
            except (FileBusyError, FileWriteError) as e:
                log.error("   ❌ 第 %d 张失败（IO）: %s — %s", i, job.output_path.name, e)
                failed.append((job, e))
            except Exception as e:
                log.error(
                    "   ❌ 第 %d 张失败: %s — %s",
                    i,
                    job.output_path.name,
                    e,
                    exc_info=True,
                )
                failed.append((job, e))

            # 进度回调：异常吞掉但留 warning，避免 UI bug 把整个批量带崩
            if progress_cb is not None:
                try:
                    progress_cb(i, total_jobs)
                except Exception:
                    log.warning("progress_cb 抛异常（已忽略）", exc_info=True)

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
        # 审计：整批失败（找不到预设 / Excel 读取失败 / Sheet 空 / build_jobs 缺列等）
        write_audit_entry(
            _TOOL_NAME,
            status="failed",
            input_path=excel,
            input_sha256=input_sha,
            output_dir=out_dir,
            extra={**audit_extra, "error": f"{type(e).__name__}: {e}"},
        )
        raise
