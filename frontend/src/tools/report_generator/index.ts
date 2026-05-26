/**
 * report_generator 工具的公开导出 —— 装配线「报告填充」环节。
 * 四件套：Provider / Page / SettingsForm。
 * Provider 必须嵌套在 DataProcessingProvider 内层（依赖 useDataProcessing）。
 */
export { ReportGeneratorProvider } from './controller';
export { ReportGeneratorPage } from './Page';
export { ReportGeneratorSettingsForm } from './SettingsForm';
