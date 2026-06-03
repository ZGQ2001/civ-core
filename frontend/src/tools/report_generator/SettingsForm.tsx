/**
 * report_generator 右侧 RightPanel「调参」—— 拆成 3 个 tab section（数据 / 模板 / 项目字段）。
 *
 * 回归工具页范式：输入回到右侧面板（和其它工具一致），但字段远多于别的工具，
 * 故按层级拆成 3 个调参 tab，App.tsx 把它们注入 rightTabs，AI 助手常驻最后。
 *
 *   ReportDataSection     数据：报告类型选择（第一步）→ 跟着显示对应输入
 *                              · 锚杆：一键导入 + 数据来源 + 输入 Excel + 规范 + 批次 + 按批工程参数 + 灌浆日期
 *                              · 防火涂层：结果 Excel + 规范
 *                              · 多类型：锚杆结果 Excel + 防火涂层结果 Excel（参数已随结果持久化）
 *   ReportTemplateSection 模板：Word 模板 + 输出目录 + 曲线图目录
 *   ReportFieldsSection   项目字段：报告预设栏 + 历史值开关 + 项目元信息（CatalogDrivenInputs）
 */
import { useCallback, useEffect, useState } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import {
  ANCHOR_STANDARDS,
  type AnchorStandard,
} from '../data_processing/types';
import { rpc } from '../../lib/rpc';
import { logLine, useShell } from '../../lib/shell';
import { AnchorParamsSection } from '../_shared/anchorParamsForm';
import { CatalogDrivenInputs } from '../_shared/CatalogDrivenInputs';
import { Field, INPUT_CLS, Picker, ResetBtn, Select } from '../_shared/forms';
import { useReportGenerator } from './controller';
import { PresetBar } from './PresetBar';
import {
  COATING_STANDARDS,
  REPORT_TYPES,
  type CoatingStandard,
  type ReportType,
} from './types';

interface CatalogSummary {
  id: string;
  label: string;
  field_count: number;
}

/** 每个 tab section 的统一外壳（间距 / 内边距 / 字号），保证三块视觉一致。 */
function SectionShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col space-y-4 px-4 py-4 text-xs">{children}</div>
  );
}

/* ────────────────────────────── 数据 tab ────────────────────────────── */

