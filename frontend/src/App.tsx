/**
 * civ-core shell：VSCode 风三段式布局。
 * 顶层：[Activity Bar | (Side Bar | Editor) Resizable] + 底部 Status Bar
 *
 * T2 阶段：纯前端骨架，无 Tauri/Python 接入；工作区路径暂时 null。
 * T3 阶段：接 Tauri rpc_call 调 Python sidecar，文件树/工作区都打通。
 */
import { useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { ActivityBar, type ActivityItem } from "./components/ActivityBar";
import { EditorArea } from "./components/EditorArea";
import { SideBar } from "./components/SideBar";
import { StatusBar } from "./components/StatusBar";

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
  const [workspacePath] = useState<string | null>(null); // T3 后接 Tauri

  const toolLabel =
    ALL_TOOLS.find((t) => t.id === activeToolId)?.tooltip ?? null;

  return (
    <div className="flex h-screen w-screen flex-col">
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
              onOpenFolder={() => console.log("TODO: open folder")}
              onNewWorkspace={() => console.log("TODO: new workspace")}
              onRefresh={() => console.log("TODO: refresh")}
              onCollapseAll={() => console.log("TODO: collapse all")}
            />
          </Panel>
          <Separator className="w-px bg-vscode-border hover:bg-vscode-focus transition-colors" />
          <Panel defaultSize={82} minSize={30} id="editor">
            <EditorArea activeToolId={activeToolId} toolLabel={toolLabel} />
          </Panel>
        </Group>
      </div>

      <StatusBar workspacePath={workspacePath} toolLabel={toolLabel} />
    </div>
  );
}
