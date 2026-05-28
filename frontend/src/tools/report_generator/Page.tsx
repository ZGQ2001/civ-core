/**
 * report_generator 主区 —— 装配线「报告填充」环节。
 *
 * 布局合并：输入参数 + 生成按钮 + 结果全在正中一页，不再依赖右侧 Panel。
 * 上半部分：输入配置（从 SettingsForm 整合进来）
 * 下半部分：生成按钮 + 结果 + 参考信息
 */
import { useCallback } from 'react';
import { openPath, revealItemInDir } from '@tauri-apps/plugin-opener';

import { logLine, useShell } from '../../lib/shell';
import { ReportGeneratorSettingsForm } from './SettingsForm';
import { useReportGenerator } from './controller';

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
    <div className="flex h-full flex-col bg-[#1e1e1e]">
      {/* 固定顶栏：标题 + 就绪态徽章 + 生成按钮（不跟随内容滚动） */}
      <div className="border-vscode-border flex shrink-0 items-start gap-3 border-b bg-[#252526] px-6 py-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-vscode-text flex items-center gap-2 text-base font-medium">
            <i className="codicon codicon-file-text !text-[16px]" />
            报告填充
          </h1>
          <p className="text-vscode-text-dim mt-1 text-xs">
            把检测数据 + 项目元信息填入 Word 模板出 docx。
          </p>
          {!c.readiness.ready && c.readiness.reason && (
            <div className="mt-2 border-l-2 border-l-yellow-500 bg-[#2d2d2d] px-3 py-1.5 text-[11px] text-yellow-300">
              <i className="codicon codicon-warning mr-1 !text-[12px]" />
              {c.readiness.reason}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={!c.readiness.ready || c.running}
          className="bg-vscode-button hover:bg-vscode-button-hover flex shrink-0 items-center justify-center gap-2 self-start rounded-[3px] px-4 py-2 text-[13px] text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        >
          {c.running ? (
            <i className="codicon codicon-loading codicon-modifier-spin !text-[14px]" />
          ) : (
            <i className="codicon codicon-play !text-[14px]" />
          )}
          {c.running ? '生成中…' : '生成 Word 报告'}
        </button>
      </div>

      {/* 滚动内容区：参数表 + 结果 */}
      <div className="min-h-0 flex-1 overflow-auto">
        <ReportGeneratorSettingsForm />
        <ResultBlock onOpen={openOutput} onReveal={revealOutput} />
      </div>
    </div>
  );
}

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