export function ReportDataSection() {
  const c = useReportGenerator();
  const shell = useShell();
  const [catalogs, setCatalogs] = useState<CatalogSummary[]>([]);

  // 拉一份 catalog 清单给「检测项目」下拉用 —— 跟模板助手共用同一份 RPC，
  // 用户在模板助手里新建/复制目录，这里刷新就能看到。
  useEffect(() => {
    let cancelled = false;
    rpc<{ catalogs: CatalogSummary[] }>('catalog.list')
      .then((r) => {
        if (!cancelled) setCatalogs(r.catalogs);
      })
      .catch((e) => {
        shell.appendOutput(logLine(`[报告] 读检测项目清单失败: ${String(e)}`));
      });
    return () => {
      cancelled = true;
    };
  }, [shell]);

  const pickExcel = useCallback(async () => {
    const sel = await openDialog({
      title: '选择输入 Excel',
      multiple: false,
      filters: [{ name: 'Excel', extensions: ['xlsx', 'xls'] }],
    });
    if (typeof sel === 'string') c.setExcelPath(sel);
  }, [c]);

  const pickCoatingExcel = useCallback(async () => {
    const sel = await openDialog({
      title: '选择防火涂层「结果」Excel',
      multiple: false,
      filters: [{ name: 'Excel', extensions: ['xlsx', 'xls'] }],
    });
    if (typeof sel === 'string') c.setCoatingInputPath(sel);
  }, [c]);

  const showAnchor = c.reportType === 'anchor' || c.reportType === 'multi';
  const showCoating = c.reportType === 'coating' || c.reportType === 'multi';
  const isMulti = c.reportType === 'multi';

  return (
    <SectionShell>
      <ReportTypeField value={c.reportType} onChange={c.setReportType} />

      {/* 一键导入数据处理：只在涉及锚杆时有意义 */}
      {showAnchor && <ImportFromDataProcessingBtn />}

      <Field
        label="检测项目"
        hint="决定项目字段定义 / 预设过滤；从模板助手已有目录里选。当前只有锚杆抗拔真正接通 calc，其余目录改字段渲染但仍走锚杆 RPC（待钻芯/回弹切 C# 后自动分发）。"
      >
        <Select
          value={c.catalogId}
          onChange={(e) => c.setCatalogId(e.target.value)}
          className="w-full"
        >
          {catalogs.length === 0 && (
            <option value={c.catalogId}>{c.catalogId}（加载中…）</option>
          )}
          {catalogs.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.label}（{cat.field_count} 字段）
            </option>
          ))}
        </Select>
      </Field>

      <Field
        label="报告名称"
        hint="影响输出文件名；留空按报告类型取默认名。可包含中文。"
      >
        <input
          type="text"
          value={c.reportName}
          placeholder="（可选 — 例：XX环境整治-检测报告）"
          onChange={(e) => c.setReportName(e.target.value)}
          className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus w-full rounded-[2px] border px-2 py-1 text-xs focus:outline-none"
        />
      </Field>

      {/* ───────── 锚杆数据（仅锚杆 / 多类型）───────── */}
      {showAnchor && (
        <div className="border-vscode-border space-y-4 rounded-[3px] border bg-[#202020] p-2.5">
          <div className="text-vscode-text-dim text-[11px] font-medium">
            锚杆抗拔数据
          </div>

          {isMulti ? (
            <div className="text-vscode-text-faint border-l-2 border-l-[#3a3a3a] py-1 pl-2 text-[11px] leading-relaxed">
              多类型组装：锚杆请选「数据处理」出的
              <b className="text-vscode-text-dim">结果 Excel</b>
              （工程参数 / 灌浆日期已随结果保存，无需在此重填）。
            </div>
          ) : (
            <Field
              label="数据来源"
              hint="result 直接读结果 xlsx 出 Word 不重算；raw 走完整链路（数据处理→出 Word）"
            >
              <div className="flex items-center gap-3">
                {(
                  [
                    {
                      v: 'raw',
                      label: '原始数据 Excel',
                      note: '走完整计算链路',
                    },
                    {
                      v: 'result',
                      label: '结果数据 Excel',
                      note: '已算好的结果，直接出 Word（不重算）',
                    },
                  ] as const
                ).map((opt) => (
                  <label
                    key={opt.v}
                    className="flex cursor-pointer items-center gap-1"
                    title={opt.note}
                  >
                    <input
                      type="radio"
                      name="dataSource"
                      value={opt.v}
                      checked={c.dataSource === opt.v}
                      onChange={() => c.setDataSource(opt.v)}
                      className="accent-vscode-focus"
                    />
                    <span className="text-[11px]">{opt.label}</span>
                  </label>
                ))}
              </div>
            </Field>
          )}

          <Field
            label={isMulti ? '锚杆结果 Excel' : '输入 Excel'}
            hint={
              isMulti
                ? '数据处理生成的结果 xlsx（不重算）'
                : '按上方「数据来源」决定：raw=原始检测数据；result=数据处理已生成的结果 xlsx'
            }
          >
            <Picker
              value={c.excelPath}
              onPick={pickExcel}
              placeholder="（必选）"
              muted={!c.excelPath}
              extra={
                c.excelPath ? (
                  <ResetBtn onClick={() => c.setExcelPath('')} />
                ) : undefined
              }
            />
          </Field>

          <Field
            label="规范"
            hint="未来可扩展其他规范；当前仅支持 GB 50086-2015"
          >
            <Select
              value={c.anchorStandard}
              onChange={(e) =>
                c.setAnchorStandard(e.target.value as AnchorStandard)
              }
              className="w-full"
            >
              {ANCHOR_STANDARDS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="锚杆结果表节号"
            hint="公司标准：单根锚杆→「表{节号}」，多根→「表{节号}-1 / -2 …」。缺省 2.4"
          >
            <input
              type="text"
              value={c.sectionNo}
              onChange={(e) => c.setSectionNo(e.target.value)}
              placeholder="2.4"
              className={`${INPUT_CLS} w-24`}
            />
          </Field>

          {/* 仅锚杆才需要批次列名 / 按批工程参数 / 灌浆日期（多类型读结果 xlsx 已持久化） */}
          {!isMulti && (
            <>
              <Field
                label="批次列名"
                hint="输入 Excel 里用于区分批次的列名（一般是「批次」）"
              >
                <input
                  type="text"
                  value={c.anchorBatchIdColumn}
                  onChange={(e) => c.setAnchorBatchIdColumn(e.target.value)}
                  className={`${INPUT_CLS} w-full`}
                />
              </Field>

              {/* 结果数据来源：工程参数已随结果 xlsx 持久化（隐藏 _批次参数 sheet），无需再填。
                  原始数据来源：按批次填参数（会从输入 xlsx 的「批次信息」sheet 预填，可覆盖）。 */}
              {c.dataSource === 'result' ? (
                <Field
                  label="锚杆工程参数"
                  hint="结果数据已含各批工程参数（生成时从结果 xlsx 读取）"
                >
                  <div className="text-vscode-text-faint border-l-2 border-l-[#3a3a3a] py-1 pl-2 text-[11px] leading-relaxed">
                    已随「结果数据 Excel」持久化，无需在此填写。
                  </div>
                </Field>
              ) : (
                <AnchorParamsSection
                  excelReady={!!c.excelPath}
                  batchIds={c.anchorBatchIds}
                  paramsByBatch={c.anchorParamsByBatch}
                  loading={c.anchorBatchesLoading}
                  error={c.anchorBatchesError}
                  onSetBatch={c.setAnchorParamsForBatch}
                  onSetAll={c.setAnchorParamsForAllBatches}
                  emptyHint="先选输入 Excel，这里会按批次展开参数表（从「批次信息」sheet 预填）"
                />
              )}

              <GroutingDateByBatchSection />
            </>
          )}
        </div>
      )}

      {/* ───────── 防火涂层数据（防火涂层 / 多类型）───────── */}
      {showCoating && (
        <div className="border-vscode-border space-y-4 rounded-[3px] border bg-[#202020] p-2.5">
          <div className="text-vscode-text-dim text-[11px] font-medium">
            防火涂层数据
          </div>
          <Field
            label="防火涂层「结果」Excel"
            hint="coating_run 产出的结果 xlsx（含机读结果 sheet）；先在「数据处理」跑出结果再来这里"
          >
            <Picker
              value={c.coatingInputPath}
              onPick={pickCoatingExcel}
              placeholder="（必选）"
              muted={!c.coatingInputPath}
              extra={
                c.coatingInputPath ? (
                  <ResetBtn onClick={() => c.setCoatingInputPath('')} />
                ) : undefined
              }
            />
          </Field>
          <Field label="防火涂层规范" hint="决定布点 / 单位 / 判定口径">
            <Select
              value={c.coatingStandard}
              onChange={(e) =>
                c.setCoatingStandard(e.target.value as CoatingStandard)
              }
              className="w-full"
            >
              {COATING_STANDARDS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      )}
    </SectionShell>
  );
}

