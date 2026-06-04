// 防火涂层厚度三张 sheet 的名字 + 列名契约。
//
//   「类型预设」  构件类型 → 测点位置(逗号) + 默认设计厚度
//   「构件清单」  批次 / 构件位置 / 构件类型 / 长度(m) / 截面数 / 设计厚度  —— 用户主填
//   「测点数据」  批次 / 构件位置 / 构件类型 / 涂层类型 / 设计厚度 / 截面号 / <测点面名列…>  —— expand 生成，用户填数字
//
// 列名容错由 NormalizeHeader 抹平（与 AnchorColumns 同口径：trim + 全角括号/连字符 + 小写）。

using System.Text.RegularExpressions;

namespace CivCore.Doc.Calc.Coating;

public static class CoatingColumns
{
    // sheet 名
    public const string TypePresetSheet = "类型预设";
    public const string MemberListSheet = "构件清单";
    public const string PointDataSheet = "测点数据";

    // 通用列名
    public const string Batch = "批次";
    public const string MemberLocation = "构件位置";
    public const string MemberType = "构件类型";
    public const string DesignThickness = "设计厚度";
    public const string SectionNo = "截面号";
    /// <summary>国标膨胀型（薄/超薄）的索引列名：按 5 处布点，故叫「处号」（1~5，每处 3 测点）。</summary>
    public const string LocationNo = "处号";
    /// <summary>旧国标膨胀型索引列名（5 测点×3 次的错误模型）。仅 reader 向后兼容已生成的旧文件，不再生成。</summary>
    public const string PointNo = "测点号";
    public const string CoatingCategory = "涂层类型";

    // 「类型预设」专属列
    public const string PointPositions = "测点位置";
    public const string DefaultDesignThickness = "默认设计厚度";

    // 「构件清单」专属列
    public const string LengthM = "长度(m)";
    public const string SectionCount = "截面数";

    public const string DefaultBatchId = "全部";

    // 尾部单位/备注括注，如「默认设计厚度(mm)」「长度(m)」。土木工程师常顺手在列名标单位，
    // 不剥掉就匹配不上裸列名常量。全角括号已先转半角，故只需匹配半角；只剥末尾一组。
    private static readonly Regex TrailingParen = new(@"\([^()]*\)$", RegexOptions.Compiled);

    /// <summary>列名归一化：HeaderNormalizer.Core + 剥尾部单位括注（防火列名常带「(mm)」「(m)」等）。</summary>
    public static string NormalizeHeader(string s) => TrailingParen.Replace(HeaderNormalizer.Core(s), "");
}
