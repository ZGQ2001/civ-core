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
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Group,
  Panel,
  Separator,
  type PanelImperativeHandle,
} from 'react-resizable-panels';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { ActivityBar, type ActivityItem } from './components/ActivityBar';
import { AgentPanel } from './components/AgentPanel';
import { BottomPanel } from './components/BottomPanel';
import { EditorArea } from './components/EditorArea';
import { RightPanel, type RightTab } from './components/RightPanel';
import { SideBar } from './components/SideBar';
import { StatusBar } from './components/StatusBar';
import { TitleBar } from './components/TitleBar';
import { rpc, type WorkspaceLast } from './lib/rpc';
import { ShellContext, logLine, type ActivatedFile } from './lib/shell';
import {
  DataProcessingProvider,
  DataProcessingSettingsForm,
} from './tools/data_processing';
import { PdfToolsProvider, PdfToolsSettingsForm } from './tools/pdf_tools';
import {
  PlotCurvesProvider,
  PlotCurvesSettingsForm,
} from './tools/plot_curves';
import {
  ReportGeneratorProvider,
  ReportGeneratorSettingsForm,
} from './tools/report_generator';
import { TemplateHelperProvider } from './tools/template_helper';
import { Word2PdfProvider, Word2PdfSettingsForm } from './tools/word2pdf';

const TOP_TOOLS: ActivityItem[] = [
  { id: 'data_processing', icon: 'symbol-method', tooltip: '数据处理' },
  { id: 'plot_curves', icon: 'graph-line', tooltip: '绘曲线图' },
  { id: 'report_generator', icon: 'file-text', tooltip: '报告填充' },
  { id: 'template_helper', icon: 'list-tree', tooltip: '模板助手' },
  { id: 'pdf_tools', icon: 'file-pdf', tooltip: 'PDF 工具' },
  { id: 'word2pdf', icon: 'file-binary', tooltip: 'Word → PDF' },
];
const BOTTOM_TOOLS: ActivityItem[] = [
  { id: 'settings', icon: 'settings-gear', tooltip: '设置' },
];

const ALL_TOOLS = [...TOP_TOOLS, ...BOTTOM_TOOLS];

