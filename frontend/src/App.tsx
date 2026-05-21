/**
 * civ-core shell：VSCode 风布局。
 *
 * 整体（自上而下）：
 *   TitleBar (30px)
 *   Main：ActivityBar (48px) + vertical Group {
 *     上：horizontal Group { SideBar | EditorArea }
 *     下：BottomPanel（可折叠 / 可拖）
 *   }
 *   StatusBar (22px)
 *
 * Activity Bar 顶部的 Explorer 图标 toggle SideBar 显隐（VSCode 原生）。
 * 底部 Panel 默认折叠；BottomPanel 内部"关闭"按钮 collapse 自身；后续会从工具页主动 expand。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Group,
  Panel,
  Separator,
  type PanelImperativeHandle,
} from "react-resizable-panels";
import { open as openDialog } from "@tauri-apps/plugin-dialog";

import { ActivityBar, type ActivityItem } from "./components/ActivityBar";
import { BottomPanel } from "./components/BottomPanel";
import { EditorArea } from "./components/EditorArea";
import { SideBar } from "./components/SideBar";
import { StatusBar } from "./components/StatusBar";
import { TitleBar } from "./components/TitleBar";
import { rpc, type WorkspaceLast } from "./lib/rpc";
import { PlotCurvesProvider, PlotCurvesSettingsForm } from "./tools/plot_curves";

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
  const [refreshKey, setRefreshKey] = useState(0);
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [bottomVisible, setBottomVisible] = useState(true);
  const [outputLog, setOutputLog] = useState("");

  // Panel refs：用于命令式 collapse/expand
  const sidebarRef = useRef<PanelImperativeHandle>(null);
  const bottomRef = useRef<PanelImperativeHandle>(null);

  const toolLabel = ALL_TOOLS.find((t) => t.id === activeToolId)?.tooltip ?? null;

  // 启动：ping + 拉上次工作区
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

  // SideBar 显隐：通过 Panel imperative handle
  const handleExplorerToggle = useCallback(() => {
    const p = sidebarRef.current;
    if (!p) return;
    if (p.isCollapsed()) {
      p.expand();
      setSidebarVisible(true);
    } else {
      p.collapse();
      setSidebarVisible(false);
    }
  }, []);

  // 工具向"输出"Tab 写日志的入口（也会自动展开底部 Panel）
  const appendOutput = useCallback((text: string) => {
    setOutputLog((prev) => (prev ? `${prev}\n${text}` : text));
    bottomRef.current?.expand();
    setBottomVisible(true);
  }, []);

  const toggleBottom = useCallback(() => {
    const p = bottomRef.current;
    if (!p) return;
    if (p.isCollapsed()) {
      p.expand();
      setBottomVisible(true);
    } else {
      p.collapse();
      setBottomVisible(false);
    }
  }, []);

  // Ctrl+J 全局快捷键（与 VSCode 一致）
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "j") {
        e.preventDefault();
        toggleBottom();
      } else if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "b") {
        e.preventDefault();
        handleExplorerToggle();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleBottom, handleExplorerToggle]);

  // SideBar 4 个按钮
  const handleOpenFolder = useCallback(async () => {
    try {
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: "选择工作区文件夹",
      });
      if (typeof selected !== "string") return;
      await rpc("workspace.set", { path: selected });
      setWorkspacePath(selected);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      console.error("打开文件夹失败:", e);
      alert(`打开文件夹失败：${String(e)}`);
    }
  }, []);

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
  const handleCollapseAll = useCallback(() => setRefreshKey((k) => k + 1), []);

  const workspaceName = workspacePath
    ? workspacePath.split(/[\\/]/).filter(Boolean).pop() ?? null
    : null;

  // 底部 Panel "工具设置" Tab 内容 —— 根据当前工具切换
  const settingsSlot = activeToolId === "plot_curves" ? <PlotCurvesSettingsForm /> : undefined;

  return (
    <PlotCurvesProvider>
    <div className="flex h-screen w-screen flex-col">
      <TitleBar workspaceName={workspaceName} toolLabel={toolLabel} />

      <div className="flex flex-1 min-h-0">
        <ActivityBar
          topItems={TOP_TOOLS}
          bottomItems={BOTTOM_TOOLS}
          activeId={activeToolId}
          onChange={setActiveToolId}
          explorerActive={sidebarVisible}
          onExplorerToggle={handleExplorerToggle}
        />

        {/* 上下分栏：上=SideBar|Editor，下=底部 Panel */}
        <Group orientation="vertical" id="civ-core-vsplit" className="flex flex-1 min-w-0 flex-col">
          <Panel defaultSize={75} minSize={20} id="vsplit-top">
            <Group
              orientation="horizontal"
              id="civ-core-hsplit"
              className="flex h-full min-h-0"
            >
              <Panel
                panelRef={sidebarRef}
                defaultSize={18}
                minSize={8}
                collapsible
                collapsedSize={0}
                id="sidebar"
                onResize={(s) => {
                  // 同步 explorerActive 高亮：用户拖到极小也算折叠
                  setSidebarVisible(s.asPercentage > 0.5);
                }}
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
                <EditorArea
                  activeToolId={activeToolId}
                  toolLabel={toolLabel}
                  appendOutput={appendOutput}
                />
              </Panel>
            </Group>
          </Panel>
          <Separator className="h-px bg-vscode-border hover:bg-vscode-focus transition-colors" />
          <Panel
            panelRef={bottomRef}
            defaultSize={25}
            minSize={10}
            collapsible
            collapsedSize={0}
            id="bottom-panel"
            onResize={(s) => setBottomVisible(s.asPercentage > 0.5)}
          >
            <BottomPanel
              output={outputLog}
              settingsSlot={settingsSlot}
              onClose={toggleBottom}
            />
          </Panel>
        </Group>
      </div>

      <StatusBar
        workspacePath={workspacePath}
        toolLabel={toolLabel}
        sidecarStatus={sidecarStatus}
        bottomPanelOpen={bottomVisible}
        onToggleBottomPanel={toggleBottom}
      />
    </div>
    </PlotCurvesProvider>
  );
}
