/**
 * report_generator 工具的公开导出 —— 装配线「报告填充」环节。
 * Provider 独立挂载，不依赖 DataProcessingProvider 嵌套：「一键导入」走 ShellContext
 * 的 dataProcessingSnapshot 显式快照消费（见 controller / lib/shell.ts），不再 useDataProcessing。
 *
 * 输入表单回归工具页范式：拆成 3 个调参 section，由 App.tsx 注入右侧 RightPanel
 * 的多 tab（数据 / 模板 / 项目字段），AI 助手常驻最后。中间页只放动作 + 结果。
 */
export { ReportGeneratorProvider } from './controller';
export { ReportGeneratorPage } from './Page';
export {
  ReportDataSection,
  ReportTemplateSection,
  ReportFieldsSection,
} from './SettingsForm';
