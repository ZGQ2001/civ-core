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
}

export function FileTree({ rootPath }: Props) {
  const name = rootPath.split(/[\\/]/).filter(Boolean).pop() ?? rootPath;
  return (
    <div className="py-1 text-[13px] text-vscode-text">
      <DirNode path={rootPath} name={name} depth={0} defaultExpanded />
    </div>
  );
}

function DirNode({
  path,
  name,
  depth,
  defaultExpanded = false,
}: {
  path: string;
  name: string;
  depth: number;
  defaultExpanded?: boolean;
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
              <DirNode key={e.path} path={e.path} name={e.name} depth={depth + 1} />
            ) : (
              <FileNode key={e.path} path={e.path} name={e.name} depth={depth + 1} />
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
}: {
  path: string;
  name: string;
  depth: number;
}) {
  return (
    <Row
      depth={depth}
      icon="file"
      label={name}
      onDoubleClick={() => {
        openPath(path).catch((e) => console.error("openPath failed:", e));
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
  onClick,
  onDoubleClick,
}: {
  depth: number;
  chevron?: string;
  icon?: string;
  label: string;
  muted?: boolean;
  onClick?: () => void;
  onDoubleClick?: () => void;
}) {
  // 缩进按 depth*12px 累加；chevron 占 16px 槽位即使没有也保留对齐
  return (
    <div
      onClick={onClick}
      onDoubleClick={onDoubleClick}
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
