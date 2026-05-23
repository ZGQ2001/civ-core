/**
 * AgentPanel：右侧 AI 助手 tab 的占位。
 *
 * 将来这里挂一个常驻 agent，能：
 *  - 看到当前激活工具 + 工作区状态（通过 context / prop）
 *  - 对话式调用 RPC（"帮我把这个 Excel 跑一下 plot_curves"）
 *  - 出图后给出文字解读
 *
 * 当前只是占位 + UX 说明，避免 RightPanel 在没工具调参时整个空着。
 */
export function AgentPanel() {
  return (
    <div className="flex h-full flex-col gap-3 p-4 text-xs">
      <div className="text-vscode-text flex items-center gap-2">
        <i className="codicon codicon-hubot !text-[16px]" />
        <span className="font-medium">AI 助手（开发中）</span>
      </div>
      <p className="text-vscode-text-dim leading-relaxed">
        这里将常驻一个能感知当前工具 + 工作区的 AI 助手，未来支持：
      </p>
      <ul className="text-vscode-text-dim list-disc space-y-1 pl-5 leading-relaxed">
        <li>对话式调用工具（"用预设 X 跑一下这份 Excel"）</li>
        <li>出图后对结果做文字解读 / 异常诊断</li>
        <li>根据上下文推荐预设、规范条文</li>
      </ul>
      <div className="border-vscode-border mt-auto border-t pt-3">
        <div className="text-vscode-text-faint italic">
          切换到上方「调参」tab 可调整当前工具的参数。
        </div>
      </div>
    </div>
  );
}
