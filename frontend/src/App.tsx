/**
 * civ-core shell：VSCode 真实布局。
 *
 *   TitleBar (30px)
 *   Main：[ActivityBar | SideBar(全高) | (Editor+BottomPanel 竖向) | RightPanel(全高)]
 *   StatusBar (22px)
 *
 * 关键：SideBar 和 RightPanel 都是全高（与 VSCode 一致），底部 Panel 只覆盖
 * Editor 区域，不挤占 SideBar 和 RightPanel。
 *
 * SideBar 显隐：Activity Bar 顶部 Explorer 图标 toggle / Ctrl+B
 * BottomPanel 显隐：StatusBar「面板」按钮 / Ctrl+J
 * RightPanel 显隐：当前工具有 settings 时展开；右上角 chevron-right 收起
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
import { AgentPanel } from "./components/AgentPanel";
import { BottomPanel } from "./components/BottomPanel";
import { EditorArea } from "./components/EditorArea";
import { RightPanel, type RightTab } from "./components/RightPanel";
import { SideBar } from "./components/SideBar";
import { StatusBar } from "./components/StatusBar";
import { TitleBar } from "./components/TitleBar";
import { rpc, type WorkspaceLast } from "./lib/rpc";
import { DataProcessingProvider, DataProcessingSettingsForm } from "./tools/data_processing";
import { PdfToolsProvider, PdfToolsSettingsForm } from "./tools/pdf_tools";
import { PlotCurvesProvider, PlotCurvesSettingsForm } from "./tools/plot_curves";
import { Word2PdfProvider, Word2PdfSettingsForm } from "./tools/word2pdf";

const TOP_TOOLS: ActivityItem[] = [
  { id: "plot_curves", icon: "graph-line", tooltip: "绘曲线图" },
  { id: "data_processing", icon: "symbol-method", tooltip: "数据处理" },
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
  const [rightVisible, setRightVisible] = useState(true);
  const [outputLog, setOutputLog] = useState("");

  const sidebarRef = useRef<PanelImperativeHandle>(null);
  const bottomRef = useRef<PanelImperativeHandle>(null);
  const rightRef = useRef<PanelImperativeHandle>(null);

  const toolLabel = ALL_TOOLS.find((t) => t.id === activeToolId)?.tooltip ?? null;

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

  const toggleRight = useCallback(() => {
    const p = rightRef.current;
    if (!p) return;
    if (p.isCollapsed()) {
      p.expand();
      setRightVisible(true);
    } else {
      p.collapse();
      setRightVisible(false);
    }
  }, []);

  // 快捷键：Ctrl+J（底部 Panel）/ Ctrl+B（SideBar）/ Ctrl+Alt+B（右侧 Panel）
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (e.ctrlKey && !e.shiftKey && !e.altKey && k === "j") {
        e.preventDefault();
        toggleBottom();
      } else if (e.ctrlKey && !e.shiftKey && !e.altKey && k === "b") {
        e.preventDefault();
        handleExplorerToggle();
      } else if (e.ctrlKey && e.altKey && !e.shiftKey && k === "b") {
        e.preventDefault();
        toggleRight();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleBottom, handleExplorerToggle, toggleRight]);

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

  // 右侧 Panel 多 tab：当前工具调参 + 常驻 AI 助手（占位）。
  // 调参 tab 只在该工具确实有 settings 时出现，AI 助手始终在。
  const rightTabs: RightTab[] = [
    ...(activeToolId === "plot_curves"
      ? [
          {
            id: "settings",
            label: "调参",
            icon: "settings-gear",
            node: <PlotCurvesSettingsForm />,
          },
        ]
      : []),
    ...(activeToolId === "data_processing"
      ? [
          {
            id: "settings",
            label: "调参",
            icon: "settings-gear",
            node: <DataProcessingSettingsForm />,
          },
        ]
      : []),
    ...(activeToolId === "pdf_tools"
      ? [
          {
            id: "settings",
            label: "调参",
            icon: "settings-gear",
            node: <PdfToolsSettingsForm />,
          },
        ]
      : []),
    ...(activeToolId === "word2pdf"
      ? [
          {
            id: "settings",
            label: "调参",
            icon: "settings-gear",
            node: <Word2PdfSettingsForm />,
          },
        ]
      : []),
    { id: "agent", label: "AI 助手", icon: "hubot", node: <AgentPanel /> },
  ];
  const rightAvailable = rightTabs.length > 0;

  return (
    <PlotCurvesProvider>
      <DataProcessingProvider>
      <PdfToolsProvider>
      <Word2PdfProvider>
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

          {/* 主 horizontal group：SideBar(全高) | 中间(Editor+底部 Panel 竖向) | RightPanel(全高) */}
          <Group orientation="horizontal" id="civ-core-main" className="flex flex-1 min-w-0">
            <Panel
              panelRef={sidebarRef}
              defaultSize={16}
              minSize={8}
              collapsible
              collapsedSize={0}
              id="sidebar"
              onResize={(s) => setSidebarVisible(s.asPercentage > 0.5)}
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

            {/* 中间：Editor + 底部 Panel 竖向分栏 */}
            <Panel defaultSize={rightAvailable ? 58 : 84} minSize={30} id="middle">
              <Group
                orientation="vertical"
                id="civ-core-vsplit"
                className="flex h-full min-h-0 flex-col"
              >
                <Panel defaultSize={75} minSize={20} id="editor">
                  <EditorArea
                    activeToolId={activeToolId}
                    toolLabel={toolLabel}
                    appendOutput={appendOutput}
                  />
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
                  <BottomPanel output={outputLog} onClose={toggleBottom} />
                </Panel>
              </Group>
            </Panel>

            {/* 右侧 Panel：tab 化（调参 + AI 助手） */}
            {rightAvailable && (
              <Separator className="w-px bg-vscode-border hover:bg-vscode-focus transition-colors" />
            )}
            <Panel
              panelRef={rightRef}
              defaultSize={rightAvailable ? 26 : 0}
              minSize={rightAvailable ? 14 : 0}
              collapsible
              collapsedSize={0}
              id="right-panel"
              onResize={(s) => setRightVisible(s.asPercentage > 0.5)}
            >
              {rightAvailable && (
                <RightPanel tabs={rightTabs} defaultActiveId="settings" onClose={toggleRight} />
              )}
            </Panel>
          </Group>
        </div>

        <StatusBar
          workspacePath={workspacePath}
          toolLabel={toolLabel}
          sidecarStatus={sidecarStatus}
          bottomPanelOpen={bottomVisible}
          onToggleBottomPanel={toggleBottom}
          rightPanelOpen={rightVisible}
          onToggleRightPanel={toggleRight}
          rightPanelAvailable={rightAvailable}
        />
      </div>
      </Word2PdfProvider>
      </PdfToolsProvider>
      </DataProcessingProvider>
    </PlotCurvesProvider>
  );
}
