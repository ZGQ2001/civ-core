/**
 * BottomPanel：VSCode 风底部面板（当前只放"输出"Tab）。
 *
 * 设计变更（2026-05-21）：工具调参面板从这里挪到了右侧 RightPanel。
 * 底部 Panel 现在专用于"输出/日志"，后续可加"问题/终端"等运行时信息。
 *
 * 显隐由外部（App）控制 panelRef.collapse/expand；这里只渲染内容。
 *
 * 自动滚动：output 增长时自动跟随到底；用户手动上滚查历史时暂停跟随，
 * 等用户重新滚回底部（或离底部 32px 内）后再恢复。
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';

interface Props {
  output: string;
  /** 折叠按钮：collapse 自身 */
  onClose: () => void;
}

/** 距离底部多少像素以内算"贴底"。给一点容差，避免子像素滚动误判。 */
const STICK_TO_BOTTOM_THRESHOLD = 32;

export function BottomPanel({ output, onClose }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [stuckToBottom, setStuckToBottom] = useState(true);

  // output 变化时，若用户当前贴底就自动滚到底部
  // useLayoutEffect 而非 useEffect：确保在浏览器绘制前完成滚动，肉眼看不到"瞬移"
  useLayoutEffect(() => {
    if (!stuckToBottom) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [output, stuckToBottom]);

  // 监听滚动事件，更新 stuckToBottom：离底部 <= 32px 视为贴底
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const distanceFromBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight;
      setStuckToBottom(distanceFromBottom <= STICK_TO_BOTTOM_THRESHOLD);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  const jumpToBottom = () => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    setStuckToBottom(true);
  };

  return (
    <div className="bg-vscode-bg border-vscode-border flex h-full min-h-0 flex-col border-t">
      <div className="border-vscode-border flex h-9 shrink-0 items-center border-b px-2">
        <div className="border-vscode-focus flex h-9 items-center gap-1.5 border-b-2 px-3 text-[11px] tracking-wider text-white uppercase">
          <i className="codicon codicon-output !text-[12px]" />
          输出
        </div>
        <div className="ml-auto flex items-center gap-1">
          {!stuckToBottom && output && (
            <button
              type="button"
              title="跳到最新（恢复自动滚动）"
              onClick={jumpToBottom}
              className="text-vscode-text-dim hover:bg-vscode-hover flex h-6 items-center gap-1 rounded-[3px] px-2 text-[11px] hover:text-white"
            >
              <i className="codicon codicon-arrow-down !text-[12px]" />
              最新
            </button>
          )}
          <button
            type="button"
            title="收起面板 (Ctrl+J)"
            onClick={onClose}
            className="text-vscode-text-dim hover:bg-vscode-hover flex h-6 w-6 items-center justify-center rounded-[3px] hover:text-white"
          >
            <i className="codicon codicon-chevron-down !text-[14px]" />
          </button>
        </div>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-auto">
        <pre className="text-vscode-text min-h-full p-3 font-mono text-[12px] break-words whitespace-pre-wrap">
          {output || (
            <span className="text-vscode-text-faint italic">
              （暂无输出。运行工具后这里会显示日志摘要。）
            </span>
          )}
        </pre>
      </div>
    </div>
  );
}
