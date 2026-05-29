/**
 * 统一弹窗系统 —— 取代全项目散落的 window.confirm / window.prompt / alert。
 *
 * 为什么要它：原生对话框在深色 IDE 风界面里弹系统白底框，割裂且不可样式化；
 * 而项目里同类操作（目录/预设 CRUD）已有精致内联弹窗，两套并存是 UX 不一致的大头。
 *
 * 用法（promise 化，调用点几乎零改造）：
 *   const dlg = useDialogs();
 *   const name = await dlg.prompt({ title: '新建曲线', label: '名字', defaultValue: '新曲线' });
 *   if (!name?.trim()) return;            // null = 用户取消
 *   if (!(await dlg.confirm({ message: '确定删除？', danger: true }))) return;
 *   await dlg.alert({ message: '保存失败', tone: 'error' });
 *
 * 挂载：main.tsx 在 <App/> 外层包一层 <DialogsProvider>，全树（含 App / FileTree / 各工具）可用。
 * 一次只显示一个弹窗（用户操作天然串行）；Esc 取消、Enter 确认、点遮罩取消。
 */
/* eslint-disable react-refresh/only-export-components -- hook(useDialogs) 与 Provider 同文件共存，与工具页 controller 范式一致 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { cn } from '../lib/cn';

type Tone = 'info' | 'error' | 'success';

interface ConfirmOpts {
  title?: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** true = 主按钮用红色（删除等不可逆操作）。 */
  danger?: boolean;
}

interface PromptOpts {
  title?: string;
  label?: React.ReactNode;
  defaultValue?: string;
  placeholder?: string;
  confirmLabel?: string;
  cancelLabel?: string;
}

interface AlertOpts {
  title?: string;
  message: React.ReactNode;
  tone?: Tone;
  okLabel?: string;
}

interface DialogsApi {
  /** 返回 true=确认 / false=取消。 */
  confirm: (opts: ConfirmOpts) => Promise<boolean>;
  /** 返回输入串（已是用户所填，未 trim）/ null=取消。 */
  prompt: (opts: PromptOpts) => Promise<string | null>;
  /** 仅告知，返回 void。 */
  alert: (opts: AlertOpts) => Promise<void>;
}

const DialogsContext = createContext<DialogsApi | null>(null);

export function useDialogs(): DialogsApi {
  const v = useContext(DialogsContext);
  if (!v) throw new Error('useDialogs 必须在 <DialogsProvider> 内调用');
  return v;
}

type Request =
  | { kind: 'confirm'; opts: ConfirmOpts; resolve: (v: boolean) => void }
  | { kind: 'prompt'; opts: PromptOpts; resolve: (v: string | null) => void }
  | { kind: 'alert'; opts: AlertOpts; resolve: () => void };

export function DialogsProvider({ children }: { children: React.ReactNode }) {
  const [req, setReq] = useState<Request | null>(null);

  const api = useMemo<DialogsApi>(
    () => ({
      confirm: (opts) =>
        new Promise<boolean>((resolve) =>
          setReq({ kind: 'confirm', opts, resolve }),
        ),
      prompt: (opts) =>
        new Promise<string | null>((resolve) =>
          setReq({ kind: 'prompt', opts, resolve }),
        ),
      alert: (opts) =>
        new Promise<void>((resolve) =>
          setReq({ kind: 'alert', opts, resolve }),
        ),
    }),
    [],
  );

  return (
    <DialogsContext.Provider value={api}>
      {children}
      {req && <DialogHost req={req} onClose={() => setReq(null)} />}
    </DialogsContext.Provider>
  );
}

const TONE_ICON: Record<Tone, { icon: string; color: string }> = {
  info: { icon: 'info', color: 'text-vscode-focus' },
  error: { icon: 'error', color: 'text-red-400' },
  success: { icon: 'pass', color: 'text-green-400' },
};

