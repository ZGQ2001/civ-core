/**
 * report_generator 主区 —— 装配线「报告填充」环节。
 *
 * 回归工具页范式：输入表单移回右侧 RightPanel（3 个调参 tab：数据 / 模板 / 项目字段，
 * 见 App.tsx + SettingsForm.tsx）。中间页只放「动作 + 结果」：
 *   - 固定顶栏：标题 + 就绪态徽章 + 「生成 Word 报告」按钮
 *   - 内容区：空态引导 / 生成中 / 报错（role=alert，第一屏可见）/ 成功卡片
 *
 * 这样报错紧挨动作按钮、永不被长表单顶到屏外（旧版把结果接在表单最后面，要滚到底才看见）。
 */
import { useCallback, useState } from 'react';
import { openPath, revealItemInDir } from '@tauri-apps/plugin-opener';

import { cn } from '../../lib/cn';
import { logLine, useShell } from '../../lib/shell';
import { ErrorBanner, RunBtn, ToolHeader } from '../_shared/forms';
import {
  ANCHOR_TABLE_PLACEHOLDER,
  COATING_TABLE_PLACEHOLDER,
  useReportGenerator,
} from './controller';

export function ReportGeneratorPage({
  appendOutput,
}: {
  appendOutput?: (line: string) => void;
}) {
  const c = useReportGenerator();
  const shell = useShell();

  const handleRun = useCallback(async () => {
    const res = await c.run();
    if (res) {
      appendOutput?.(`完成：${res.summary} → ${res.output}`);
    }
    // 失败由 run() 内部统一 appendOutput；不在 await 后读 c.runError（陈旧闭包值）
  }, [c, appendOutput]);

  const openOutput = useCallback(async () => {
    if (!c.lastResult?.output) return;
    try {
      await openPath(c.lastResult.output);
    } catch (e) {
      shell.appendOutput(
        logLine(`[报告] 打开 docx 失败（请手动打开）: ${String(e)}`),
      );
    }
  }, [c.lastResult, shell]);

  const revealOutput = useCallback(async () => {
    if (!c.lastResult?.output) return;
    try {
      await revealItemInDir(c.lastResult.output);
    } catch (e) {
      shell.appendOutput(
        logLine(`[报告] 在资源管理器中显示失败: ${String(e)}`),
      );
    }
  }, [c.lastResult, shell]);

  return (
    <div className="flex h-full flex-col bg-[#1e1e1e]">
      <ToolHeader
        icon="file-text"
        title="报告填充"
        subtitle="在右侧「调参」填好输入（数据 / 模板 / 项目字段），把检测数据 + 项目元信息填入 Word 模板出 docx。"
        badge={
          !c.readiness.ready && c.readiness.reason ? (
            <div className="mt-2 border-l-2 border-l-yellow-500 bg-[#2d2d2d] px-3 py-1.5 text-[11px] text-yellow-300">
              <i className="codicon codicon-warning mr-1 !text-[12px]" />
              {c.readiness.reason}
            </div>
          ) : undefined
        }
        actions={
          <RunBtn
            running={c.running}
            disabled={!c.readiness.ready || c.running}
            onClick={handleRun}
          >
            {c.running ? '生成中…' : '生成 Word 报告'}
          </RunBtn>
        }
      />

      {/* 内容区：状态互斥（生成中 / 报错 / 成功 / 空态引导） */}
      <div className="min-h-0 flex-1 overflow-auto p-6">
        <StatusArea
          onOpen={openOutput}
          onReveal={revealOutput}
          onRetry={handleRun}
        />
      </div>
    </div>
  );
}