/**
 * 报告类型选择 —— 第一步：决定出哪种报告，下面只显示对应的输入。
 * 仅锚杆 / 仅防火涂层 / 两者组装到一份报告；以后加检测类型 = REPORT_TYPES 加一项。
 */
function ReportTypeField({
  value,
  onChange,
}: {
  value: ReportType;
  onChange: (t: ReportType) => void;
}) {
  return (
    <Field
      label="报告类型"
      hint="先选出什么报告，下面只显示对应的输入。模板也要对应：仅锚杆需 {{表格:锚杆}}；仅防火涂层需 {{表格:防火涂层}}；多类型两者都要。"
    >
      <div className="grid grid-cols-1 gap-1">
        {REPORT_TYPES.map((rt) => (
          <label
            key={rt.id}
            className={`flex cursor-pointer items-center gap-2 rounded-[2px] border px-2 py-1.5 ${
              value === rt.id
                ? 'border-vscode-focus bg-[#252525]'
                : 'border-vscode-border bg-[#1f1f1f]'
            }`}
          >
            <input
              type="radio"
              name="reportType"
              value={rt.id}
              checked={value === rt.id}
              onChange={() => onChange(rt.id)}
              className="accent-vscode-focus"
            />
            <span className="text-vscode-text text-[12px]">{rt.label}</span>
          </label>
        ))}
      </div>
    </Field>
  );
}