function DialogHost({ req, onClose }: { req: Request; onClose: () => void }) {
  const [draft, setDraft] = useState(
    req.kind === 'prompt' ? (req.opts.defaultValue ?? '') : '',
  );
  const inputRef = useRef<HTMLInputElement>(null);

  // 进场聚焦：prompt 选中输入框文本（方便直接改名）；其余聚焦无（Enter 走全局）
  useEffect(() => {
    if (req.kind === 'prompt') {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [req.kind]);

  const cancel = useCallback(() => {
    if (req.kind === 'confirm') req.resolve(false);
    else if (req.kind === 'prompt') req.resolve(null);
    else req.resolve();
    onClose();
  }, [req, onClose]);

  const promptEmpty = req.kind === 'prompt' && !draft.trim();

  const confirm = useCallback(() => {
    if (req.kind === 'confirm') req.resolve(true);
    else if (req.kind === 'prompt') {
      if (!draft.trim()) return; // 空输入不提交
      req.resolve(draft);
    } else req.resolve();
    onClose();
  }, [req, draft, onClose]);

  // 键盘：Esc 取消；Enter 确认（prompt 的 Enter 由输入框 onKeyDown 处理，避免重复）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        cancel();
      } else if (e.key === 'Enter' && req.kind !== 'prompt') {
        e.preventDefault();
        confirm();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [cancel, confirm, req.kind]);

  const title =
    req.opts.title ??
    (req.kind === 'confirm' ? '确认' : req.kind === 'prompt' ? '输入' : '提示');
  const danger = req.kind === 'confirm' && req.opts.danger;
  const tone: Tone = req.kind === 'alert' ? (req.opts.tone ?? 'info') : 'info';

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50"
      onClick={cancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="border-vscode-border w-[360px] max-w-[90vw] rounded border bg-[#252526] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="border-vscode-border flex items-center gap-2 border-b px-4 py-2.5">
          {req.kind === 'alert' && (
            <i
              className={cn(
                'codicon',
                `codicon-${TONE_ICON[tone].icon}`,
                TONE_ICON[tone].color,
                '!text-[15px]',
              )}
            />
          )}
          <span className="text-vscode-text text-[13px] font-medium">
            {title}
          </span>
        </div>

        {/* 正文 */}
        <div className="px-4 py-3 text-xs">
          {req.kind === 'confirm' && (
            <div className="text-vscode-text-dim leading-relaxed whitespace-pre-wrap">
              {req.opts.message}
            </div>
          )}
          {req.kind === 'alert' && (
            <div className="text-vscode-text-dim leading-relaxed whitespace-pre-wrap">
              {req.opts.message}
            </div>
          )}
          {req.kind === 'prompt' && (
            <>
              {req.opts.label && (
                <div className="text-vscode-text-dim mb-1.5">
                  {req.opts.label}
                </div>
              )}
              <input
                ref={inputRef}
                type="text"
                value={draft}
                placeholder={req.opts.placeholder}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    confirm();
                  }
                }}
                className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus w-full rounded-[2px] border px-2 py-1.5 text-xs focus:outline-none"
              />
            </>
          )}
        </div>

        {/* 按钮栏 */}
        <div className="flex items-center justify-end gap-2 px-4 pb-3">
          {req.kind !== 'alert' && (
            <button
              type="button"
              onClick={cancel}
              className="text-vscode-text-dim hover:text-vscode-text rounded-[2px] px-3 py-1 text-xs"
            >
              {req.opts.cancelLabel ?? '取消'}
            </button>
          )}
          <button
            type="button"
            onClick={confirm}
            disabled={promptEmpty}
            className={cn(
              'rounded-[2px] px-3 py-1 text-xs text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50',
              danger
                ? 'bg-red-700 hover:bg-red-600'
                : 'bg-vscode-button hover:bg-vscode-button-hover',
            )}
          >
            {req.kind === 'confirm'
              ? (req.opts.confirmLabel ?? '确定')
              : req.kind === 'prompt'
                ? (req.opts.confirmLabel ?? '确定')
                : (req.opts.okLabel ?? '知道了')}
          </button>
        </div>
      </div>
    </div>
  );
}
