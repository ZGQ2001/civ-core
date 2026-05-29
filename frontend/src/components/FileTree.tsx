/**
 * FileTree：VSCode 风格的文件树。
 *
 * 设计要点：
 *  - 扁平渲染：所有节点元信息（isDir/name/parent/expanded/entries 等）汇总到顶层
 *    Map<path, NodeState>；从根做 DFS 得到 visible rows 扁平数组直接 map 渲染。
 *    这样键盘导航 / 选中态 / 右键菜单 / in-place 编辑 都好挂。
 *  - 懒加载：目录首次展开时 RPC 拉 entries；同时把子节点元信息注册到 nodes。
 *  - 聚焦自动刷新：window focus → 静默 refetch 所有展开目录。
 *  - refetch 后 diff：被删除的子节点从 nodes 移除（连带丢失其展开/缓存）；新增的初始化。
 *  - in-place 编辑：选中行（重命名）或目录展开下首行（新建）渲染 input；Enter 提交 / Esc 取消。
 *  - 右键菜单：自定义 ContextMenu 浮层；外部点击/Esc 关闭。
 *  - 剪贴板：纯前端 state（path + copy/cut），粘贴时调 RPC files.copy / files.move。
 *  - 删除走回收站（后端 send2trash）。
 *
 * 不可变约束：
 *  - 所有文件系统操作走 Python RPC（files.*），前端不直接碰文件
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { openPath } from '@tauri-apps/plugin-opener';

import { cn } from '../lib/cn';
import { rpc, type FileEntry } from '../lib/rpc';
import { useDialogs } from './Dialogs';

// ──────────────────────────────────────────────────────────────────────────────
// 类型
// ──────────────────────────────────────────────────────────────────────────────

interface NodeState {
  /** 元信息（节点首次出现在某父节点的 entries 时初始化） */
  isDir: boolean;
  name: string;
  parent: string | null; // 根节点 null
  /** 仅目录有效 */
  entries: FileEntry[] | null;
  loading: boolean;
  error: string | null;
  expanded: boolean;
  isNew?: boolean;
}

interface RenderRow {
  path: string;
  name: string;
  isDir: boolean;
  depth: number;
  expanded: boolean;
  /** 选中时高亮 */
  selected: boolean;
  isNew?: boolean;
}

type EditState =
  | { kind: 'rename'; path: string; initialValue: string }
  | { kind: 'create'; parent: string; isDir: boolean }
  | null;

interface ClipboardState {
  path: string;
  mode: 'copy' | 'cut';
}

interface MenuState {
  x: number;
  y: number;
  /** 右键的目标节点 path；null = 在空白区右键，目标 = 根目录 */
  target: string | null;
}

interface TreeCtx {
  rootPath: string;
  nodes: Map<string, NodeState>;
  visibleRows: RenderRow[];
  selectedPath: string | null;
  editing: EditState;
  clipboard: ClipboardState | null;
  // actions
  toggle(path: string): void;
  select(path: string): void;
  activate(path: string, shift: boolean): void;
  beginRename(path: string): void;
  beginCreate(parent: string, isDir: boolean): void;
  commitEdit(value: string): void;
  cancelEdit(): void;
  doDelete(path: string): void;
  doUndoDelete(): void;
  undoStack: number[];
  doCopyToClipboard(path: string): void;
  doCutToClipboard(path: string): void;
  doPaste(targetDir: string): void;
  doCopyPath(path: string): void;
  doReveal(path: string): void;
  openMenu(e: React.MouseEvent, target: string | null): void;
}

const Ctx = createContext<TreeCtx | null>(null);

// ──────────────────────────────────────────────────────────────────────────────
// 常量 / 工具
// ──────────────────────────────────────────────────────────────────────────────

const TOOL_INPUT_EXTS = new Set(['.xlsx', '.xls', '.docx', '.doc', '.pdf']);

function getFileIcon(name: string): { icon: string; colorClass: string } {
  const idx = name.lastIndexOf('.');
  const ext = idx > 0 ? name.slice(idx + 1).toLowerCase() : '';
  switch (ext) {
    case 'xlsx':
    case 'xls':
    case 'xlsm':
    case 'csv':
      return { icon: 'table', colorClass: 'text-green-400' };
    case 'docx':
    case 'doc':
      return { icon: 'file', colorClass: 'text-blue-400' };
    case 'pdf':
      return { icon: 'file-pdf', colorClass: 'text-red-400' };
    case 'json':
    case 'yaml':
    case 'yml':
    case 'toml':
      return { icon: 'json', colorClass: 'text-yellow-400' };
    case 'md':
      return { icon: 'markdown', colorClass: 'text-blue-300' };
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'bmp':
    case 'svg':
    case 'webp':
      return { icon: 'file-media', colorClass: 'text-purple-300' };
    case 'zip':
    case 'rar':
    case '7z':
    case 'tar':
    case 'gz':
      return { icon: 'file-zip', colorClass: 'text-yellow-500' };
    case 'py':
    case 'ts':
    case 'tsx':
    case 'js':
    case 'jsx':
    case 'cs':
    case 'rs':
      return { icon: 'file-code', colorClass: 'text-cyan-400' };
    case 'txt':
    case 'log':
      return { icon: 'file', colorClass: 'text-vscode-text-dim' };
    default:
      return { icon: 'file', colorClass: 'text-vscode-text' };
  }
}

