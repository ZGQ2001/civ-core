/**
 * civ-core shell：VSCode 风三段式布局。
 * 顶层：[Activity Bar | (Side Bar | Editor) Resizable] + 底部 Status Bar
 *
 * T2 阶段：纯前端骨架，无 Tauri/Python 接入；工作区路径暂时 null。
 * T3 阶段：接 Tauri rpc_call 调 Python sidecar，文件树/工作区都打通。
 */
import { useCallback, useEffect, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { open as openDialog } from "@tauri-apps/plugin-dialog";

import { ActivityBar, type ActivityItem } from "./components/ActivityBar";
import { EditorArea } from "./components/EditorArea";
import { SideBar } from "./components/SideBar";
import { StatusBar } from "./components/StatusBar";
import { TitleBar } from "./components/TitleBar";
import { rpc, type WorkspaceLast } from "./lib/rpc";

const TOP_TOOLS: ActivityItem[] = [
  { id: "plot_curves", icon: "graph-line", tooltip: "绘曲线图" },
  { id: "leeb_hardness", icon: "symbol-numeric", tooltip: "里氏硬度" },
  { id: "pdf_tools", icon: "file-pdf", tooltip: "PDF 工具" },
  { id: "word2pdf", icon: "file-binary", tooltip: "Word → PDF" },
];
const BOTTOM_TOOLS: ActivityItem[] = [
  { id: "settings", icon: "settings-gear", tooltip: "设置" },
];

const ALL_TOOLS = [...TOP_TOOLS, ...BOTTOM_TOOLS];

export default function App() {
  const [activeToolId, setActiveToolId] = useState<string>("plot_curves");
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [sidecarStatus, setSidecarStatus] = useState<string>("连接中…");
  // 递增即触发 FileTree 整树重挂（刷新 / 全部折叠共用这一把锤子）
  const [refreshKey, setRefreshKey] = useState(0);

  const toolLabel =
    ALL_TOOLS.find((t) => t.id === activeToolId)?.tooltip ?? null;

  // 启动时：ping 确认 sidecar 通了，再读 last_workspace 自动加载
  useEffect(() => {
    (async () => {
      try {
        const pong = await rpc<string>("ping");
        setSidecarStatus(`后端就绪 (${pong})`);
        const ws = await rpc<WorkspaceLast>("workspace.last");
        if (ws.path) setWorkspacePath(ws.path);
      } catch (e) {
        setSidecarStatus(`后端连接失败：${String(e)}`);
      }
    })();
  }, []);

  // 打开文件夹：dialog 选目录 → workspace.set 持久化 → 更新 state
  const handleOpenFolder = useCallback(async () => {
    try {
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: "选择工作区文件夹",
      });
      if (typeof selected !== "string") return; // 用户取消
      await rpc("workspace.set", { path: selected });
      setWorkspacePath(selected);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      console.error("打开文件夹失败:", e);
      alert(`打开文件夹失败：${String(e)}`);
    }
  }, []);

  // 新建标准结构：dialog 选父目录 → prompt 输入项目名 → workspace.create_standard
  // 注意：window.prompt 在 Tauri webview 里能用但样式不可控；T5+ 可换自定义 modal
  const handleNewWorkspace = useCallback(async () => {
    try {
      const parent = await openDialog({
        directory: true,
        multiple: false,
        title: "选择父目录（在其下创建标准项目结构）",
      });
      if (typeof parent !== "string") return;
      const name = window.prompt("输入项目名（将在父目录下创建同名子文件夹 + 标准骨架）：");
      if (!name || !name.trim()) return;
      const res = await rpc<{ ok: boolean; path: string }>(
        "workspace.create_standard",
        { parent_dir: parent, name: name.trim() },
      );
      await rpc("workspace.set", { path: res.path });
      setWorkspacePath(res.path);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      console.error("新建工作区失败:", e);
      alert(`新建工作区失败：${String(e)}`);
    }
  }, []);

  const handleRefresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  // 折叠所有：第一版用整树重挂复用 refresh 路径；后续要保留 expanded 再细化
  const handleCollapseAll = useCallback(() => setRefreshKey((k) => k + 1), []);

  const workspaceName = workspacePath
    ? workspacePath.split(/[\\/]/).filter(Boolean).pop() ?? null
    : null;

  return (
    <div className="flex h-screen w-screen flex-col">
      <TitleBar workspaceName={workspaceName} toolLabel={toolLabel} />

      {/* 主区：Activity Bar + 可拖动两栏 */}
      <div className="flex flex-1 min-h-0">
        <ActivityBar
          topItems={TOP_TOOLS}
          bottomItems={BOTTOM_TOOLS}
          activeId={activeToolId}
          onChange={setActiveToolId}
        />

        <Group orientation="horizontal" id="civ-core-shell" className="flex flex-1 min-w-0">
          <Panel
            defaultSize={18}
            minSize={6}
            collapsible
            collapsedSize={0}
            id="sidebar"
          >
            <SideBar
              workspacePath={workspacePath}
              refreshKey={refreshKey}
              onOpenFolder={handleOpenFolder}
              onNewWorkspace={handleNewWorkspace}
              onRefresh={handleRefresh}
              onCollapseAll={handleCollapseAll}
            />
          </Panel>
          <Separator className="w-px bg-vscode-border hover:bg-vscode-focus transition-colors" />
          <Panel defaultSize={82} minSize={30} id="editor">
            <EditorArea activeToolId={activeToolId} toolLabel={toolLabel} />
          </Panel>
        </Group>
      </div>

      <StatusBar workspacePath={workspacePath} toolLabel={toolLabel} sidecarStatus={sidecarStatus} />
    </div>
  );
}
