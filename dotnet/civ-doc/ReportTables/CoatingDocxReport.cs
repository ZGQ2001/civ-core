// 防火涂层「一键 Word 报告」—— 现在是 DocxReportAssembler 的单 section 薄包装。
//
//   薄壳（封面/项目信息主表/结论/页眉）：用户在模板里写 {{委托单位}}/{{检测结论}} 等占位符。
//   数据表：用户在要放表处写一段「{{表格:防火涂层}}」占位符
//     → 程序按规范格式建好的表（CoatingWordTable.BuildAll）插在该处。
//
// 表的内部格式固定在代码（判错=事故，规范统一）；薄壳走占位符（甲方可改、换模板零代码）。
// 多检测类型组装见 DocxReportAssembler / report.assemble。

using CivCore.Doc.Calc.Coating;

namespace CivCore.Doc.ReportTables;

public static class CoatingDocxReport
{
    /// <summary>数据表占位符 —— 用户在模板里要放表的位置写这一段。</summary>
    public const string TablePlaceholder = "{{表格:防火涂层}}";

    public record Result(int TablesInserted, int Replaced, IReadOnlyList<string> UnknownKeys);

    /// <summary>
    /// 用 templatePath 薄壳模板生成 outputPath docx：在 {{表格:防火涂层}} 处插入数据表，
    /// 其余 {{}} 占位符按 userInputs 填。members 为单批构件计算结果。
    /// </summary>
    public static Result Generate(
        string templatePath,
        string outputPath,
        IReadOnlyList<(CoatingMemberInput Input, CoatingMemberResult Result)> members,
        string standard,
        IReadOnlyDictionary<string, string> userInputs)
    {
        if (members.Count == 0)
            throw new ArgumentException("没有构件计算结果可填入报告");

        var section = new ReportSection(
            TablePlaceholder,
            _ => SectionBuild.Plain(CoatingWordTable.BuildAll(members, standard)));

        var r = DocxReportAssembler.Generate(
            templatePath, outputPath, new[] { section }, userInputs, catalog: null);

        return new Result(r.TablesInserted, r.Replaced, r.UnknownKeys);
    }
}
