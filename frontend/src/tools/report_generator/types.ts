/**
 * report_generator 工具的前端类型契约。
 *
 * 装配线「报告填充」环节：数据处理 → (可选) 绘曲线图 → ★ 报告填充 ★
 *
 * 字段定义已迁到后端 catalog（~/.civ-core/catalogs/<id>.json），前端不再硬编码 32 字段
 * 强类型；user_inputs 是 `Record<string, string>` 自由 map，key 由 catalog 决定。
 * 渲染走 [[CatalogDrivenInputs]] 公共组件，模板助手改字段后这边立刻同步。
 *
 * 批次级字段（同一项目不同批次值不同）仍走 ReportBatchUserInputs，目前只有「灌浆日期」
 * 一个；P4 会把这部分也接入 catalog 的 level=batch 字段自动渲染。
 */

/** 报告级 + 检测项目级用户输入 —— 自由 map，key 由 catalog 字段定义。 */
export type ReportUserInputs = Record<string, string>;

/**
 * 批次级 user_inputs —— 同一项目不同批次值不同的字段（目前只有「灌浆日期」）。
 *
 * P4 会把所有 level=batch 字段自动接入；当前先白名单维护方便兼容。
 */
export interface ReportBatchUserInputs {
  grouting_date: string;
}

export const DEFAULT_REPORT_BATCH_USER_INPUTS: ReportBatchUserInputs = {
  grouting_date: '',
};

/** 哪些 catalog key 是「批次维度」字段 —— 前端白名单，P4 改成读 catalog level=batch。 */
export const BATCH_DIM_KEYS = ['grouting_date'] as const;
export type BatchDimKey = (typeof BATCH_DIM_KEYS)[number];

/** 当前装配线锚定的 catalog id —— P4 会改成可选择的检测项目下拉。 */
export const DEFAULT_CATALOG_ID = 'anchor';

/** 报告生成结果（前端渲染用）。 */
export interface ReportRunRes {
  output: string;
  rowsRendered: number;
  unknownKeys: string[];
  /** {{img:xxx}} 图片占位符解析失败的列表（缺路径 / 文件不存在）—— 前端警告用。 */
  missingImages: string[];
}