/* ────────────────────────────── 模板 tab ────────────────────────────── */

export function ReportTemplateSection() {
  const c = useReportGenerator();

  const pickTemplate = useCallback(async () => {
    const sel = await openDialog({
      title: '选择 Word 报告模板',
      multiple: false,
      filters: [{ name: 'Word', extensions: ['docx'] }],
    });
    if (typeof sel === 'string') c.setWordTemplatePath(sel);
  }, [c]);

  const pickOutputDir = useCallback(async () => {
    const sel = await openDialog({
      directory: true,
      multiple: false,
      title: '选择 Word 报告输出目录',
    });
    if (typeof sel === 'string') c.setOutputDir(sel);
  }, [c]);

  const pickCurveImageDir = useCallback(async () => {
    const sel = await openDialog({
      directory: true,
      multiple: false,
      title: '选择曲线图目录（plot_curves 出图的文件夹）',
    });
    if (typeof sel === 'string') c.setCurveImageDir(sel);
  }, [c]);

  return (
    <SectionShell>
      <Field
        label="Word 模板"
        hint="带 {{占位符}} 的薄壳 .docx：要放数据表处写一段表格占位符（程序按规范建表插入）——锚杆写 {{表格:锚杆}}、防火涂层写 {{表格:防火涂层}}、多类型两个都写。项目信息写 {{委托单位}} 等 {{}} 占位符。不会做？打开 ActivityBar 的「模板助手」。"
      >
        <Picker
          value={c.wordTemplatePath}
          onPick={pickTemplate}
          placeholder="（必选）"
          muted={!c.wordTemplatePath}
          extra={
            c.wordTemplatePath ? (
              <ResetBtn onClick={() => c.setWordTemplatePath('')} />
            ) : undefined
          }
        />
      </Field>

      <Field
        label="输出目录"
        hint="留空 = 在输入 Excel 同级建「_Word报告」子目录"
      >
        <Picker
          value={c.outputDir}
          onPick={pickOutputDir}
          placeholder="（自动）"
          muted={!c.outputDir}
          extra={
            c.outputDir ? (
              <ResetBtn onClick={() => c.setOutputDir('')} />
            ) : undefined
          }
        />
      </Field>

      <Field
        label="曲线图目录"
        hint="plot_curves 出图文件夹（按锚杆编号智能查找 svg/png/jpg）；留空 = 不嵌图，{{img:曲线图}} 留原文"
      >
        <Picker
          value={c.curveImageDir}
          onPick={pickCurveImageDir}
          placeholder="（可选 — 不嵌图）"
          muted={!c.curveImageDir}
          extra={
            c.curveImageDir ? (
              <ResetBtn onClick={() => c.setCurveImageDir('')} />
            ) : undefined
          }
        />
      </Field>
    </SectionShell>
  );
}

/* ───────────────────────────── 项目字段 tab ──────────────────────────── */

export function ReportFieldsSection() {
  const c = useReportGenerator();
  return (
    <SectionShell>
      <PresetBar
        catalogId={c.catalogId}
        values={c.userInputs}
        onLoad={c.loadUserInputs}
      />
      <HistoryToggleAndInputs />
    </SectionShell>
  );
}