/** 拆名字为 stem / ext（含点）。foo.xlsx → ["foo", ".xlsx"]；foo → ["foo", ""] */
function splitName(name: string): [string, string] {
  const idx = name.lastIndexOf('.');
  if (idx <= 0) return [name, ''];
  return [name.slice(0, idx), name.slice(idx)];
}

function buildVisibleRows(
  rootPath: string,
  nodes: Map<string, NodeState>,
  selectedPath: string | null,
): RenderRow[] {
  const rows: RenderRow[] = [];
  const walk = (path: string, depth: number): void => {
    const s = nodes.get(path);
    if (!s) return;
    rows.push({
      path,
      name: s.name,
      isDir: s.isDir,
      depth,
      expanded: s.expanded,
      selected: path === selectedPath,
      isNew: s.isNew,
    });
    if (s.isDir && s.expanded && s.entries) {
      for (const e of s.entries) walk(e.path, depth + 1);
    }
  };
  walk(rootPath, 0);
  return rows;
}

function rootName(rootPath: string): string {
  return rootPath.split(/[\\/]/).filter(Boolean).pop() ?? rootPath;
}

// ──────────────────────────────────────────────────────────────────────────────
// 主组件
// ──────────────────────────────────────────────────────────────────────────────

interface Props {
  rootPath: string;
  /** 变化时：refetch 所有展开目录 */
  refreshNonce?: number;
  /** 变化时：折叠所有非根节点 */
  collapseNonce?: number;
  /** 双击 .xlsx/.docx/.pdf 时上抛 */
  onFileActivate?: (path: string) => void;
}

