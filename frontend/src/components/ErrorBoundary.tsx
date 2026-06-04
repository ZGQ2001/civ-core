/**
 * 全局/局部错误边界 —— 捕 React 渲染期未捕获异常，避免整页白屏不可恢复。
 *
 * 此前全项目零 Error Boundary：任一工具页或共享组件渲染抛错 → 整个 App 白屏，用户无路可退。
 * 契合本项目「程序不能是黑盒」：崩溃时显式呈现错误消息 + 组件栈（可追溯），并给「重试渲染 /
 * 重载应用」两条恢复路径，而非静默白屏。
 *
 * React 错误边界目前只能用 class 组件实现（getDerivedStateFromError / componentDidCatch），
 * 这里自写一个，不引第三方依赖。
 */
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** 边界标识（如工具名）；多处复用时标明是哪块崩了，也用于 fallback 标题。 */
  label?: string;
}

interface State {
  error: Error | null;
  componentStack: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, componentStack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 不静默吞：错误进 console（devtools 可查），含组件栈，便于追溯定位。
    const tag = this.props.label
      ? `[ErrorBoundary ${this.props.label}]`
      : '[ErrorBoundary]';
    console.error(tag, error, info.componentStack);
    this.setState({ componentStack: info.componentStack ?? null });
  }

  private reset = () => this.setState({ error: null, componentStack: null });
  private reload = () => location.reload();

  render() {
    const { error, componentStack } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="flex h-full w-full items-center justify-center overflow-auto bg-[#1e1e1e] p-6">
        <div
          role="alert"
          className="border-vscode-border text-vscode-text w-full max-w-2xl rounded border border-l-2 border-l-red-400 bg-[#2d2d2d] p-4 text-xs"
        >
          <div className="flex items-center gap-2 text-sm text-red-400">
            <i className="codicon codicon-error !text-[16px]" />
            <span className="font-medium">
              {this.props.label ? `${this.props.label} 出错了` : '应用出错了'}
            </span>
          </div>
          <div className="mt-2 whitespace-pre-wrap text-red-300">
            {error.message || String(error)}
          </div>
          {componentStack && (
            <details className="text-vscode-text-dim mt-2">
              <summary className="cursor-pointer select-none">
                组件栈（排查用）
              </summary>
              <pre className="mt-1 max-h-48 overflow-auto text-[11px] whitespace-pre-wrap">
                {componentStack}
              </pre>
            </details>
          )}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={this.reset}
              className="border-vscode-border text-vscode-text hover:bg-vscode-hover flex items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-[11px] hover:text-white"
            >
              <i className="codicon codicon-refresh !text-[11px]" />
              重试
            </button>
            <button
              type="button"
              onClick={this.reload}
              className="border-vscode-border text-vscode-text hover:bg-vscode-hover flex items-center gap-1 rounded-[2px] border bg-[#2d2d2d] px-2 py-1 text-[11px] hover:text-white"
            >
              <i className="codicon codicon-refresh !text-[11px]" />
              重载应用
            </button>
          </div>
        </div>
      </div>
    );
  }
}
