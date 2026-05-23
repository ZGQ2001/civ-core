/**
 * EditorArea：按 activeToolId 路由到各工具页。
 * appendOutput 透传给工具页，工具页跑完往底部 Panel 输出 Tab 写日志摘要。
 */
import { DataProcessingPage } from '../tools/data_processing';
import { PdfToolsPage } from '../tools/pdf_tools';
import { Placeholder } from '../tools/Placeholder';
import { PlotCurvesPage } from '../tools/plot_curves';
import { Word2PdfPage } from '../tools/word2pdf';

interface Props {
  activeToolId: string | null;
  toolLabel: string | null;
  appendOutput: (text: string) => void;
}

export function EditorArea({ activeToolId, toolLabel, appendOutput }: Props) {
  return (
    <div className="bg-vscode-bg flex h-full min-w-0 flex-col">
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
    case 'plot_curves':
      return <PlotCurvesPage appendOutput={appendOutput} />;
    case 'data_processing':
      return <DataProcessingPage appendOutput={appendOutput} />;
    case 'pdf_tools':
      return <PdfToolsPage appendOutput={appendOutput} />;
    case 'word2pdf':
      return <Word2PdfPage appendOutput={appendOutput} />;
    case 'settings':
      return (
        <Placeholder
          icon="settings-gear"
          label={label ?? '设置'}
          detail="后续接入"
        />
      );
    default:
      return (
        <Placeholder
          icon="tools"
          label={label ?? '请选择工具'}
          detail="从左侧 Activity Bar 选一个工具"
        />
      );
  }
}