export default function App() {
  const [activeToolId, setActiveToolId] = useState<string>('data_processing');
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [sidecarStatus, setSidecarStatus] = useState<string>('连接中…');
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [collapseNonce, setCollapseNonce] = useState(0);
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [bottomVisible, setBottomVisible] = useState(true);
  const [rightVisible, setRightVisible] = useState(true);
  const [outputLog, setOutputLog] = useState('');
  const [activatedFile, setActivatedFile] = useState<ActivatedFile | null>(
    null,
  );
  const fileKeyRef = useRef(0);

  const sidebarRef = useRef<PanelImperativeHandle>(null);
  const bottomRef = useRef<PanelImperativeHandle>(null);
  const rightRef = useRef<PanelImperativeHandle>(null);

  /** 文件树双击 .xlsx/.docx/.pdf 时上抛；工具 Provider 自己用 useShell 监听 + 决定是否接收。 */
  const handleFileActivate = useCallback((path: string) => {
    fileKeyRef.current += 1;
    setActivatedFile({ path, key: fileKeyRef.current });
  }, []);

  const toolLabel =
    ALL_TOOLS.find((t) => t.id === activeToolId)?.tooltip ?? null;

  const appendOutput = useCallback((text: string) => {
    setOutputLog((prev) => (prev ? `${prev}\n${text}` : text));
    bottomRef.current?.expand();
    setBottomVisible(true);
  }, []);

  // 工作区路径变化时启动 OS 级文件系统监控；watch_workspace 内部自动替换旧监控。
  useEffect(() => {
    if (!workspacePath) return;
    invoke('watch_workspace', { path: workspacePath }).catch(console.error);
  }, [workspacePath]);

  // 监听 Rust 侧发来的 workspace-files-changed 事件，触发目录树刷新。
  // 只注册一次：unlisten 在组件卸载时清理。
  useEffect(() => {
    let cancelled = false;
    let stopListen: (() => void) | null = null;
    listen<null>('workspace-files-changed', () => {
      setRefreshNonce((n) => n + 1);
    })
      .then((fn) => {
        if (cancelled) fn();
        else stopListen = fn;
      })
      .catch(console.error);
    return () => {
      cancelled = true;
      stopListen?.();
    };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        // 并行 ping 两个 sidecar（Python + C#），任一失败状态栏显示错误
        const [pyPong, docPong] = await Promise.all([
          rpc<string>('ping'),
          rpc<string>('doc.ping'),
        ]);
        const status = `后端就绪 (py=${pyPong}, doc=${docPong})`;
        setSidecarStatus(status);
        appendOutput(logLine(status));
        const ws = await rpc<WorkspaceLast>('workspace.last');
        if (ws.path) {
          setWorkspacePath(ws.path);
          appendOutput(logLine(`恢复工作区: ${ws.path}`));
        }
      } catch (e) {
        const msg = `后端连接失败: ${String(e)}`;
        setSidecarStatus(msg);
        appendOutput(logLine(msg));
      }
    })();
    // 仅启动跑一次；appendOutput 是 useCallback 稳定引用，加进 deps 不影响
  }, [appendOutput]);

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

  // 拦截 webview 网页式行为：原生右键菜单 / F5 / Ctrl+R 重载 / Ctrl+P 打印 / Ctrl+S 另存 /
  // 拖文件到窗口被当作导航（会把 app 替换成 file:// URL）。
  // 自定义右键菜单（如 FileTree）自己在 onContextMenu 里 preventDefault，事件冒到 document
  // 时已被取消，这里再 preventDefault 也是 no-op；浏览器原生菜单不会出现。
  // 不拦 F12 / Ctrl+Shift+I，留给开发者工具。
  useEffect(() => {
    const onContextMenu = (e: MouseEvent) => e.preventDefault();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'F5') {
        e.preventDefault();
        return;
      }
      if (e.ctrlKey && !e.shiftKey && !e.altKey) {
        const k = e.key.toLowerCase();
        if (k === 'r' || k === 'p' || k === 's') e.preventDefault();
      }
    };
    const onDragOver = (e: DragEvent) => e.preventDefault();
    const onDrop = (e: DragEvent) => e.preventDefault();
    document.addEventListener('contextmenu', onContextMenu);
    document.addEventListener('keydown', onKey);
    document.addEventListener('dragover', onDragOver);
    document.addEventListener('drop', onDrop);
    return () => {
      document.removeEventListener('contextmenu', onContextMenu);
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('dragover', onDragOver);
      document.removeEventListener('drop', onDrop);
    };
  }, []);

  // 快捷键：Ctrl+J（底部 Panel）/ Ctrl+B（SideBar）/ Ctrl+Alt+B（右侧 Panel）
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (e.ctrlKey && !e.shiftKey && !e.altKey && k === 'j') {
        e.preventDefault();
        toggleBottom();
      } else if (e.ctrlKey && !e.shiftKey && !e.altKey && k === 'b') {
        e.preventDefault();
        handleExplorerToggle();
      } else if (e.ctrlKey && e.altKey && !e.shiftKey && k === 'b') {
        e.preventDefault();
        toggleRight();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggleBottom, handleExplorerToggle, toggleRight]);

  // SideBar 4 个按钮
  const handleOpenFolder = useCallback(async () => {
    try {
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: '选择工作区文件夹',
      });
      if (typeof selected !== 'string') return;
      await rpc('workspace.set', { path: selected });
      setWorkspacePath(selected);
      // 兜底：若用户重选了同一个路径，rootPath 不变，靠 nonce 触发 refetch
      setRefreshNonce((n) => n + 1);
    } catch (e) {
      console.error('打开文件夹失败:', e);
      alert(`打开文件夹失败：${String(e)}`);
    }
  }, []);

  const handleNewWorkspace = useCallback(async () => {
    try {
      const parent = await openDialog({
        directory: true,
        multiple: false,
        title: '选择父目录（在其下创建标准项目结构）',
      });
      if (typeof parent !== 'string') return;
      const name = window.prompt(
        '输入项目名（将在父目录下创建同名子文件夹 + 标准骨架）：',
      );
      if (!name || !name.trim()) return;
      const res = await rpc<{ ok: boolean; path: string }>(
        'workspace.create_standard',
        { parent_dir: parent, name: name.trim() },
      );
      await rpc('workspace.set', { path: res.path });
      setWorkspacePath(res.path);
      setRefreshNonce((n) => n + 1);
    } catch (e) {
      console.error('新建工作区失败:', e);
      alert(`新建工作区失败：${String(e)}`);
    }
  }, []);

  const handleRefresh = useCallback(() => setRefreshNonce((n) => n + 1), []);
  const handleCollapseAll = useCallback(
    () => setCollapseNonce((n) => n + 1),
    [],
  );

  const workspaceName = workspacePath
    ? (workspacePath.split(/[\\/]/).filter(Boolean).pop() ?? null)
    : null;

  // 右侧 Panel 多 tab：当前工具调参 + 常驻 AI 助手（占位）。
  // 调参 tab 只在该工具确实有 settings 时出现，AI 助手始终在。
  const rightTabs: RightTab[] = [
    ...(activeToolId === 'plot_curves'
      ? [
          {
            id: 'settings',
            label: '调参',
            icon: 'settings-gear',
            node: <PlotCurvesSettingsForm />,
          },
        ]
      : []),
    ...(activeToolId === 'data_processing'
      ? [
          {
            id: 'settings',
            label: '调参',
            icon: 'settings-gear',
            node: <DataProcessingSettingsForm />,
          },
        ]
      : []),
    ...(activeToolId === 'pdf_tools'
      ? [
          {
            id: 'settings',
            label: '调参',
            icon: 'settings-gear',
            node: <PdfToolsSettingsForm />,
          },
        ]
      : []),
    ...(activeToolId === 'word2pdf'
      ? [
          {
            id: 'settings',
            label: '调参',
            icon: 'settings-gear',
            node: <Word2PdfSettingsForm />,
          },
        ]
      : []),
    ...(activeToolId === 'report_generator'
      ? [
          {
            id: 'settings',
            label: '调参',
            icon: 'settings-gear',
            node: <ReportGeneratorSettingsForm />,
          },
        ]
      : []),
    { id: 'agent', label: 'AI 助手', icon: 'hubot', node: <AgentPanel /> },
  ];
  const rightAvailable = rightTabs.length > 0;

  const notifyFilesChanged = useCallback(
    () => setRefreshNonce((n) => n + 1),
    [],
  );

  const shellValue = {
    appendOutput,
    activeToolId,
    activatedFile,
    notifyFilesChanged,
  };

  return (
    <ShellContext.Provider value={shellValue}>
      <PlotCurvesProvider>
        <DataProcessingProvider>
          <ReportGeneratorProvider>
            <PdfToolsProvider>
              <TemplateHelperProvider>
                <Word2PdfProvider>
                <div className="flex h-screen w-screen flex-col">
                  <TitleBar
                    workspaceName={workspaceName}
                    toolLabel={toolLabel}
                  />

                  <div className="flex min-h-0 flex-1">
                    <ActivityBar
                      topItems={TOP_TOOLS}
                      bottomItems={BOTTOM_TOOLS}
                      activeId={activeToolId}
                      onChange={setActiveToolId}
                      explorerActive={sidebarVisible}
                      onExplorerToggle={handleExplorerToggle}
                    />

                    {/* 主 horizontal group：SideBar(全高) | 中间(Editor+底部 Panel 竖向) | RightPanel(全高) */}
                    <Group
                      orientation="horizontal"
                      id="civ-core-main"
                      className="flex min-w-0 flex-1"
                    >
                      <Panel
                        panelRef={sidebarRef}
                        defaultSize={200}
                        minSize={200}
                        maxSize={400}
                        collapsible
                        collapsedSize={0}
                        id="sidebar"
                        onResize={(s) =>
                          setSidebarVisible(s.asPercentage > 0.5)
                        }
                      >
                        <SideBar
                          workspacePath={workspacePath}
                          refreshNonce={refreshNonce}
                          collapseNonce={collapseNonce}
                          onOpenFolder={handleOpenFolder}
                          onNewWorkspace={handleNewWorkspace}
                          onRefresh={handleRefresh}
                          onCollapseAll={handleCollapseAll}
                          onFileActivate={handleFileActivate}
                        />
                      </Panel>
                      <Separator className="bg-vscode-border hover:bg-vscode-focus w-px transition-colors" />

                      {/* 中间：Editor + 底部 Panel 竖向分栏 */}
                      <Panel
                        defaultSize={rightAvailable ? 58 : 84}
                        minSize={30}
                        id="middle"
                      >
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
                          <Separator className="bg-vscode-border hover:bg-vscode-focus h-px transition-colors" />
                          <Panel
                            panelRef={bottomRef}
                            defaultSize={200}
                            minSize={150}
                            maxSize={400}
                            collapsible
                            collapsedSize={0}
                            id="bottom-panel"
                            onResize={(s) =>
                              setBottomVisible(s.asPercentage > 0.5)
                            }
                          >
                            <BottomPanel
                              output={outputLog}
                              onClose={toggleBottom}
                            />
                          </Panel>
                        </Group>
                      </Panel>

                      {/* 右侧 Panel：tab 化（调参 + AI 助手） */}
                      {rightAvailable && (
                        <Separator className="bg-vscode-border hover:bg-vscode-focus w-px transition-colors" />
                      )}
                      <Panel
                        panelRef={rightRef}
                        defaultSize={rightAvailable ? 400 : 0}
                        minSize={rightAvailable ? 300 : 500}
                        maxSize={rightAvailable ? 600 : 800}
                        collapsible
                        collapsedSize={0}
                        id="right-panel"
                        onResize={(s) => setRightVisible(s.asPercentage > 0.5)}
                      >
                        {rightAvailable && (
                          <RightPanel
                            tabs={rightTabs}
                            defaultActiveId="settings"
                            onClose={toggleRight}
                          />
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
              </TemplateHelperProvider>
            </PdfToolsProvider>
          </ReportGeneratorProvider>
        </DataProcessingProvider>
      </PlotCurvesProvider>
    </ShellContext.Provider>
  );
}
