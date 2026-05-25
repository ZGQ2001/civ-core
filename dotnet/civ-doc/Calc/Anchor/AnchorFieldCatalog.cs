// 锚杆抗拔报告可绑定字段清单（GB 50086-2015）。
//
// 这是模板编辑器的「字段菜单」—— 用户在 Word 表格里选一个格子，从这个清单挑字段绑定上去。
//
// 解耦：本文件依赖 Template/FieldDef.cs（通用类型），但 Template 引擎不依赖本文件；
//       未来加钻芯/回弹只需要新增 Calc/<Type>/<Type>FieldCatalog.cs，引擎零改动。
//
// Key 命名规则：
//   - snake_case（跨语言友好，跟 RPC 习惯一致）
//   - 主键稳定：规范换术语只改 Name，绝不改 Key
//   - 加载等级用 nt 倍数（"d01nt_disp" = 0.1Nt 时位移），跟 AnchorColumns 表头逻辑对齐

using CivCore.Doc.Template;

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorFieldCatalog
{
    /// <summary>所有可绑定字段（按报告版面分组顺序排列，方便前端 BindingPanel 直接渲染）。</summary>
    public static readonly FieldDef[] All =
    [
        // ── 委托方/工程参数（同批次共享，从 AnchorParams 取） ──
        FieldDef.Create("axial_design_load", "轴向拉力设计值 P (N)", FieldSource.Parameter, "double", "0.00"),
        FieldDef.Create("free_length",       "自由段长度 Lf (mm)",   FieldSource.Parameter, "double", "0.0"),
        FieldDef.Create("anchor_length",     "锚固段长度 La (mm)",   FieldSource.Parameter, "double", "0.0"),
        FieldDef.Create("steel_area",        "钢筋面积 A (mm²)",     FieldSource.Parameter, "double", "0.00"),
        FieldDef.Create("elastic_modulus",   "弹性模量 E (N/mm²)",   FieldSource.Parameter, "double", "0"),

        // ── 单根锚杆原始数据（AnchorRowInput） ──
        FieldDef.Create("anchor_id",  "锚杆编号", FieldSource.RawInput, "string"),
        FieldDef.Create("disp_01nt",  "0.1Nt 时位移 (mm)",        FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_04nt",  "0.4Nt 时位移 (mm)",        FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_07nt",  "0.7Nt 时位移 (mm)",        FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_10nt",  "1.0Nt 时位移 (mm)",        FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_12nt_1min", "1.2Nt 持荷 1min (mm)", FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_12nt_3min", "1.2Nt 持荷 3min (mm)", FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_12nt_5min", "1.2Nt 持荷 5min (mm)", FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_unload_10nt", "卸载至 1.0Nt (mm)",  FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_unload_07nt", "卸载至 0.7Nt (mm)",  FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_unload_04nt", "卸载至 0.4Nt (mm)",  FieldSource.RawInput, "double", "0.00"),
        FieldDef.Create("disp_unload_01nt", "卸载至 0.1Nt (mm)",  FieldSource.RawInput, "double", "0.00"),

        // ── 计算结果（AnchorRowResult） ──
        FieldDef.Create("elastic_displacement", "弹性位移量 M (mm)", FieldSource.Calculated, "double", "0.00"),
        FieldDef.Create("lower_limit",          "判定下限 Q (mm)",   FieldSource.Calculated, "double", "0.00"),
        FieldDef.Create("upper_limit",          "判定上限 R (mm)",   FieldSource.Calculated, "double", "0.00"),
        FieldDef.Create("judgement_result",     "判定结果",          FieldSource.Calculated, "string"),

        // ── 用户输入（前端表单收集，非计算产物） ──
        FieldDef.Create("client_name",     "委托单位",   FieldSource.UserInput, "string"),
        FieldDef.Create("project_name",    "工程名称",   FieldSource.UserInput, "string"),
        FieldDef.Create("test_date",       "试验日期",   FieldSource.UserInput, "string"),
        FieldDef.Create("test_engineer",   "试验人员",   FieldSource.UserInput, "string"),
    ];
}