function StatusArea({
  onOpen,
  onReveal,
  onRetry,
}: {
  onOpen: () => void;
  onReveal: () => void;
  onRetry: () => void;
}) {
  const c = useReportGenerator();

  if (c.running) {
    return (
      <div className="text-vscode-text-dim flex h-full flex-col items-center justify-center gap-3 text-center">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[32px]" />
        <div className="text-sm">正在生成 Word 报告…</div>
        <div className="text-vscode-text-faint text-xs">
          读取数据 → 套用规范 → 填充模板，稍候
        </div>
      </div>
    );
  }

  if (c.runError) {
    return (
      <div className="space-y-2">
        <ErrorBanner message={c.runError} onRetry={onRetry} />
        <div className="text-vscode-text-faint text-[11px]">
          完整日志见底部「输出」面板（Ctrl+J）；修正右侧参数后可重试。
        </div>
        {c.wordTemplatePath && <TemplateCheckCard />}
      </div>
    );
  }

  if (c.lastResult) {
    return (
      <div className="rounded border border-l-2 border-l-green-500 bg-[#252525] p-4 text-xs">
        <div className="flex items-center gap-2 text-green-400">
          <i className="codicon codicon-pass !text-[16px]" />
          <span className="font-medium">生成成功：{c.lastResult.summary}</span>
        </div>
        <div className="text-vscode-text-dim mt-1 break-all">
          {c.lastResult.output}
        </div>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={onOpen}
            className="bg-vscode-button hover:bg-vscode-button-hover flex items-center gap-1 rounded-[2px] px-3 py-1 text-[11px] text-white"
          >
            <i className="codicon codicon-go-to-file !text-[11px]" />
            打开 docx
          </button>
          <button
            type="button"
            onClick={onReveal}
            className="text-vscode-text flex items-center gap-1 rounded-[2px] bg-[#3a3d41] px-3 py-1 text-[11px] hover:bg-[#4a4d51]"
          >
            <i className="codicon codicon-folder-opened !text-[11px]" />
            在资源管理器中显示
          </button>
        </div>
        {c.lastResult.unknownKeys.length > 0 && (
          <div className="mt-3 text-[11px] text-yellow-400">
            <i className="codicon codicon-warning mr-1 !text-[11px]" />
            模板里有 {c.lastResult.unknownKeys.length} 个未识别占位符：
            {c.lastResult.unknownKeys.join('、')}
          </div>
        )}
        {c.lastResult.missingImages.length > 0 && (
          <div className="mt-2 text-[11px] text-yellow-400">
            <i className="codicon codicon-warning mr-1 !text-[11px]" />
            {c.lastResult.missingImages.length} 个图片占位符未嵌入（路径不存在 /
            未配置曲线图目录）：
            {c.lastResult.missingImages.join('、')}
          </div>
        )}
      </div>
    );
  }

  // 已选模板：摆出「模板体检」（前置发现缺锚点 / 层级错 / 未识别占位符），
  // 而不是等点「生成」失败才知道。
  if (c.wordTemplatePath) {
    return <TemplateCheckCard />;
  }

  // 空态引导（还没选模板）
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <i className="codicon codicon-file-text text-vscode-text-faint !text-[48px]" />
      <div className="text-vscode-text-dim mt-3 text-sm">
        在右侧「调参」面板填好输入
      </div>
      <div className="text-vscode-text-faint mt-1 max-w-md text-xs leading-relaxed">
        先在「数据」tab 勾选检测类型（可多选：锚杆 /
        防火涂层），再依次填模板、项目字段， 就绪后点上方「生成 Word
        报告」。生成结果与报错都会显示在这里。
      </div>
    </div>
  );
}

/**
 * 模板体检卡 —— 选完 Word 模板后（生成前）摆出 template.validate 的结果，
 * 聚焦「这模板能不能出报告」：
 *   - 数据表占位符（{{表格:锚杆}} / {{表格:防火涂层}}）提醒 + 一键复制
 *   - 需修正（层级错配）/ 未识别占位符（生成时会留原文；表格占位符不计入）
 *   - 去模板助手看完整字段对照的指引
 *
 * 跟模板助手的完整审计分工：这里是下游「就绪检查」，模板助手是上游「字段编辑 + 全量审计」。
 */
