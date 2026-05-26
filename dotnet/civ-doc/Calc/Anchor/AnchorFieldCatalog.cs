// 锚杆抗拔报告可绑定字段清单（GB 50086-2015）。
//
// 这是模板编辑器的「字段菜单」—— 用户在 Word 表格里选一个格子，从这个清单挑字段绑定上去。
//
// 解耦：本文件依赖 Template/FieldDef.cs（通用类型），但 Template 引擎不依赖本文件；
//       未来加钻芯/回弹只需要新增 Calc/<Type>/<Type>FieldCatalog.cs，引擎零改动。
//
// Key 命名规则：
//   - snake_case（跨语言友好，跟 RPC 习惯一致）
//   - 主键稳定：规范换术语只改 Name 或加 Alias，绝不改 Key
//   - 加载等级用 nt 倍数（"d01nt_disp" = 0.1Nt 时位移），跟 AnchorColumns 表头逻辑对齐
//
// Alias 用法：用户在 Word 模板里可能写短名（如 {{0.1Nt位移}}），不是 catalog 的完整 Name
// （"0.1Nt 时位移 (mm)"）。Aliases 让引擎反查时也命中。

using CivCore.Doc.Template;

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorFieldCatalog
{
    /// <summary>所有可绑定字段（按报告版面分组顺序排列，方便前端 BindingPanel 直接渲染）。</summary>
    public static readonly FieldDef[] All =
    [
        // ── 批次标识 ──
        FieldDef.Create("batch_id", "批次编号", FieldSource.Parameter, "string"),

        // ── 委托方/工程参数（同批次共享，从 AnchorParams 取） ──
        // axial_design_load 内部单位 N（计算 M = N·L/(A·E) 要 N）；
        // 报告里展示用 kN，见下面的 axial_design_load_kn 派生字段。
        FieldDef.Create("axial_design_load", "轴向拉力设计值 P (N)", FieldSource.Parameter, "double", "0.00"),
        FieldDef.Create("free_length", "自由段长度 Lf (mm)", FieldSource.Parameter, "double", "0.0",
            aliases: ["自由段长度"]),
        FieldDef.Create("anchor_length", "锚固段长度 La (mm)", FieldSource.Parameter, "double", "0.0",
            aliases: ["锚固段长度"]),
        FieldDef.Create("steel_area", "钢筋面积 A (mm²)", FieldSource.Parameter, "double", "0.00",
            aliases: ["钢筋面积"]),
        FieldDef.Create("elastic_modulus", "弹性模量 E (N/mm²)", FieldSource.Parameter, "double", "0",
            aliases: ["弹性模量", "杆体弹模"]),

        // ── 单根锚杆原始数据（AnchorRowInput） ──
        FieldDef.Create("anchor_id", "锚杆编号", FieldSource.RawInput, "string"),
        FieldDef.Create("disp_01nt", "0.1Nt 时位移 (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["0.1Nt位移", "0.1Nt"]),
        FieldDef.Create("disp_04nt", "0.4Nt 时位移 (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["0.4Nt位移", "0.4Nt"]),
        FieldDef.Create("disp_07nt", "0.7Nt 时位移 (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["0.7Nt位移", "0.7Nt"]),
        FieldDef.Create("disp_10nt", "1.0Nt 时位移 (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["1.0Nt位移", "1.0Nt"]),
        FieldDef.Create("disp_12nt_1min", "1.2Nt 持荷 1min (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["1.2Nt-1min"]),
        FieldDef.Create("disp_12nt_3min", "1.2Nt 持荷 3min (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["1.2Nt-3min"]),
        // 用户模板里写 {{1.2Nt位移}} 默认取 5min（持荷时间最长，规范一般取最终稳定值）
        FieldDef.Create("disp_12nt_5min", "1.2Nt 持荷 5min (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["1.2Nt位移", "1.2Nt-5min", "1.2Nt"]),
        FieldDef.Create("disp_unload_10nt", "卸载至 1.0Nt (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["卸载1.0Nt位移", "卸载1.0Nt"]),
        FieldDef.Create("disp_unload_07nt", "卸载至 0.7Nt (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["卸载0.7Nt位移", "卸载0.7Nt"]),
        FieldDef.Create("disp_unload_04nt", "卸载至 0.4Nt (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["卸载0.4Nt位移", "卸载0.4Nt"]),
        FieldDef.Create("disp_unload_01nt", "卸载至 0.1Nt (mm)", FieldSource.RawInput, "double", "0.00",
            aliases: ["卸载0.1Nt位移", "卸载0.1Nt"]),

        // ── 计算结果（AnchorRowResult） ──
        // M 是在最大试验荷载（1.2Nt）下的弹性位移量；用户模板里常写 "最大试验荷载下弹性位移量"
        // 作短名，这里加 alias 命中。
        FieldDef.Create("elastic_displacement", "弹性位移量 M (mm)", FieldSource.Calculated, "double", "0.00",
            aliases: ["弹性位移量", "最大试验荷载下弹性位移量"]),
        FieldDef.Create("lower_limit", "判定下限 Q (mm)", FieldSource.Calculated, "double", "0.00",
            aliases: ["允许值下限", "判定下限"]),
        FieldDef.Create("upper_limit", "判定上限 R (mm)", FieldSource.Calculated, "double", "0.00",
            aliases: ["允许值上限", "判定上限"]),
        FieldDef.Create("judgement_result", "判定结果", FieldSource.Calculated, "string"),
        // 锚杆序号：引擎按克隆次序自动注入 1/2/3...，模板写 {{锚杆序号}} 即可
        FieldDef.Create("anchor_index", "锚杆序号", FieldSource.Calculated, "int"),
        // 派生字段：轴向拉力设计值的 kN 表示 —— 报告版面常用 kN，引擎自动 / 1000。
        // alias "轴向拉力设计值" 默认命中此字段，模板里写 {{轴向拉力设计值}} 输出 kN。
        FieldDef.Create("axial_design_load_kn", "轴向拉力设计值 (kN)", FieldSource.Calculated, "double", "0",
            aliases: ["轴向拉力设计值"]),

        // ── 用户输入：项目信息（前端表单收集） ──
        FieldDef.Create("client_name", "委托单位", FieldSource.UserInput, "string"),
        FieldDef.Create("project_name", "工程名称", FieldSource.UserInput, "string",
            aliases: ["项目名称"]),
        FieldDef.Create("report_no", "报告编号", FieldSource.UserInput, "string"),
        FieldDef.Create("supervisor_unit", "监理单位", FieldSource.UserInput, "string"),
        FieldDef.Create("designer_unit", "设计单位", FieldSource.UserInput, "string"),
        FieldDef.Create("constructor_unit", "施工单位", FieldSource.UserInput, "string"),
        FieldDef.Create("inspection_category", "检测类别", FieldSource.UserInput, "string"),
        FieldDef.Create("inspection_item", "检测项目", FieldSource.UserInput, "string"),
        FieldDef.Create("inspection_site", "检测地点", FieldSource.UserInput, "string"),
        FieldDef.Create("inspection_basis", "检测及判定依据", FieldSource.UserInput, "string"),
        FieldDef.Create("inspection_conclusion", "检测结论", FieldSource.UserInput, "string"),
        // 检测时间 / 检测人员同时覆盖原"试验日期 / 试验人员"语义（实际报告里一般是同一组人/日期）
        FieldDef.Create("inspection_time", "检测时间", FieldSource.UserInput, "string",
            aliases: ["试验日期"]),
        FieldDef.Create("inspection_engineer", "检测人员", FieldSource.UserInput, "string",
            aliases: ["试验人员"]),

        // ── 用户输入：检测仪器 ──
        FieldDef.Create("instrument1_name", "检测仪器1", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument1_no", "检测仪器1编号", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument1_cert_no", "检测仪器1证书编号", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument1_valid_until", "检测仪器1使用有效期", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument1_precision", "检测仪器1检测精度", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument2_name", "检测仪器2", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument2_no", "检测仪器2编号", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument2_cert_no", "检测仪器2证书编号", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument2_valid_until", "检测仪器2使用有效期", FieldSource.UserInput, "string"),
        FieldDef.Create("instrument2_precision", "检测仪器2检测精度", FieldSource.UserInput, "string"),

        // ── 用户输入：锚杆/工程参数描述 ──
        // 这些字段当前按项目级（一份报告填一次）；如果同一份报告里这些值会变化
        // （例如锚杆灌浆日期不同），约定的做法是把数据拆成多批输入——
        // 一批 = 一组共享元信息，多批合成一份报告（走 GenerateMultiBatch 模式）。
        // 若未来真要按"每根锚杆"变化，应从 user_input 改成 RawInput + 加输入 Excel 列。
        FieldDef.Create("rock_soil_property", "岩土性状", FieldSource.UserInput, "string"),
        FieldDef.Create("bar_material_spec", "杆体材料规格", FieldSource.UserInput, "string"),
        FieldDef.Create("grouting_date", "灌浆日期", FieldSource.UserInput, "string"),
        FieldDef.Create("grout_ratio", "注浆材料配合比", FieldSource.UserInput, "string"),
        FieldDef.Create("grout_strength", "注浆材料强度等级", FieldSource.UserInput, "string"),
        FieldDef.Create("drill_angle", "钻孔倾角", FieldSource.UserInput, "string"),
        FieldDef.Create("drill_diameter", "钻孔直径", FieldSource.UserInput, "string"),

        // ── 图片占位符（Commit 3 才真正注入图片，当前先作 string 占位） ──
        // 用户模板里写 {{曲线图}}，目前作 user_input 让用户填路径或描述；
        // Commit 3 会改成 {{img:曲线图}} 自动嵌入 plot_curves 生成的 PNG。
        FieldDef.Create("curve_image", "曲线图", FieldSource.UserInput, "string"),
    ];
}
