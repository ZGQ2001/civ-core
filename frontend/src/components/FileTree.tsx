/**
 * FileTree：调 Python files.list_dir 渲染的递归文件树。
 *
 * 设计要点：
 *  - 懒加载：DirNode 第一次 expanded=true 时才发 RPC；entries 拉过一次后缓存在节点 state 里
 *  - 刷新/全部折叠：由外部传 refreshKey 触发整树重挂（FileTree 上的 key={refreshKey}）
 *    最简实现 —— 牺牲精细 expanded 状态保留，换最少状态机；后续真有痛点再换 context refetch
 *  - 双击文件：走 @tauri-apps/plugin-opener 的 openPath（系统默认程序）
 *  - 根目录默认展开一次，深层节点默认折叠
 */
import { useEffect, useState } from "react";
import { openPath } from "@tauri-apps/plugin-opener";

import { cn } from "../lib/cn";
import { rpc, type FileEntry } from "../lib/rpc";

interface Props {
  rootPath: string;
  /** 双击 .xlsx/.xls/.docx/.pdf 时调，用于把文件灌给当前工具 */
  onFileActivate?: (path: string) => void;
}

/** 可被「灌入工具」的扩展名集合。其他扩展走系统 openPath 原行为。 */
const TOOL_INPUT_EXTS = new Set([".xlsx", ".xls", ".docx", ".doc", ".pdf"]);

export function FileTree({ rootPath, onFileActivate }: Props) {
  const name = rootPath.split(/[\\/]/).filter(Boolean).pop() ?? rootPath;
  return (
    <div className="py-1 text-[13px] text-vscode-text">
      <DirNode
        path={rootPath}
        name={name}
        depth={0}
        defaultExpanded
        onFileActivate={onFileActivate}
      />
    </div>
  );
}

function DirNode({
  path,
  name,
  depth,
  defaultExpanded = false,
  onFileActivate,
}: {
  path: string;
  name: string;
  depth: number;
  defaultExpanded?: boolean;
  onFileActivate?: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [entries, setEntries] = useState<FileEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 展开后第一次加载 entries（之后缓存）
  useEffect(() => {
    if (!expanded || entries !== null || loading) return;
    setLoading(true);
    setError(null);
    rpc<{ entries: FileEntry[] }>("files.list_dir", { path })
      .then((r) => setEntries(r.entries))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [expanded, entries, loading, path]);

  return (
    <>
      <Row
        depth={depth}
        chevron={expanded ? "chevron-down" : "chevron-right"}
        icon={expanded ? "folder-opened" : "folder"}
        label={name}
        onClick={() => setExpanded((v) => !v)}
      />
      {expanded && (
        <>
          {loading && <Row depth={depth + 1} icon="loading~spin" label="加载中…" muted />}
          {error && <Row depth={depth + 1} icon="error" label={error} muted />}
          {entries?.length === 0 && (
            <Row depth={depth + 1} label="（空目录）" muted />
          )}
          {entries?.map((e) =>
            e.is_dir ? (
              <DirNode
                key={e.path}
                path={e.path}
                name={e.name}
                depth={depth + 1}
                onFileActivate={onFileActivate}
              />
            ) : (
              <FileNode
                key={e.path}
                path={e.path}
                name={e.name}
                depth={depth + 1}
                onFileActivate={onFileActivate}
              />
            ),
          )}
        </>
      )}
    </>
  );
}

function FileNode({
  path,
  name,
  depth,
  onFileActivate,
}: {
  path: string;
  name: string;
  depth: number;
  onFileActivate?: (path: string) => void;
}) {
  const ext = (() => {
    const idx = name.lastIndexOf(".");
    return idx > 0 ? name.slice(idx).toLowerCase() : "";
  })();
  const canActivate = !!onFileActivate && TOOL_INPUT_EXTS.has(ext);
  const tooltip = canActivate
    ? `双击：作为当前工具输入\n（按住 Shift 双击：用系统默认程序打开）`
    : `双击：用系统默认程序打开`;

  return (
    <Row
      depth={depth}
      icon={canActivate ? "file-symlink-file" : "file"}
      label={name}
      title={tooltip}
      onDoubleClick={(e) => {
        // Shift+双击 强制系统打开；普通双击优先灌给工具
        if (canActivate && !e?.shiftKey) {
          onFileActivate!(path);
        } else {
          openPath(path).catch((err) => console.error("openPath failed:", err));
        }
      }}
    />
  );
}

function Row({
  depth,
  chevron,
  icon,
  label,
  muted,
  title,
  onClick,
  onDoubleClick,
}: {
  depth: number;
  chevron?: string;
  icon?: string;
  label: string;
  muted?: boolean;
  title?: string;
  onClick?: () => void;
  onDoubleClick?: (e: React.MouseEvent) => void;
}) {
  // 缩进按 depth*12px 累加；chevron 占 16px 槽位即使没有也保留对齐
  return (
    <div
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      title={title}
      style={{ paddingLeft: depth * 12 + 4 }}
      className={cn(
        "flex h-[22px] items-center gap-1 pr-2 cursor-pointer select-none",
        "hover:bg-vscode-hover",
        muted && "cursor-default",
      )}
    >
      <i
        className={cn(
          "codicon !text-[12px] w-4 text-vscode-text-dim shrink-0",
          chevron && `codicon-${chevron}`,
        )}
      />
      {icon && (
        <i
          className={cn(
            "codicon !text-[14px] shrink-0",
            `codicon-${icon}`,
            muted ? "text-vscode-text-dim" : "text-vscode-text",
          )}
        />
      )}
      <span className={cn("truncate", muted && "text-vscode-text-dim")}>{label}</span>
    </div>
  );
}