function TemplateCheckCard() {
  const c = useReportGenerator();

  if (c.templateChecking && !c.templateCheck) {
    return (
      <div className="text-vscode-text-dim flex items-center gap-2 text-xs">
        <i className="codicon codicon-loading codicon-modifier-spin !text-[14px]" />
        正在体检模板…
      </div>
    );
  }

  if (c.templateCheckError) {
    return (
      <div className="rounded border border-l-2 border-l-red-500 bg-[#2a1d1d] p-3 text-xs text-red-300">
        <i className="codicon codicon-error mr-1 !text-[13px]" />
        模板体检失败：{c.templateCheckError}
        <div className="text-vscode-text-faint mt-1 text-[11px]">
          确认 .docx 没被 Word 占用 / 路径可读后重选模板。
        </div>
      </div>
    );
  }

  const tc = c.templateCheck;
  if (!tc) return null;

  // 数据表占位符（{{表格:xxx}}）不是 catalog 字段，会落在 unrecognized；这里单独识别，
  // 既不当成「未识别错误」，又能按报告类型提示用户该写哪个占位符。
  const isTablePh = (ph: string) =>
    ph.includes('表格:锚杆') || ph.includes('表格:防火涂层');
  const hasAnchorTable = tc.unrecognized.some((u) =>
    u.placeholder.includes('表格:锚杆'),
  );
  const hasCoatingTable = tc.unrecognized.some((u) =>
    u.placeholder.includes('表格:防火涂层'),
  );
  const fieldUnrecognized = tc.unrecognized.filter(
    (u) => !isTablePh(u.placeholder),
  );

  // 当前勾选的检测类型需要哪些数据表占位符（缺了生成会报错）
  const needAnchor = c.selectedTypes.includes('anchor');
  const needCoating = c.selectedTypes.includes('coating');
  const missingRequired: string[] = [];
  if (needAnchor && !hasAnchorTable)
    missingRequired.push(ANCHOR_TABLE_PLACEHOLDER);
  if (needCoating && !hasCoatingTable)
    missingRequired.push(COATING_TABLE_PLACEHOLDER);
  const allClear =
    missingRequired.length === 0 &&
    tc.hints.length === 0 &&
    fieldUnrecognized.length === 0;

  return (
    <div className="space-y-3 text-xs">
      {/* 标题行 + 状态 */}
      <div className="flex items-center gap-2">
        <i
          className={cn(
            'codicon !text-[15px]',
            allClear
              ? 'codicon-pass text-green-400'
              : 'codicon-warning text-yellow-400',
          )}
        />
        <span className="text-vscode-text font-medium">模板体检</span>
        <span className="text-vscode-text-faint text-[11px]">
          {allClear
            ? '模板就绪，可生成'
            : '生成前请看以下提示（已匹配 ' +
              tc.summary.matched_count +
              ' 字段）'}
        </span>
      </div>

      {/* 数据表占位符提醒 —— 按报告类型标注「需要 / 不需要」+ 是否已写 */}
      <div className="border-vscode-border space-y-1.5 rounded border bg-[#252525] p-2.5">
        <div className="text-vscode-text-dim leading-relaxed">
          数据表占位符（程序在此处按规范建表插入）：
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <TablePhChip
            label="锚杆"
            placeholder={ANCHOR_TABLE_PLACEHOLDER}
            need={needAnchor}
            present={hasAnchorTable}
          />
          <span className="text-vscode-text-faint">·</span>
          <TablePhChip
            label="防火涂层"
            placeholder={COATING_TABLE_PLACEHOLDER}
            need={needCoating}
            present={hasCoatingTable}
          />
        </div>
        {missingRequired.length > 0 && (
          <div className="text-[11px] text-yellow-300/90">
            模板缺少本报告类型需要的占位符：
            {missingRequired.map((ph) => (
              <code key={ph} className="mx-0.5 rounded bg-black/30 px-1">
                {ph}
              </code>
            ))}
            ——生成时会报「缺占位符」。点上方对应 chip 复制后粘到 Word
            要放表的位置，独占一段。
          </div>
        )}
      </div>

      {/* 需修正：层级错配等（hints） */}
      {tc.hints.length > 0 && (
        <div className="space-y-1">
          {tc.hints.map((h, i) => {
            const isError = h.severity === 'error';
            return (
              <div
                key={`${h.field_name}-${i}`}
                className={cn(
                  'flex items-start gap-2 rounded-[2px] border border-l-2 px-2 py-1',
                  isError
                    ? 'border-red-600/40 border-l-red-500 bg-[#2a1d1d]'
                    : 'border-yellow-600/40 border-l-yellow-500 bg-[#2a2620]',
                )}
              >
                <i
                  className={cn(
                    'codicon mt-0.5 shrink-0 !text-[12px]',
                    isError
                      ? 'codicon-error text-red-400'
                      : 'codicon-warning text-yellow-400',
                  )}
                />
                <div className="min-w-0">
                  <span
                    className={isError ? 'text-red-200' : 'text-yellow-200'}
                  >
                    {h.message}
                  </span>
                  <div className="text-vscode-text-faint mt-0.5 text-[11px]">
                    {h.location}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 未识别占位符：生成时会留原文（数据表 {{表格:xxx}} 已排除，不算错误） */}
      {fieldUnrecognized.length > 0 && (
        <div className="rounded-[2px] border border-l-2 border-yellow-600/40 border-l-yellow-500 bg-[#2a2620] px-2 py-1.5">
          <div className="text-yellow-200">
            <i className="codicon codicon-question mr-1 !text-[12px]" />
            {fieldUnrecognized.length} 个未识别占位符（生成时保留原文不替换）：
          </div>
          <div className="text-vscode-text-dim mt-1 flex flex-wrap gap-1.5">
            {fieldUnrecognized.map((u, i) => (
              <code
                key={`${u.placeholder}-${i}`}
                className="rounded bg-black/30 px-1 text-yellow-200"
                title={u.location}
              >
                {u.placeholder}
              </code>
            ))}
          </div>
        </div>
      )}

      <div className="text-vscode-text-faint text-[11px]">
        完整字段对照 / 编辑见 ActivityBar「模板助手」。
      </div>
    </div>
  );
}

/**
 * 数据表占位符状态 chip —— 按「本报告类型是否需要 + 模板里是否已写」着色：
 *   需要 + 已写 → 绿勾；需要 + 没写 → 黄警告；不需要 → 暗（标「不需要」）。
 * 附一键复制占位符文本。
 */
function TablePhChip({
  label,
  placeholder,
  need,
  present,
}: {
  label: string;
  placeholder: string;
  need: boolean;
  present: boolean;
}) {
  const color = !need
    ? 'text-vscode-text-faint'
    : present
      ? 'text-green-400'
      : 'text-yellow-300';
  const icon = !need
    ? 'codicon-circle-outline'
    : present
      ? 'codicon-check'
      : 'codicon-warning';
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn('inline-flex items-center gap-1', color)}>
        <i className={cn('codicon !text-[12px]', icon)} />
        {label}
        {!need && (
          <span className="text-vscode-text-faint text-[10px]">（不需要）</span>
        )}
      </span>
      <CopyChip text={placeholder} small />
    </span>
  );
}

/** 一键复制 marker 文本的小按钮，复制后短暂显示「已复制」。 */
function CopyChip({ text, small }: { text: string; small?: boolean }) {
  const [copied, setCopied] = useState(false);
  const onClick = useCallback(() => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'border-vscode-border inline-flex items-center gap-1 rounded border bg-[#252525] hover:bg-[#3a3a3a]',
        small ? 'px-1.5 py-0 text-[10px]' : 'px-2 py-0.5 text-[11px]',
      )}
      title={`复制 ${text}`}
    >
      <i
        className={cn(
          'codicon !text-[10px]',
          copied ? 'codicon-check text-green-400' : 'codicon-copy',
        )}
      />
      {copied ? '已复制' : <code>{text}</code>}
    </button>
  );
}