export function FileTree({
  rootPath,
  refreshNonce,
  collapseNonce,
  onFileActivate,
}: Props) {
  const [nodes, setNodes] = useState<Map<string, NodeState>>(() => {
    const m = new Map<string, NodeState>();
    m.set(rootPath, {
      isDir: true,
      name: rootName(rootPath),
      parent: null,
      entries: null,
      loading: false,
      error: null,
      expanded: true,
    });
    return m;
  });
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditState>(null);
  const [clipboard, setClipboard] = useState<ClipboardState | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [undoStack, setUndoStack] = useState<number[]>([]);
  const [opBusy, setOpBusy] = useState(false);
  const dlg = useDialogs();

  // refs：让 effect/callback 拿到最新值而不污染 deps
  const nodesRef = useRef(nodes);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);
  const selectedRef = useRef(selectedPath);
  useEffect(() => {
    selectedRef.current = selectedPath;
  }, [selectedPath]);

  const containerRef = useRef<HTMLDivElement>(null);

  // 可见行（用于键盘 ↑↓ 导航 & 渲染）
  const visibleRows = useMemo(
    () => buildVisibleRows(rootPath, nodes, selectedPath),
    [rootPath, nodes, selectedPath],
  );
  const visibleRowsRef = useRef(visibleRows);
  useEffect(() => {
    visibleRowsRef.current = visibleRows;
  }, [visibleRows]);

  // ─── 低层操作 ──────────────────────────────────────────────────────────

  const patchNode = useCallback((path: string, partial: Partial<NodeState>) => {
    setNodes((m) => {
      const prev = m.get(path);
      if (!prev) return m;
      const next = new Map(m);
      next.set(path, { ...prev, ...partial });
      return next;
    });
  }, []);

  const fetchDir = useCallback(
    async (path: string) => {
      patchNode(path, { loading: true, error: null });
      try {
        const r = await rpc<{ entries: FileEntry[] }>('files.list_dir', {
          path,
        });
        setNodes((m) => {
          const cur = m.get(path);
          if (!cur) return m;
          const next = new Map(m);
          next.set(path, {
            ...cur,
            entries: r.entries,
            loading: false,
            error: null,
          });
          // diff：把现在不在 entries 的子孙都清掉（被外部删/移走的）
          const childSet = new Set(r.entries.map((e) => e.path));
          const removable: string[] = [];
          for (const [p, s] of next) {
            if (s.parent === path && !childSet.has(p)) removable.push(p);
          }
          for (const p of removable) {
            // 递归删 p 及其后代
            const stack = [p];
            while (stack.length) {
              const cp = stack.pop()!;
              next.delete(cp);
              for (const [pp, ss] of next) {
                if (ss.parent === cp) stack.push(pp);
              }
            }
          }
          // 注册/更新子节点元信息
          for (const e of r.entries) {
            const old = next.get(e.path);
            if (old) {
              next.set(e.path, {
                ...old,
                name: e.name,
                isDir: e.is_dir,
                parent: path,
              });
            } else {
              next.set(e.path, {
                isDir: e.is_dir,
                name: e.name,
                parent: path,
                entries: null,
                loading: false,
                error: null,
                expanded: false,
                isNew: cur.entries !== null,
              });
            }
          }
          return next;
        });
      } catch (e) {
        patchNode(path, { error: String(e), loading: false });
      }
    },
    [patchNode],
  );

  const refetchExpanded = useCallback(() => {
    for (const [path, state] of nodesRef.current) {
      if (state.isDir && state.expanded) fetchDir(path);
    }
  }, [fetchDir]);

  // ─── 顶层 effect：rootPath / focus / refreshNonce / collapseNonce ──────

  useEffect(() => {
    // 重置（rootPath 变化）— prop 切换触发的强制全清，必须在 effect 里
    /* eslint-disable react-hooks/set-state-in-effect */
    setNodes(
      new Map([
        [
          rootPath,
          {
            isDir: true,
            name: rootName(rootPath),
            parent: null,
            entries: null,
            loading: false,
            error: null,
            expanded: true,
          },
        ],
      ]),
    );
    setSelectedPath(null);
    setEditing(null);
    setMenu(null);
    setDeleteTarget(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    fetchDir(rootPath);
  }, [rootPath, fetchDir]);

  useEffect(() => {
    const onFocus = () => refetchExpanded();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
    // 注：文件系统变更的实时感知待后端提供 watch/notify RPC 后接入，当前仅依赖 focus + refreshNonce
  }, [refetchExpanded]);

  const refreshSkip = useRef(true);
  useEffect(() => {
    if (refreshNonce === undefined) return;
    if (refreshSkip.current) {
      refreshSkip.current = false;
      return;
    }
    refetchExpanded();
  }, [refreshNonce, refetchExpanded]);

  const collapseSkip = useRef(true);
  useEffect(() => {
    if (collapseNonce === undefined) return;
    if (collapseSkip.current) {
      collapseSkip.current = false;
      return;
    }
    setNodes((m) => {
      const next = new Map<string, NodeState>();
      for (const [p, s] of m) next.set(p, { ...s, expanded: p === rootPath });
      return next;
    });
  }, [collapseNonce, rootPath]);

  // ─── 用户动作 ──────────────────────────────────────────────────────────

  const toggle = useCallback(
    (path: string) => {
      const cur = nodesRef.current.get(path);
      if (!cur || !cur.isDir) return;
      const willExpand = !cur.expanded;
      patchNode(path, { expanded: willExpand });
      if (willExpand && cur.entries === null && !cur.loading) {
        fetchDir(path);
      }
    },
    [patchNode, fetchDir],
  );

  const select = useCallback(
    (path: string) => {
      setSelectedPath(path);
      patchNode(path, { isNew: false });
      containerRef.current?.focus();
    },
    [patchNode],
  );

  const activate = useCallback(
    (path: string, shift: boolean) => {
      const cur = nodesRef.current.get(path);
      if (!cur) return;
      if (cur.isDir) {
        toggle(path);
        return;
      }
      const ext = (() => {
        const i = cur.name.lastIndexOf('.');
        return i > 0 ? cur.name.slice(i).toLowerCase() : '';
      })();
      if (!shift && onFileActivate && TOOL_INPUT_EXTS.has(ext)) {
        onFileActivate(path);
      } else {
        openPath(path).catch((err) => console.error('openPath failed:', err));
      }
    },
    [toggle, onFileActivate],
  );

  // 工具：确保选中目录已展开（用于"新建于此"）
  const ensureExpanded = useCallback(
    async (dir: string) => {
      const cur = nodesRef.current.get(dir);
      if (!cur || !cur.isDir) return;
      if (!cur.expanded) {
        patchNode(dir, { expanded: true });
        if (cur.entries === null) await fetchDir(dir);
      }
    },
    [patchNode, fetchDir],
  );

  const beginRename = useCallback((path: string) => {
    const cur = nodesRef.current.get(path);
    if (!cur || cur.parent === null) return; // 根目录不能改名
    setSelectedPath(path);
    setEditing({ kind: 'rename', path, initialValue: cur.name });
  }, []);

  const beginCreate = useCallback(
    async (parent: string, isDir: boolean) => {
      // 目标 parent 必须是目录；选中是文件时 → 取其父目录
      let target = parent;
      const targetNode = nodesRef.current.get(target);
      if (targetNode && !targetNode.isDir && targetNode.parent) {
        target = targetNode.parent;
      }
      await ensureExpanded(target);
      setSelectedPath(target);
      setEditing({ kind: 'create', parent: target, isDir });
    },
    [ensureExpanded],
  );

  const cancelEdit = useCallback(() => setEditing(null), []);

  const commitEdit = useCallback(
    async (rawValue: string) => {
      const ed = editing;
      if (!ed) return;
      const value = rawValue.trim();
      if (!value) {
        setEditing(null);
        return;
      }
      try {
        if (ed.kind === 'rename') {
          if (value === ed.initialValue) {
            setEditing(null);
            return;
          }
          const r = await rpc<{ path: string }>('files.rename', {
            path: ed.path,
            new_name: value,
          });
          setEditing(null);
          // 刷新父目录，然后选中新 path
          const parentNode = nodesRef.current.get(ed.path);
          const parentPath = parentNode?.parent;
          if (parentPath) await fetchDir(parentPath);
          setSelectedPath(r.path);
        } else {
          const method = ed.isDir ? 'files.create_folder' : 'files.create_file';
          const r = await rpc<{ path: string }>(method, {
            parent: ed.parent,
            name: value,
          });
          setEditing(null);
          await fetchDir(ed.parent);
          setSelectedPath(r.path);
        }
      } catch (e) {
        // 失败保持编辑态，让用户改
        await dlg.alert({
          title: '操作失败',
          message: String(e),
          tone: 'error',
        });
      }
    },
    [dlg, editing, fetchDir],
  );

  const doDelete = useCallback((path: string) => {
    const cur = nodesRef.current.get(path);
    if (!cur || cur.parent === null) return;
    setDeleteTarget(path);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    const path = deleteTarget;
    const cur = nodesRef.current.get(path);
    setDeleteTarget(null);
    if (!cur || cur.parent === null) return;
    try {
      await rpc('files.delete', { path });
      setUndoStack((prev) => [...prev, Date.now()]);
      if (selectedRef.current === path) setSelectedPath(null);
      if (cur.parent) await fetchDir(cur.parent);
    } catch (e) {
      await dlg.alert({ title: '删除失败', message: String(e), tone: 'error' });
    }
  }, [dlg, deleteTarget, fetchDir]);

  const doUndoDelete = useCallback(async () => {
    if (opBusy) return;
    setOpBusy(true);
    try {
      const r = await rpc<{ restored_path: string; parent: string }>(
        'files.undo_delete',
        {},
      );
      setUndoStack((prev) => prev.slice(0, -1));
      await fetchDir(r.parent);
      setSelectedPath(r.restored_path);
    } catch (e) {
      await dlg.alert({
        title: '撤销删除失败',
        message: String(e),
        tone: 'error',
      });
    } finally {
      setOpBusy(false);
    }
  }, [dlg, fetchDir, opBusy]);

  const doCopyToClipboard = useCallback((path: string) => {
    setClipboard({ path, mode: 'copy' });
  }, []);

  const doCutToClipboard = useCallback((path: string) => {
    setClipboard({ path, mode: 'cut' });
  }, []);

  const doPaste = useCallback(
    async (targetDirIn: string) => {
      if (!clipboard || opBusy) return;
      setOpBusy(true);
      // 如果 target 是文件，粘贴到其父目录
      let target = targetDirIn;
      const t = nodesRef.current.get(target);
      if (t && !t.isDir && t.parent) target = t.parent;
      const srcNode = nodesRef.current.get(clipboard.path);
      const srcParent = srcNode?.parent ?? null;
      try {
        const method = clipboard.mode === 'copy' ? 'files.copy' : 'files.move';
        const r = await rpc<{ path: string }>(method, {
          src: clipboard.path,
          dst_parent: target,
        });
        if (clipboard.mode === 'cut') setClipboard(null);
        await fetchDir(target);
        if (clipboard.mode === 'cut' && srcParent && srcParent !== target) {
          await fetchDir(srcParent);
        }
        setSelectedPath(r.path);
      } catch (e) {
        await dlg.alert({
          title: '粘贴失败',
          message: String(e),
          tone: 'error',
        });
      } finally {
        setOpBusy(false);
      }
    },
    [dlg, clipboard, fetchDir, opBusy],
  );

  const doCopyPath = useCallback((path: string) => {
    navigator.clipboard.writeText(path).catch((err) => console.error(err));
  }, []);

  const doReveal = useCallback(
    async (path: string) => {
      try {
        await rpc('files.reveal', { path });
      } catch (e) {
        await dlg.alert({
          title: '在资源管理器中显示失败',
          message: String(e),
          tone: 'error',
        });
      }
    },
    [dlg],
  );

  const openMenu = useCallback((e: React.MouseEvent, target: string | null) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, target });
    if (target) setSelectedPath(target);
  }, []);

  // ─── 键盘导航 ──────────────────────────────────────────────────────────

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (editing) return;
      if (menu) return;
      if (deleteTarget) {
        if (e.key === 'Escape') setDeleteTarget(null);
        if (e.key === 'Enter') confirmDelete();
        return;
      }
      const rows = visibleRowsRef.current;
      if (rows.length === 0) return;
      const cur = selectedRef.current;
      const idx = cur ? rows.findIndex((r) => r.path === cur) : -1;

      const moveTo = (i: number) => {
        const clamped = Math.max(0, Math.min(rows.length - 1, i));
        setSelectedPath(rows[clamped].path);
      };

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveTo(idx + 1);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveTo(idx - 1);
        return;
      }
      if (!cur || idx < 0) return;
      const row = rows[idx];

      if (e.key === 'ArrowRight') {
        e.preventDefault();
        if (row.isDir && !row.expanded) toggle(row.path);
        else if (row.isDir && row.expanded && idx + 1 < rows.length)
          setSelectedPath(rows[idx + 1].path);
        return;
      }
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        if (row.isDir && row.expanded) {
          toggle(row.path);
          return;
        }
        const node = nodesRef.current.get(row.path);
        if (node?.parent) setSelectedPath(node.parent);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        activate(row.path, e.shiftKey);
        return;
      }
      if (e.key === 'F2') {
        e.preventDefault();
        beginRename(row.path);
        return;
      }
      if (e.key === 'Delete') {
        e.preventDefault();
        doDelete(row.path);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setSelectedPath(null);
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        doUndoDelete();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
        e.preventDefault();
        doCopyToClipboard(row.path);
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'x') {
        e.preventDefault();
        doCutToClipboard(row.path);
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
        e.preventDefault();
        doPaste(row.path);
        return;
      }
    },
    [
      editing,
      menu,
      deleteTarget,
      confirmDelete,
      toggle,
      activate,
      beginRename,
      doDelete,
      doUndoDelete,
      doCopyToClipboard,
      doCutToClipboard,
      doPaste,
    ],
  );

  // ─── Context value ─────────────────────────────────────────────────────

  const ctxValue = useMemo<TreeCtx>(
    () => ({
      rootPath,
      nodes,
      visibleRows,
      selectedPath,
      editing,
      clipboard,
      toggle,
      select,
      activate,
      beginRename,
      beginCreate,
      commitEdit,
      cancelEdit,
      doDelete,
      doUndoDelete,
      undoStack,
      doCopyToClipboard,
      doCutToClipboard,
      doPaste,
      doCopyPath,
      doReveal,
      openMenu,
    }),
    [
      rootPath,
      nodes,
      visibleRows,
      selectedPath,
      editing,
      clipboard,
      toggle,
      select,
      activate,
      beginRename,
      beginCreate,
      commitEdit,
      cancelEdit,
      doDelete,
      doUndoDelete,
      undoStack,
      doCopyToClipboard,
      doCutToClipboard,
      doPaste,
      doCopyPath,
      doReveal,
      openMenu,
    ],
  );

  // 在编辑/新建结束后 / 选中变化后让容器拿到焦点（便于继续键盘操作）
  useEffect(() => {
    if (!editing && !deleteTarget && !menu) containerRef.current?.focus();
  }, [editing, deleteTarget, menu]);

  return (
    <Ctx.Provider value={ctxValue}>
      <div
        ref={containerRef}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        onContextMenu={(e) => {
          // 空白区右键：target = null（动作落到根）
          if ((e.target as HTMLElement).closest('[data-row]')) return;
          openMenu(e, null);
        }}
        onClick={(e) => {
          // 空白区单击 → 取消选中
          if (!(e.target as HTMLElement).closest('[data-row]')) {
            setSelectedPath(null);
          }
        }}
        className="text-vscode-text min-h-full py-1 text-[13px] outline-none"
      >
        {visibleRows.map((row) => (
          <NodeRow key={row.path} row={row} />
        ))}
        {/* 新建编辑行：插在目标 parent 的 entries 顶端不好对齐，统一放到目标行下方简单实现 */}
        {editing?.kind === 'create' && (
          <CreateRow
            editing={editing}
            commit={commitEdit}
            cancel={cancelEdit}
          />
        )}
      </div>
      {menu && <ContextMenuView menu={menu} onClose={() => setMenu(null)} />}
      {deleteTarget &&
        (() => {
          const node = nodes.get(deleteTarget);
          return (
            <DeleteConfirmModal
              targetName={node?.name ?? '此项'}
              targetPath={deleteTarget}
              isDir={node?.isDir ?? false}
              onConfirm={confirmDelete}
              onCancel={() => setDeleteTarget(null)}
            />
          );
        })()}
    </Ctx.Provider>
  );
}

