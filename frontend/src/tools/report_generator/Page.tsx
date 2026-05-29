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
import { useCallback } from 'react';
import { openPath, revealItemInDir } from '@tauri-apps/plugin-opener';

import { logLine, useShell } from '../../lib/shell';
import { ErrorBanner, RunBtn, ToolHeader } from '../_shared/forms';
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
      </div>
    );
  }

  if (c.lastResult) {
    return (
      <div className="rounded border border-l-2 border-l-green-500 bg-[#252525] p-4 text-xs">
        <div className="flex items-center gap-2 text-green-400">
          <i className="codicon codicon-pass !text-[16px]" />
          <span className="font-medium">
            生成成功：{c.lastResult.rowsRendered} 根锚杆
          </span>
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

  // 空态引导
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <i className="codicon codicon-file-text text-vscode-text-faint !text-[48px]" />
      <div className="text-vscode-text-dim mt-3 text-sm">
        在右侧「调参」面板填好输入
      </div>
      <div className="text-vscode-text-faint mt-1 max-w-md text-xs leading-relaxed">
        依次填「数据」「模板」「项目字段」三个 tab，就绪后点上方「生成 Word
        报告」。生成结果与报错都会显示在这里。
      </div>
    </div>
  );
}
