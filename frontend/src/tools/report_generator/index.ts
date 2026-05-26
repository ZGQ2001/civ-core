/**
 * report_generator 工具的公开导出 —— 装配线「报告填充」环节。
 * Provider 必须嵌套在 DataProcessingProvider 内层（依赖 useDataProcessing）。
 * SettingsForm 合并到 Page 正中渲染，不再单独导出。
 */
export { ReportGeneratorProvider } from './controller';
export { ReportGeneratorPage } from './Page';
