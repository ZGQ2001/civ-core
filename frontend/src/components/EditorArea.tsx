/**
 * EditorArea：按 activeToolId 路由到各工具页。
 * T5：plot_curves 已端到端；其他工具页用 Placeholder 占位，等后续轮次接入。
 */
import { Placeholder } from "../tools/Placeholder";
import { PlotCurvesTool } from "../tools/PlotCurvesTool";

interface Props {
  activeToolId: string | null;
  toolLabel: string | null;
}

export function EditorArea({ activeToolId, toolLabel }: Props) {
  return (
    <div className="flex h-full flex-col bg-vscode-bg min-w-0">
      {renderTool(activeToolId, toolLabel)}
    </div>
  );
}

function renderTool(id: string | null, label: string | null) {
  switch (id) {
    case "plot_curves":
      return <PlotCurvesTool />;
    case "leeb_hardness":
      return <Placeholder icon="symbol-numeric" label={label ?? "里氏硬度"} detail="T5.2 接入" />;
    case "pdf_tools":
      return <Placeholder icon="file-pdf" label={label ?? "PDF 工具"} detail="T5.3 接入" />;
    case "word2pdf":
      return <Placeholder icon="file-binary" label={label ?? "Word → PDF"} detail="T5.4 接入" />;
    case "settings":
      return <Placeholder icon="settings-gear" label={label ?? "设置"} detail="后续接入" />;
    default:
      return <Placeholder icon="tools" label={label ?? "请选择工具"} detail="从左侧 Activity Bar 选一个工具" />;
  }
}
