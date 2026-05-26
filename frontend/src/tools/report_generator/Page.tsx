/**
 * report_generator 主区 —— 装配线「报告填充」环节。
 *
 * 中间显示「能不能生成 + 上游摘要 + 生成按钮 + 结果 + 字段对照表」。
 * 真正的 Word 模板路径 / 项目元信息 / 输出目录 全在右侧 SettingsForm 填。
 */
import { useCallback, useState } from 'react';
import { openPath, revealItemInDir } from '@tauri-apps/plugin-opener';

import { rpc } from '../../lib/rpc';
import { logLine, useShell } from '../../lib/shell';
import { useReportGenerator } from './controller';

interface FieldInfo {
  key: string;
  name: string;
  source: string;
}

const SOURCE_LABEL: Record<string, string> = {
  parameter: '工程参数',
  rawinput: '原始数据（每根锚杆）',
  calculated: '计算结果（每根锚杆）',
  userinput: '用户输入（项目级）',
};

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
      appendOutput?.(`完成：${res.rowsRendered} 根 → ${res.output}`);
    } else if (c.runError) {
      appendOutput?.(`错误：${c.runError}`);
    }
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
      shell.appendOutput(logLine(`[报告] 在资源管理器中显示失败: ${String(e)}`));
    }
  }, [c.lastResult, shell]);

  return (
    <div className="flex h-full flex-col overflow-auto bg-[#1e1e1e]">
      <Header />
      <UpstreamSummary />
      <RunBar onRun={handleRun} />
      <ResultBlock onOpen={openOutput} onReveal={revealOutput} />
      <FieldCatalogBlock />
      <TemplateHelpBlock />
    </div>
  );
}

// ── 顶部标题 ────────────────────────────────────────────

function Header() {
  return (
    <div className="border-vscode-border bg-[#252526] px-6 pt-4 pb-3">
      <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
        <i className="codicon codicon-file-text !text-[16px]" />
        报告填充
      </h1>
      <p className="text-vscode-text-dim mt-1 text-xs">
        把数据处理算好的结果 + 项目元信息填入 Word 模板。
        Excel 输入和工程参数从「数据处理」工具页继承——不用重新填。
      </p>
    </div>
  );
}

// ── 上游 (data_processing) 状态摘要 ──────────────────────

function UpstreamSummary() {
  const c = useReportGenerator();
  const u = c.upstream;

  return (
    <div className="border-vscode-border mx-6 mt-4 rounded-[3px] border bg-[#252525] p-3 text-xs">
      <div className="mb-2 flex items-center gap-2">
        <i className="codicon codicon-symbol-method text-vscode-focus !text-[14px]" />
        <span className="text-vscode-text font-medium">来自数据处理</span>
      </div>

      <Row label="输入 Excel" value={u.excelPath || '（未选）'} muted={!u.excelPath} />
      <Row label="Sheet" value={u.sheet || '（默认）'} muted={!u.sheet} />
      <Row label="规范" value={u.standard} />
      <Row label="批次列" value={u.batchCol} />
      <Row
        label="批次清单"
        value={
          u.batchCount > 0
            ? `${u.batchCount} 批，已填参数 ${u.paramsFilledBatchCount} / ${u.batchCount}`
            : '（无）'
        }
        muted={u.batchCount === 0}
      />
    </div>
  );
}

function Row({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div className="flex gap-3 py-0.5">
      <span className="text-vscode-text-dim w-[88px] shrink-0">{label}</span>
      <span
        className={muted ? 'text-vscode-text-faint italic' : 'text-vscode-text break-all'}
      >
        {value}
      </span>
    </div>
  );
}

// ── 生成按钮 + 阻断原因 ─────────────────────────────────

function RunBar({ onRun }: { onRun: () => void }) {
  const c = useReportGenerator();
  const u = c.upstream;

  return (
    <div className="mx-6 mt-3">
      {!u.ready && u.blockReason && (
        <div className="border-l-2 border-l-yellow-500 bg-[#2d2d2d] px-3 py-2 text-[11px] text-yellow-300">
          <i className="codicon codicon-warning mr-1 !text-[12px]" />
          {u.blockReason}
        </div>
      )}
      <button
        type="button"
        onClick={onRun}
        disabled={!u.ready || c.running}
        className="mt-2 flex w-full items-center justify-center gap-2 rounded-[3px] bg-vscode-button px-4 py-2 text-[13px] text-white transition-colors hover:bg-vscode-button-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        {c.running ? (
          <i className="codicon codicon-loading codicon-modifier-spin !text-[14px]" />
        ) : (
          <i className="codicon codicon-play !text-[14px]" />
        )}
        {c.running ? '生成中…' : '生成 Word 报告'}
      </button>
    </div>
  );
}

// ── 结果块 ──────────────────────────────────────────────

