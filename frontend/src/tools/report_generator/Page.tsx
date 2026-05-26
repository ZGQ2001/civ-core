/**
 * report_generator 主区 —— 装配线「报告填充」环节。
 *
 * 中间显示「输入摘要 + 生成按钮 + 结果 + 字段对照表 + 模板格式 cheat sheet」。
 * 真正的输入路径 / 模板路径 / 项目元信息 全在右侧 SettingsForm 填。
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
      shell.appendOutput(
        logLine(`[报告] 在资源管理器中显示失败: ${String(e)}`),
      );
    }
  }, [c.lastResult, shell]);

  return (
    <div className="flex h-full flex-col overflow-auto bg-[#1e1e1e]">
      <Header />
      <InputSummary />
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
        把锚杆抗拔数据 + 项目元信息填入 Word 模板出 docx。
        本工具独立可用——也可以一键从「数据处理」复用输入和工程参数（右侧调参栏顶部按钮）。
      </p>
    </div>
  );
}

// ── 输入摘要（本工具自身 state） ──────────────────────────

function InputSummary() {
  const c = useReportGenerator();

  return (
    <div className="border-vscode-border mx-6 mt-4 rounded-[3px] border bg-[#252525] p-3 text-xs">
      <div className="mb-2 flex items-center gap-2">
        <i className="codicon codicon-list-tree text-vscode-focus !text-[14px]" />
        <span className="text-vscode-text font-medium">输入摘要</span>
      </div>

      <Row
        label="输入 Excel"
        value={c.excelPath || '（未选）'}
        muted={!c.excelPath}
      />
      <Row label="Sheet" value={c.sheet || '（默认）'} muted={!c.sheet} />
      <Row label="规范" value={c.anchorStandard} />
      <Row label="批次列" value={c.anchorBatchIdColumn} />
      <Row
        label="批次清单"
        value={
          c.anchorBatchesLoading
            ? '加载中…'
            : c.anchorBatchesError
              ? `读取失败`
              : c.anchorBatchIds.length > 0
                ? `${c.anchorBatchIds.length} 批，参数已填 ${anchorParamsFilledCount(c)} / ${c.anchorBatchIds.length}`
                : '（无）'
        }
        muted={c.anchorBatchIds.length === 0}
      />
      <Row
        label="Word 模板"
        value={c.wordTemplatePath || '（未选）'}
        muted={!c.wordTemplatePath}
      />
      <Row
        label="输出目录"
        value={c.outputDir || '（自动，输入 Excel 同级）'}
        muted={!c.outputDir}
      />
      <Row
        label="曲线图目录"
        value={c.curveImageDir || '（未选 — {{img:曲线图}} 留原文）'}
        muted={!c.curveImageDir}
      />
    </div>
  );
}

function anchorParamsFilledCount(
  c: ReturnType<typeof useReportGenerator>,
): number {
  return c.anchorBatchIds.filter((b) => !!c.anchorParamsByBatch[b]).length;
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
        className={
          muted ? 'text-vscode-text-faint italic' : 'text-vscode-text break-all'
        }
      >
        {value}
      </span>
    </div>
  );
}

// ── 生成按钮 + 阻断原因 ─────────────────────────────────

function RunBar({ onRun }: { onRun: () => void }) {
  const c = useReportGenerator();
  const r = c.readiness;

  return (
    <div className="mx-6 mt-3">
      {!r.ready && r.reason && (
        <div className="border-l-2 border-l-yellow-500 bg-[#2d2d2d] px-3 py-2 text-[11px] text-yellow-300">
          <i className="codicon codicon-warning mr-1 !text-[12px]" />
          {r.reason}
        </div>
      )}
      <button
        type="button"
        onClick={onRun}
        disabled={!r.ready || c.running}
        className="bg-vscode-button hover:bg-vscode-button-hover mt-2 flex w-full items-center justify-center gap-2 rounded-[3px] px-4 py-2 text-[13px] text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
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
        <div className="mt-2 text-[11px] text-yellow-400">
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
        <i className="codicon codicon-question !text-[12px]" /> Word
        模板格式约定
      </summary>
      <div className="text-vscode-text-dim space-y-1.5 px-3 pb-3">
        <p>
          <span className="text-vscode-text">1. 占位符</span>：模板里写{' '}
          <code className="bg-[#1e1e1e] px-1">{'{{key}}'}</code> 或{' '}
          <code className="bg-[#1e1e1e] px-1">{'{{中文名}}'}</code>{' '}
          （都识别）。例：{'{{委托单位}}'} / {'{{锚杆编号}}'} /{' '}
          {'{{0.1Nt位移}}'}。
        </p>
        <p>
          <span className="text-vscode-text">2. 锚杆数据表克隆</span>
          ：要按每根锚杆重复的部分用一对锚点包起来：
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
          上下限默认 2 位小数；{'{{轴向拉力设计值}}'} 默认输出 kN（内部计算用
          N，引擎自动换算）。
        </p>
        <p>
          <span className="text-vscode-text">5. 图片占位符</span>：写{' '}
          <code className="bg-[#1e1e1e] px-1">{'{{img:曲线图}}'}</code> （img:
          前缀必须）。配合右栏「曲线图目录」选 plot_curves 出图文件夹
          （按锚杆编号命名 1.png / 2.png /...），引擎按 anchor_id 自动匹配嵌入。
          留空目录则占位符留原文 + 报 missingImages。
        </p>
      </div>
    </details>
  );
}