/**
 * VSCode 同款删除确认 modal。
 * - 顶部：垃圾桶图标 + 标题「确定要删除 'name' 吗？」
 * - 副文本：路径全名（断词显示）+ 文件夹时额外提示「连同子项一起」
 * - 主按钮「移到回收站」蓝色 primary；次按钮「取消」灰色
 * - Backdrop 不可关（防误点）；Esc 取消，Enter 确认
 */
function DeleteConfirmModal({
  targetName,
  targetPath,
  isDir,
  onConfirm,
  onCancel,
}: {
  targetName: string;
  targetPath: string;
  isDir: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        onConfirm();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onConfirm, onCancel]);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40"
      // 点 backdrop 不关 —— VSCode 删除 modal 也不可点空白关闭，避免误操作丢失上下文
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className="border-vscode-border text-vscode-text w-full max-w-[440px] rounded-[4px] border bg-[#252526] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex gap-3 p-5 pb-3">
          <i className="codicon codicon-trash text-vscode-focus mt-0.5 shrink-0 !text-[20px]" />
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] leading-tight font-medium">
              确定要删除「<span className="break-all">{targetName}</span>」吗？
            </h2>
            <p className="text-vscode-text-dim mt-2 text-[12px] break-all">
              {targetPath}
            </p>
            {isDir && (
              <p className="mt-2 text-[12px] text-yellow-400">
                <i className="codicon codicon-warning mr-1 !text-[12px]" />
                这是一个文件夹，将连同其中的所有子项一起删除。
              </p>
            )}
            <p className="text-vscode-text-dim mt-2 text-[12px]">
              文件将移到系统回收站，可在回收站中还原；也可在文件树里按 Ctrl+Z
              撤销最近 5 分钟内的删除。
            </p>
          </div>
        </div>
        <div className="bg-vscode-border/30 flex justify-end gap-2 rounded-b-[4px] px-5 py-3">
          <button
            className="text-vscode-text rounded-[2px] bg-[#3a3d41] px-4 py-1.5 text-[13px] transition-colors outline-none hover:bg-[#4a4d51]"
            onClick={onCancel}
          >
            取消
          </button>
          <button
            autoFocus
            className="bg-vscode-button hover:bg-vscode-button-hover rounded-[2px] px-4 py-1.5 text-[13px] text-white transition-colors outline-none"
            onClick={onConfirm}
          >
            移到回收站
          </button>
        </div>
      </div>
    </div>
  );
}

