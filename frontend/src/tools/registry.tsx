/**
 * 工具注册表 —— 唯一来源。
 *
 * 此前 App.tsx 把同一份「6 个工具」枚举重复了 4 次（ActivityBar 列表 / EditorArea switch /
 * rightTabs 三元 / Provider 金字塔），加一个工具要改 4 处、极易漏。这里收敛成一份描述：
 *   - TOOLS：id / 图标 / 名称 / 页面 / 右侧调参 tab —— 驱动 ActivityBar + EditorArea + RightPanel
 *   - TOOL_PROVIDERS：各工具 Context Provider —— 全在根挂载（持有各自 state，跨工具切换不丢）
 *   - ComposeProviders：把 Provider 列表嵌套起来（D1 后工具间无耦合，顺序仅保留历史 effect 次序）
 *
 * 加新工具：在 TOOLS + TOOL_PROVIDERS 各加一行即可，App.tsx 不用动。
 */
/* eslint-disable react-refresh/only-export-components -- 注册表本就是「数据(TOOLS) + ComposeProviders」同文件共存，非热更新组件库 */
import type { RightTab } from '../components/RightPanel';
import {
  DataProcessingPage,
  DataProcessingProvider,
  DataProcessingSettingsForm,
} from './data_processing';
import {
  PdfToolsPage,
  PdfToolsProvider,
  PdfToolsSettingsForm,
} from './pdf_tools';
import {
  PlotCurvesPage,
  PlotCurvesProvider,
  PlotCurvesSettingsForm,
} from './plot_curves';
import {
  ReportDataSection,
  ReportFieldsSection,
  ReportGeneratorPage,
  ReportGeneratorProvider,
  ReportTemplateSection,
} from './report_generator';
import { TemplateHelperPage, TemplateHelperProvider } from './template_helper';
import {
  Word2PdfPage,
  Word2PdfProvider,
  Word2PdfSettingsForm,
} from './word2pdf';

export interface ToolDef {
  id: string;
  /** codicon 名（不带 codicon- 前缀） */
  icon: string;
  label: string;
  Page: React.ComponentType<{ appendOutput: (line: string) => void }>;
  /** 右侧 RightPanel 的调参 tab（不含常驻「AI 助手」，App 统一追加）；无则不出调参 tab。 */
  settingsTabs?: RightTab[];
}

/** 单个「调参」tab 的常用工厂（多数工具就一个 settings tab）。 */
function settingsTab(node: React.ReactNode): RightTab[] {
  return [{ id: 'settings', label: '调参', icon: 'settings-gear', node }];
}

/** ActivityBar 顶部工具，顺序即展示顺序。 */
export const TOOLS: ToolDef[] = [
  {
    id: 'data_processing',
    icon: 'symbol-method',
    label: '数据处理',
    Page: DataProcessingPage,
    settingsTabs: settingsTab(<DataProcessingSettingsForm />),
  },
  {
    id: 'plot_curves',
    icon: 'graph-line',
    label: '绘曲线图',
    Page: PlotCurvesPage,
    settingsTabs: settingsTab(<PlotCurvesSettingsForm />),
  },
  {
    id: 'report_generator',
    icon: 'file-text',
    label: '报告填充',
    Page: ReportGeneratorPage,
    // 字段多，拆 3 个调参 tab（见 report_generator/SettingsForm.tsx）
    settingsTabs: [
      {
        id: 'rg-data',
        label: '数据',
        icon: 'table',
        node: <ReportDataSection />,
      },
      {
        id: 'rg-template',
        label: '模板',
        icon: 'files',
        node: <ReportTemplateSection />,
      },
      {
        id: 'rg-fields',
        label: '项目字段',
        icon: 'symbol-field',
        node: <ReportFieldsSection />,
      },
    ],
  },
  {
    id: 'template_helper',
    icon: 'list-tree',
    label: '模板助手',
    Page: TemplateHelperPage,
    // 无右侧调参（自身在中间页管字段目录）
  },
  {
    id: 'pdf_tools',
    icon: 'file-pdf',
    label: 'PDF 工具',
    Page: PdfToolsPage,
    settingsTabs: settingsTab(<PdfToolsSettingsForm />),
  },
  {
    id: 'word2pdf',
    icon: 'file-binary',
    label: 'Word → PDF',
    Page: Word2PdfPage,
    settingsTabs: settingsTab(<Word2PdfSettingsForm />),
  },
];

/**
 * 各工具 Context Provider —— 全部在根挂载（持有各自 state，切换工具不重置）。
 * D1 解耦后工具间无相互依赖，嵌套顺序无关紧要；此处保留历史顺序仅为不改变 effect 触发次序。
 */
const TOOL_PROVIDERS: React.ComponentType<{ children: React.ReactNode }>[] = [
  PlotCurvesProvider,
  DataProcessingProvider,
  ReportGeneratorProvider,
  PdfToolsProvider,
  TemplateHelperProvider,
  Word2PdfProvider,
];

/** 把 TOOL_PROVIDERS 依次嵌套（数组首个在最外层），包住 children。 */
export function ComposeProviders({ children }: { children: React.ReactNode }) {
  return TOOL_PROVIDERS.reduceRight(
    (acc, Provider) => <Provider>{acc}</Provider>,
    children,
  );
}
