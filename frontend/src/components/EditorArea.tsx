/**
 * EditorArea：按 activeToolId 路由到各工具页。
 * appendOutput 透传给工具页，工具页跑完往底部 Panel 输出 Tab 写日志摘要。
 */
import { LeebHardnessTool } from "../tools/LeebHardnessTool";
import { PdfToolsTool } from "../tools/PdfToolsTool";
import { Placeholder } from "../tools/Placeholder";
import { PlotCurvesTool } from "../tools/PlotCurvesTool";
import { Word2PdfTool } from "../tools/Word2PdfTool";

interface Props {
  activeToolId: string | null;
  toolLabel: string | null;
  appendOutput: (text: string) => void;
}

export function EditorArea({ activeToolId, toolLabel, appendOutput }: Props) {
  return (
    <div className="flex h-full flex-col bg-vscode-bg min-w-0">
      {renderTool(activeToolId, toolLabel, appendOutput)}
    </div>
  );
}

function renderTool(
  id: string | null,
  label: string | null,
  appendOutput: (text: string) => void,
) {
  switch (id) {
    case "plot_curves":
      return <PlotCurvesTool appendOutput={appendOutput} />;
    case "leeb_hardness":
      return <LeebHardnessTool appendOutput={appendOutput} />;
    case "pdf_tools":
      return <PdfToolsTool appendOutput={appendOutput} />;
    case "word2pdf":
      return <Word2PdfTool appendOutput={appendOutput} />;
    case "settings":
      return <Placeholder icon="settings-gear" label={label ?? "设置"} detail="后续接入" />;
    default:
      return (
        <Placeholder icon="tools" label={label ?? "请选择工具"} detail="从左侧 Activity Bar 选一个工具" />
      );
  }
}