function useTreeCtx(): TreeCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('must be inside <FileTree>');
  return v;
}

// ──────────────────────────────────────────────────────────────────────────────
// NodeRow：扁平渲染中的一行
// ──────────────────────────────────────────────────────────────────────────────

function NodeRow({ row }: { row: RenderRow }) {
  const c = useTreeCtx();
  const isEditing = c.editing?.kind === 'rename' && c.editing.path === row.path;
  const isCut = c.clipboard?.mode === 'cut' && c.clipboard.path === row.path;

  const fileIcon = !row.isDir ? getFileIcon(row.name) : null;
  const ext = !row.isDir
    ? (() => {
        const i = row.name.lastIndexOf('.');
        return i > 0 ? row.name.slice(i).toLowerCase() : '';
      })()
    : '';
  const isToolFile = !row.isDir && TOOL_INPUT_EXTS.has(ext);
  const tooltip = row.isDir
    ? undefined
    : isToolFile
      ? '双击：作为当前工具输入\n（Shift+双击：用系统默认程序打开）'
      : '双击：用系统默认程序打开';

  return (
    <div
      data-row
      data-path={row.path}
      onClick={(e) => {
        e.stopPropagation();
        c.select(row.path);
        // 单击目录也 toggle（VSCode 风）
        if (row.isDir) c.toggle(row.path);
      }}
      onDoubleClick={(e) => {
        e.stopPropagation();
        c.activate(row.path, e.shiftKey);
      }}
      onContextMenu={(e) => c.openMenu(e, row.path)}
      title={tooltip}
      style={{ paddingLeft: row.depth * 12 + 4 }}
      className={cn(
        'flex h-[22px] cursor-pointer items-center gap-1 pr-2 select-none',
        row.selected ? 'bg-vscode-selected' : 'hover:bg-vscode-hover',
        isCut && 'opacity-60',
      )}
    >
      <i
        className={cn(
          'codicon text-vscode-text-dim w-4 shrink-0 !text-[12px]',
          row.isDir &&
            `codicon-${row.expanded ? 'chevron-down' : 'chevron-right'}`,
        )}
      />
      <i
        className={cn(
          'codicon shrink-0 !text-[14px]',
          row.isDir
            ? `codicon-${row.expanded ? 'folder-opened' : 'folder'} text-vscode-text`
            : `codicon-${fileIcon!.icon} ${fileIcon!.colorClass}`,
        )}
      />
      {isEditing ? (
        <InlineInput
          initial={(c.editing as { initialValue: string }).initialValue}
          autoSelectStem={!row.isDir}
          onCommit={(v) => c.commitEdit(v)}
          onCancel={c.cancelEdit}
        />
      ) : (
        <>
          <span
            className={cn('flex-1 truncate', row.isNew && 'text-[#73c991]')}
          >
            {row.name}
          </span>
          {row.isNew && (
            <span
              className="mr-1 flex-shrink-0 text-[10px] font-medium text-[#73c991] select-none"
              title="Untracked"
            >
              U
            </span>
          )}
        </>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// CreateRow：新建文件/文件夹时的临时输入行
// ──────────────────────────────────────────────────────────────────────────────

function CreateRow({
  editing,
  commit,
  cancel,
}: {
  editing: { kind: 'create'; parent: string; isDir: boolean };
  commit: (v: string) => void;
  cancel: () => void;
}) {
  const c = useTreeCtx();
  // 把新建输入插在 parent 行紧跟着的位置：找 parent 在 visibleRows 的 depth
  const parentRow = c.visibleRows.find((r) => r.path === editing.parent);
  const depth = (parentRow?.depth ?? 0) + 1;

  return (
    <div
      data-row
      style={{ paddingLeft: depth * 12 + 4 }}
      className="bg-vscode-selected/30 flex h-[22px] items-center gap-1 pr-2"
    >
      <i className="codicon w-4 shrink-0 !text-[12px]" />
      <i
        className={cn(
          'codicon text-vscode-text shrink-0 !text-[14px]',
          editing.isDir ? 'codicon-folder' : 'codicon-file',
        )}
      />
      <InlineInput
        initial=""
        autoSelectStem={false}
        onCommit={commit}
        onCancel={cancel}
      />
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// InlineInput：通用 in-place 输入框
// ──────────────────────────────────────────────────────────────────────────────

function InlineInput({
  initial,
  autoSelectStem,
  onCommit,
  onCancel,
}: {
  initial: string;
  /** 重命名文件时 true：自动只选中 stem（不含扩展名）；新建/文件夹用 false */
  autoSelectStem: boolean;
  onCommit: (v: string) => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const committedRef = useRef(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    if (autoSelectStem) {
      const [stem] = splitName(initial);
      el.setSelectionRange(0, stem.length);
    } else {
      el.select();
    }
  }, [autoSelectStem, initial]);

  return (
    <input
      ref={ref}
      defaultValue={initial}
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          committedRef.current = true;
          onCommit((e.target as HTMLInputElement).value);
        } else if (e.key === 'Escape') {
          e.preventDefault();
          onCancel();
        }
        e.stopPropagation();
      }}
      onBlur={(e) => {
        if (committedRef.current) return;
        const v = e.target.value;
        if (v && v !== initial) onCommit(v);
        else onCancel();
      }}
      className={cn(
        'text-vscode-text border-vscode-focus min-w-0 flex-1 border bg-[#3c3c3c]',
        'h-[18px] px-1 text-[13px] outline-none',
      )}
    />
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// ContextMenuView
// ──────────────────────────────────────────────────────────────────────────────

interface MenuItem {
  label: string;
  icon?: string;
  shortcut?: string;
  disabled?: boolean;
  danger?: boolean;
  onClick: () => void;
}

function ContextMenuView({
  menu,
  onClose,
}: {
  menu: MenuState;
  onClose: () => void;
}) {
  const c = useTreeCtx();
  const ref = useRef<HTMLDivElement>(null);

  // 外部点击 / Esc 关闭
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  // 视口边界修正：菜单超出右/下边界时回拉
  const [pos, setPos] = useState({ x: menu.x, y: menu.y });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth,
      h = el.offsetHeight;
    const vw = window.innerWidth,
      vh = window.innerHeight;
    setPos({
      x: Math.min(menu.x, vw - w - 4),
      y: Math.min(menu.y, vh - h - 4),
    });
  }, [menu]);

  const target = menu.target;
  const targetNode = target ? c.nodes.get(target) : null;
  const isDir = target === null ? true : !!targetNode?.isDir;
  // "粘贴"的目标目录：选中是文件时取其父目录；空白则为 root
  const pasteTarget =
    target === null
      ? c.rootPath
      : targetNode?.isDir
        ? target
        : (targetNode?.parent ?? c.rootPath);

  const items: (MenuItem | 'sep')[] = [];

  // 文件：用系统默认打开 / 在工具中打开
  if (target && !isDir) {
    items.push({
      label: '用系统默认程序打开',
      icon: 'link-external',
      onClick: () => {
        openPath(target).catch((err) => console.error(err));
        onClose();
      },
    });
    items.push('sep');
  }

  // 新建（目标是目录或空白）
  if (isDir) {
    items.push({
      label: '新建文件',
      icon: 'new-file',
      onClick: () => {
        c.beginCreate(target ?? c.rootPath, false);
        onClose();
      },
    });
    items.push({
      label: '新建文件夹',
      icon: 'new-folder',
      onClick: () => {
        c.beginCreate(target ?? c.rootPath, true);
        onClose();
      },
    });
    items.push('sep');
  }

  // 剪切/复制/粘贴/复制路径
  if (target) {
    items.push({
      label: '剪切',
      icon: 'discard',
      shortcut: 'Ctrl+X',
      onClick: () => {
        c.doCutToClipboard(target);
        onClose();
      },
    });
    items.push({
      label: '复制',
      icon: 'copy',
      shortcut: 'Ctrl+C',
      onClick: () => {
        c.doCopyToClipboard(target);
        onClose();
      },
    });
  }
  items.push({
    label: '粘贴',
    icon: 'clippy',
    shortcut: 'Ctrl+V',
    disabled: !c.clipboard,
    onClick: () => {
      c.doPaste(pasteTarget);
      onClose();
    },
  });
  if (target) {
    items.push({
      label: '复制路径',
      icon: 'files',
      onClick: () => {
        c.doCopyPath(target);
        onClose();
      },
    });
  }

  items.push('sep');

  // 重命名 / 删除（target 必须存在且非根）
  if (target && targetNode?.parent) {
    items.push({
      label: '重命名',
      icon: 'edit',
      shortcut: 'F2',
      onClick: () => {
        c.beginRename(target);
        onClose();
      },
    });
    items.push({
      label: '删除（到回收站）',
      icon: 'trash',
      shortcut: 'Delete',
      danger: true,
      onClick: () => {
        c.doDelete(target);
        onClose();
      },
    });
    items.push('sep');
  }

  // 撤销删除（仅5分钟内有效且有记录）
  // Date.now() 是非纯函数，不能在 render 里直接读。菜单短暂存在，开启时
  // 锁一次时间足以判断 5 分钟窗口；菜单常开 5 分钟以上的场景不存在
  const [menuOpenedAt] = useState(() => Date.now());
  const canUndo =
    c.undoStack.length > 0 &&
    menuOpenedAt - c.undoStack[c.undoStack.length - 1] <= 300000;
  items.push({
    label: '撤销删除',
    icon: 'discard',
    shortcut: 'Ctrl+Z',
    disabled: !canUndo,
    onClick: () => {
      c.doUndoDelete();
      onClose();
    },
  });
  items.push('sep');

  // Reveal
  items.push({
    label: '在资源管理器中显示',
    icon: 'folder-opened',
    onClick: () => {
      c.doReveal(target ?? c.rootPath);
      onClose();
    },
  });

  // 去掉首尾和连续的 sep
  const cleaned: (MenuItem | 'sep')[] = [];
  for (const it of items) {
    if (it === 'sep') {
      if (cleaned.length === 0 || cleaned[cleaned.length - 1] === 'sep')
        continue;
      cleaned.push(it);
    } else cleaned.push(it);
  }
  while (cleaned[cleaned.length - 1] === 'sep') cleaned.pop();

  return (
    <div
      ref={ref}
      style={{ left: pos.x, top: pos.y }}
      className={cn(
        'fixed z-50 min-w-[200px] rounded-[3px] py-1',
        'border-vscode-border border bg-[#252526] shadow-xl',
        'text-vscode-text text-[13px]',
      )}
      onContextMenu={(e) => e.preventDefault()}
    >
      {cleaned.map((it, i) => {
        if (it === 'sep') {
          return (
            <div
              key={`sep-${i}`}
              className="border-vscode-border my-1 border-t"
            />
          );
        }
        return (
          <button
            key={it.label}
            type="button"
            disabled={it.disabled}
            onClick={(e) => {
              e.stopPropagation();
              it.onClick();
            }}
            className={cn(
              'flex h-[24px] w-full items-center gap-2 px-3 text-left',
              it.disabled
                ? 'cursor-not-allowed opacity-50'
                : 'hover:bg-vscode-hover hover:text-white',
              it.danger && !it.disabled && 'hover:!bg-red-700',
            )}
          >
            <i
              className={cn(
                'codicon w-4 !text-[14px]',
                it.icon && `codicon-${it.icon}`,
              )}
            />
            <span className="flex-1 truncate">{it.label}</span>
            {it.shortcut && (
              <span className="text-vscode-text-dim ml-4 text-[11px]">
                {it.shortcut}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