/**
 * 历史值下拉的主开关 + 实际的字段渲染。
 * 默认关：避免页面加载时就并发 N 次 preset_get；用户点开关后才聚合。
 * 聚合规则：调 report_preset_list 拿 catalog 下所有预设，再依次 preset_get
 * 取 user_inputs，按 key 去重合并。
 */
function HistoryToggleAndInputs() {
  const c = useReportGenerator();
  const shell = useShell();
  const [historyEnabled, setHistoryEnabled] = useState(false);
  const [historyByKey, setHistoryByKey] = useState<Record<string, string[]>>(
    {},
  );
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    if (!historyEnabled) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHistoryByKey({});
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    (async () => {
      try {
        const list = await rpc<{
          presets: Array<{ id: string }>;
        }>('report_preset.list', { catalog_id: c.catalogId });
        // 并发拉全部预设
        const dtos = await Promise.all(
          list.presets.map((p) =>
            rpc<{
              preset: { user_inputs: Record<string, string> };
            }>('report_preset.get', { id: p.id }),
          ),
        );
        if (cancelled) return;
        const agg: Record<string, Set<string>> = {};
        for (const d of dtos) {
          for (const [k, v] of Object.entries(d.preset.user_inputs)) {
            if (!v?.trim()) continue;
            (agg[k] ??= new Set()).add(v);
          }
        }
        const out: Record<string, string[]> = {};
        for (const [k, s] of Object.entries(agg)) out[k] = Array.from(s).sort();
        setHistoryByKey(out);
      } catch (e) {
        shell.appendOutput(logLine(`[报告] 聚合历史值失败: ${String(e)}`));
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [historyEnabled, c.catalogId, shell]);

  return (
    <>
      <label className="border-vscode-border flex cursor-pointer items-center gap-2 rounded-[2px] border bg-[#252525] px-2 py-1.5">
        <input
          type="checkbox"
          checked={historyEnabled}
          onChange={(e) => setHistoryEnabled(e.target.checked)}
          className="accent-vscode-focus"
        />
        <span className="text-vscode-text text-[11px]">
          字段右侧显示「历史值下拉」
        </span>
        <span className="text-vscode-text-faint flex-1 text-[10px]">
          从同 catalog 已有预设里聚合；默认关，避免误覆盖你正在填的内容
        </span>
        {historyLoading && (
          <i className="codicon codicon-loading codicon-modifier-spin text-vscode-text-dim !text-[12px]" />
        )}
      </label>

      <CatalogDrivenInputs
        catalogId={c.catalogId}
        values={c.userInputs}
        onChange={c.setUserInput}
        onReset={c.resetUserInputs}
        historyByKey={historyEnabled ? historyByKey : undefined}
      />
    </>
  );
}

/**
 * 顶部「从数据处理一键导入」按钮 ——
 * 上游有可用 state 时高亮、可点；没有时灰禁、显示原因。
 */
function ImportFromDataProcessingBtn() {
  const c = useReportGenerator();
  const u = c.upstream;
  return (
    <div className="border-vscode-border rounded-[3px] border bg-[#252525] p-2">
      <button
        type="button"
        onClick={c.importFromDataProcessing}
        disabled={!u.available}
        className="bg-vscode-button hover:bg-vscode-button-hover flex w-full items-center justify-center gap-2 rounded-[2px] px-3 py-1.5 text-[12px] text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        title={
          u.available
            ? `导入: ${u.excelPath}（${u.batchCount} 批）`
            : (u.reason ?? '上游无可导入数据')
        }
      >
        <i className="codicon codicon-arrow-down !text-[13px]" />
        从「数据处理」一键导入
      </button>
      <div className="text-vscode-text-faint mt-1 text-[10px] leading-tight">
        {u.available ? (
          <>
            上游已就绪：{u.batchCount} 批，参数已填 {u.paramsFilledBatchCount}/
            {u.batchCount}
          </>
        ) : (
          <>未就绪：{u.reason ?? '—'}</>
        )}
      </div>
    </div>
  );
}

/**
 * 灌浆日期 按批次 渲染 ——
 *
 * 跟 AnchorParamsSection 共用状态机（excelReady / loading / error / 空批次 / 有批次）。
 * 不复用 BatchParamsCard：这里只有一个字段（grouting_date），折叠卡片反而臃肿。
 *
 * 各批灌浆日期会自动出现在该批锚杆的 表2.4「灌浆日期」格（程序建表按批填值，无需 marker）。
 */
function GroutingDateByBatchSection() {
  const c = useReportGenerator();
  const [broadcastDate, setBroadcastDate] = useState('');

  if (!c.excelPath) {
    return (
      <Field
        label="灌浆日期（按批次）"
        hint="选完输入 Excel 后这里会按批次展开"
      >
        <div className="text-vscode-text-faint text-[11px] italic">
          先选输入 Excel
        </div>
      </Field>
    );
  }
  if (c.anchorBatchesLoading) {
    return (
      <Field label="灌浆日期（按批次）">
        <div className="text-vscode-text-dim flex items-center gap-1 text-[11px]">
          <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
          加载批次清单…
        </div>
      </Field>
    );
  }
  if (c.anchorBatchesError) {
    return (
      <Field label="灌浆日期（按批次）">
        <div className="text-[11px] whitespace-pre-wrap text-red-400">
          读批次失败：{c.anchorBatchesError}
        </div>
      </Field>
    );
  }
  if (c.anchorBatchIds.length === 0) {
    return (
      <Field label="灌浆日期（按批次）">
        <div className="text-vscode-text-faint text-[11px] italic">
          Excel 里没读到任何批次
        </div>
      </Field>
    );
  }

  const filled = c.anchorBatchIds.filter((b) =>
    c.groutingDateByBatch[b]?.trim(),
  ).length;

  return (
    <Field
      label={`灌浆日期（按批次，共 ${c.anchorBatchIds.length} 批）`}
      hint="不同批次灌浆日期可能不同；各批日期会自动填进该批锚杆表的「灌浆日期」格"
    >
      <div className="space-y-2">
        <div className="text-vscode-text-faint flex items-center justify-between text-[10px]">
          <span>
            已填 {filled} / {c.anchorBatchIds.length}
          </span>
        </div>

        {/* 广播：填一次同步所有批次 */}
        <div className="border-vscode-border flex items-center gap-2 rounded-[2px] border bg-[#1f1f1f] px-2 py-1.5">
          <span className="text-vscode-text-dim shrink-0 text-[10px]">
            全部批次填同一日期：
          </span>
          <input
            type="date"
            value={broadcastDate}
            onChange={(e) => setBroadcastDate(e.target.value)}
            className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus min-w-0 flex-1 rounded-[2px] border px-1.5 py-0.5 text-[10px] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              if (broadcastDate) c.setGroutingDateForAllBatches(broadcastDate);
            }}
            disabled={!broadcastDate}
            className="text-vscode-focus disabled:text-vscode-text-faint shrink-0 text-[10px] hover:underline disabled:cursor-not-allowed disabled:no-underline"
          >
            应用
          </button>
        </div>

        {/* 每批一行 date input */}
        <div className="space-y-1.5">
          {c.anchorBatchIds.map((batchId) => (
            <div key={batchId} className="flex items-center gap-2">
              <span
                className="text-vscode-text-dim w-20 shrink-0 truncate text-[11px]"
                title={batchId}
              >
                {batchId}
              </span>
              <input
                type="date"
                value={c.groutingDateByBatch[batchId] ?? ''}
                onChange={(e) =>
                  c.setGroutingDateForBatch(batchId, e.target.value)
                }
                className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus min-w-0 flex-1 rounded-[2px] border px-2 py-1 text-[11px] focus:outline-none"
              />
            </div>
          ))}
        </div>
      </div>
    </Field>
  );
}