function ResultBlock({
  onOpen,
  onReveal,
}: {
  onOpen: () => void;
  onReveal: () => void;
}) {
  const c = useReportGenerator();

  if (c.runError) {
    return (
      <div className="m-6 mt-3 rounded border border-l-2 border-l-red-400 bg-[#2d2d2d] p-3 text-xs whitespace-pre-wrap text-red-400">
        <i className="codicon codicon-error mr-1 !text-[14px]" />
        生成失败：{c.runError}
      </div>
    );
  }
  if (!c.lastResult) return null;
  return (
    <div className="m-6 mt-3 rounded border border-l-2 border-l-green-500 bg-[#252525] p-3 text-xs">
      <div className="flex items-center gap-2 text-green-400">
        <i className="codicon codicon-pass !text-[14px]" />
        <span className="font-medium">
          生成成功：{c.lastResult.rowsRendered} 根锚杆
        </span>
      </div>
      <div className="text-vscode-text-dim mt-1 break-all">
        {c.lastResult.output}
      </div>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="flex items-center gap-1 rounded-[2px] bg-vscode-button px-3 py-1 text-[11px] text-white hover:bg-vscode-button-hover"
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
        <div className="mt-2 text-[11px] text-yellow-400">
          <i className="codicon codicon-warning mr-1 !text-[11px]" />
          模板里有 {c.lastResult.unknownKeys.length} 个未识别占位符：
          {c.lastResult.unknownKeys.join('、')}
        </div>
      )}
    </div>
  );
}

// ── 字段对照表（可折叠） ────────────────────────────────

function FieldCatalogBlock() {
  const shell = useShell();
  const [expanded, setExpanded] = useState(false);
  const [fields, setFields] = useState<FieldInfo[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (fields) {
      setExpanded((v) => !v);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await rpc<{ fields: FieldInfo[] }>('template.fields', {
        project_type: 'anchor',
      });
      setFields(res.fields);
      setExpanded(true);
    } catch (e) {
      const msg = String(e);
      setError(msg);
      shell.appendOutput(logLine(`[报告] 加载字段清单失败: ${msg}`));
    } finally {
      setLoading(false);
    }
  }, [fields, shell]);

  return (
    <div className="mx-6 mt-3 mb-2">
      <button
        type="button"
        onClick={load}
        disabled={loading}
        className="text-vscode-focus flex items-center gap-1 text-xs hover:underline disabled:opacity-60"
      >
        {loading ? (
          <i className="codicon codicon-loading codicon-modifier-spin !text-[12px]" />
        ) : (
          <i
            className={`codicon codicon-chevron-${expanded ? 'down' : 'right'} !text-[12px]`}
          />
        )}
        <i className="codicon codicon-list-unordered !text-[12px]" />
        模板可用占位符清单（{fields?.length ?? '?'} 个）
      </button>
      {error && (
        <div className="mt-1 text-[11px] text-red-400">加载失败：{error}</div>
      )}
      {expanded && fields && (
        <div className="border-vscode-border mt-2 max-h-[280px] overflow-auto rounded-[2px] border bg-[#1e1e1e] px-3 py-2 text-[11px]">
          {['parameter', 'rawinput', 'calculated', 'userinput'].map((src) => {
            const group = fields.filter((f) => f.source === src);
            if (group.length === 0) return null;
            return (
              <div key={src} className="mt-1.5 first:mt-0">
                <div className="text-vscode-text-dim text-[10px] tracking-wider uppercase">
                  {SOURCE_LABEL[src] ?? src}（{group.length}）
                </div>
                <div className="mt-1 grid grid-cols-1 gap-x-3 md:grid-cols-2">
                  {group.map((f) => (
                    <div
                      key={f.key}
                      className="text-vscode-text flex items-baseline gap-2 py-0.5"
                    >
                      <code className="text-vscode-focus shrink-0">{`{{${f.key}}}`}</code>
                      <span className="text-vscode-text-dim truncate">
                        {f.name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── 模板格式 cheat sheet ───────────────────────────────

function TemplateHelpBlock() {
  return (
    <details className="border-vscode-border mx-6 my-3 rounded border bg-[#252525] text-xs">
      <summary className="text-vscode-text-dim cursor-pointer px-3 py-2 hover:text-white">
        <i className="codicon codicon-question !text-[12px]" /> Word 模板格式约定
      </summary>
      <div className="text-vscode-text-dim space-y-1.5 px-3 pb-3">
        <p>
          <span className="text-vscode-text">1. 占位符</span>：模板里写{' '}
          <code className="bg-[#1e1e1e] px-1">{'{{key}}'}</code> 或{' '}
          <code className="bg-[#1e1e1e] px-1">{'{{中文名}}'}</code>{' '}
          （都识别）。例：{'{{委托单位}}'} / {'{{锚杆编号}}'} / {'{{0.1Nt位移}}'}。
        </p>
        <p>
          <span className="text-vscode-text">2. 锚杆数据表克隆</span>：要按每根锚杆重复的部分用一对锚点包起来：
        </p>
        <pre className="bg-[#1e1e1e] px-2 py-1 text-[10px]">{`[[每根锚杆]]
表2.4-{{锚杆序号}}  {{检测项目}}结果表
（含 {{锚杆编号}}/{{0.1Nt位移}} 等的数据表）
[[/每根锚杆]]`}</pre>
        <p>
          <span className="text-vscode-text">3. 锚点段落</span>必须独占一段，
          不能放在表格单元格内。生成后 marker 段会被删掉，最终 docx 看不到。
        </p>
        <p>
          <span className="text-vscode-text">4. 数值格式</span>：弹性位移量 /
          上下限默认 2 位小数（catalog 里的 default_format 控制）。
        </p>
        <p>
          <span className="text-vscode-text">5. {'{{曲线图}}'}</span>{' '}
          当前是文本占位符；Commit 3 接入 plot_curves 后会自动嵌入 PNG。
        </p>
      </div>
    </details>
  );
}
