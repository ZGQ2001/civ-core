/**
 * report_generator 右侧 RightPanel「调参」tab。
 *
 * 完全独立模式：自己填 Excel + 参数 + Word 模板 + user_inputs。
 * 顶部「从数据处理一键导入」按钮可选——上游有数据就高亮。
 *
 * 五块：
 *   1. 输入 Excel + 规范 + 批次列 + 共享的按批次参数卡片
 *   2. Word 模板路径 + 输出目录
 *   3. user_inputs 7 个折叠 group 卡片
 *   4. 「从数据处理一键导入」按钮（顶部）
 */
import { useCallback, useState } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import {
  ANCHOR_STANDARDS,
  type AnchorStandard,
} from '../data_processing/types';
import { AnchorParamsSection } from '../_shared/anchorParamsForm';
import { Field, Picker, ResetBtn } from '../_shared/forms';
import { useReportGenerator } from './controller';
import { USER_INPUT_GROUPS, type UserInputGroup } from './types';

export function ReportGeneratorSettingsForm() {
  const c = useReportGenerator();

  const pickExcel = useCallback(async () => {
    const sel = await openDialog({
      title: '选择输入 Excel',
      multiple: false,
      filters: [{ name: 'Excel', extensions: ['xlsx', 'xls'] }],
    });
    if (typeof sel === 'string') c.setExcelPath(sel);
  }, [c]);

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
    <div className="flex flex-col space-y-4 px-6 py-4 text-xs">
      <ImportFromDataProcessingBtn />

      <Field
        label="输入 Excel"
        hint="锚杆抗拔的原始数据或数据处理输出的结果 xlsx 都行"
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

      <Field label="规范" hint="未来可扩展其他规范；当前仅支持 GB 50086-2015">
        <select
          value={c.anchorStandard}
          onChange={(e) =>
            c.setAnchorStandard(e.target.value as AnchorStandard)
          }
          className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
        >
          {ANCHOR_STANDARDS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </Field>

      <Field
        label="批次列名"
        hint="输入 Excel 里用于区分批次的列名（一般是「批次」）"
      >
        <input
          type="text"
          value={c.anchorBatchIdColumn}
          onChange={(e) => c.setAnchorBatchIdColumn(e.target.value)}
          className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
        />
      </Field>

      <AnchorParamsSection
        excelReady={!!c.excelPath}
        batchIds={c.anchorBatchIds}
        paramsByBatch={c.anchorParamsByBatch}
        loading={c.anchorBatchesLoading}
        error={c.anchorBatchesError}
        onSetBatch={c.setAnchorParamsForBatch}
        onSetAll={c.setAnchorParamsForAllBatches}
        emptyHint="先选输入 Excel，这里会按批次展开参数表"
      />

      <GroutingDateByBatchSection />

      <div className="border-vscode-border border-t pt-3" />

      <Field
        label="Word 模板"
        hint="带 {{占位符}} 的 .docx。按锚杆克隆：用 [[每根锚杆]] / [[/每根锚杆]] 包住；按批次输出（灌浆日期等批次级字段）：外层再包 [[批次]] / [[/批次]]。不会做？打开 ActivityBar 的「模板助手」可按层级列字段并自动验证你的模板。"
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

      <div className="border-vscode-border flex items-center justify-between border-t pt-3">
        <div className="text-vscode-text text-[12px] font-medium">
          项目元信息（
          {USER_INPUT_GROUPS.reduce((s, g) => s + g.fields.length, 0)} 项）
        </div>
        <button
          type="button"
          onClick={c.resetUserInputs}
          className="text-vscode-text-dim hover:text-vscode-focus text-[11px] hover:underline"
        >
          全部清空
        </button>
      </div>

      <div className="space-y-2">
        {USER_INPUT_GROUPS.map((g, idx) => (
          <GroupCard key={g.id} group={g} defaultExpanded={idx === 0} />
        ))}
      </div>
    </div>
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
 * 模板要写 [[批次]]...[[/批次]] 才会按批次输出；旧模板（只有 [[每根锚杆]]）后端会
 * 走单批路径，此处填的日期会用其中一批的值（或忽略，由 AnchorHandlers.Run 决定）。
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
      hint="不同批次灌浆日期可能不同；模板里写 [[批次]]...[[/批次]] 后端才按批输出"
    >
      <div className="space-y-2">
        {/* 醒目提示：批次段是按批输出的必要条件 */}
        <div className="border-l-2 border-l-yellow-500 bg-[#2d2620] px-2 py-1.5 text-[10px] leading-relaxed text-yellow-300/90">
          <i className="codicon codicon-info mr-1 !text-[11px]" />
          模板里必须含{' '}
          <code className="rounded bg-black/30 px-1 text-yellow-200">
            [[批次]]...[[/批次]]
          </code>{' '}
          段，才能按批次输出不同灌浆日期；否则只取第一批的值灌入项目级。
        </div>

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
            className="bg-vscode-input border-vscode-border text-vscode-text min-w-0 flex-1 rounded-[2px] border px-1.5 py-0.5 text-[10px]"
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

function GroupCard({
  group,
  defaultExpanded,
}: {
  group: UserInputGroup;
  defaultExpanded: boolean;
}) {
  const c = useReportGenerator();
  const [expanded, setExpanded] = useState(defaultExpanded);

  const filledCount = group.fields.filter(
    (f) => !!c.userInputs[f.key]?.trim(),
  ).length;

  return (
    <div className="border-vscode-border rounded-[3px] border bg-[#252525]">
      <div
        className="hover:bg-vscode-hover flex cursor-pointer items-center px-2 py-1.5 select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <i
          className={`codicon codicon-chevron-${expanded ? 'down' : 'right'} text-vscode-text-dim mr-1 !text-[12px]`}
        />
        <i
          className={`codicon codicon-${group.icon} text-vscode-text-dim mr-1.5 !text-[12px]`}
        />
        <span className="text-vscode-text text-[12px] font-medium">
          {group.label}
        </span>
        <span className="text-vscode-text-faint ml-auto text-[10px]">
          {filledCount} / {group.fields.length}
        </span>
      </div>

      {expanded && (
        <div className="border-vscode-border space-y-2 border-t px-3 py-2">
          {group.fields.map((f) => (
            <div key={f.key}>
              <div className="text-vscode-text-dim mb-0.5 text-[11px]">
                {f.label}
              </div>
              <input
                type="text"
                value={c.userInputs[f.key]}
                placeholder={f.placeholder}
                onChange={(e) => c.setUserInput(f.key, e.target.value)}
                className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus w-full rounded-[2px] border px-2 py-1 text-xs focus:outline-none"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
