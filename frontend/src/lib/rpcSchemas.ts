/**
 * 关键 RPC 响应的运行时 zod schema —— 在边界把「后端契约漂移」显式化。
 *
 * 为什么：`rpc<T>` 的 `as T` 无运行时校验，后端字段缺失/改名只在渲染时静默炸或出错报告
 * （主 CLAUDE.md：「出错代价是工程事故」）。最近的 `source: 'user_input' vs 'userinput'`
 * 漂移就是静默丢了 23 个字段。这里给出错代价最高的核心方法加边界校验，宁可拒绝也不放行脏数据。
 *
 * 范围（只覆盖核心，不全量——避免 schema 维护成本压过收益）：
 *   - anchor.run / report.run_from_result：锚杆计算 + 出 Word 报告
 *   - catalog.get：字段目录（报告填充「项目字段」渲染依赖它）
 *
 * 安全性：zod object 默认 strip 未知键 —— 后端多返字段不会误拒，只在「缺必需字段 / 类型不符」时抛。
 * 各字段的可选性严格对齐现有 TS 调用点类型，避免误拒合法响应。
 */
import { z } from 'zod';

/** anchor.run / report.run_from_result 的统一返回。word_* 仅出报告路径返回，故 optional。 */
export const anchorRunResultSchema = z.object({
  batches: z.number(),
  anchors_total: z.number(),
  anchors_qualified: z.number(),
  output: z.string(),
  word_outputs: z.array(z.string()).optional(),
  word_unknown_keys: z.array(z.string()).optional(),
  word_missing_images: z.array(z.string()).optional(),
});

/** report.assemble 返回（多检测类型一键组装 Word）。 */
export const reportAssembleResultSchema = z.object({
  output: z.string(),
  tables: z.number(),
  replaced: z.number(),
  unknown_keys: z.array(z.string()),
  missing_images: z.array(z.string()),
  sections: z.array(z.string()),
});

/** coating.run 返回（厚涂型防火涂层厚度验收）。member 单位的计数，无 Word 路径。 */
export const coatingRunResultSchema = z.object({
  batches: z.number(),
  members_total: z.number(),
  members_qualified: z.number(),
  members_pending: z.number().optional(), // 薄型/超薄型待接入数
  output: z.string(),
});

/** 与 template_helper/types 的 CatalogField 对齐（调用点 setCatalog 会做编译期可赋值检查）。 */
const catalogFieldSchema = z.object({
  key: z.string(),
  name: z.string(),
  group: z.string(),
  level: z.enum(['report', 'detection_item', 'batch', 'component']),
  source: z.string(),
  value_type: z.string(),
  default_format: z.string().nullable(),
  aliases: z.array(z.string()),
});

/** catalog.get 返回 { catalog: FieldCatalog }。 */
export const catalogGetResultSchema = z.object({
  catalog: z.object({
    id: z.string(),
    label: z.string(),
    fields: z.array(catalogFieldSchema),
  }),
});
