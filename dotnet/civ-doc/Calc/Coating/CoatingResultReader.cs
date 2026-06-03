// 反向读防火涂层结果 xlsx —— 让 coating.report / report.assemble 不重算就出 Word。
//
// 来源 xlsx 由 coating.run 产出（CoatingAnalysisSheet 人看宽表 + CoatingResultMetadataSheet 机读长表）。
// 本 reader 只读机读 sheet（全精度、列序固定），直接拼回 CoatingWorkbookResult，绕开
// CoatingCalculator.Calc 那一步。对齐锚杆 AnchorResultReader 的「读结果不重算」。
//
// 兼容性：缺机读 sheet（旧版本生成的结果 xlsx，或根本不是 coating.run 出的）→ 报清晰错误，
// 提示用户重新跑「数据处理」。

using ClosedXML.Excel;
using CivCore.Doc.ReportTables;

namespace CivCore.Doc.Calc.Coating;

public static class CoatingResultReader
{
    /// <summary>读结果 xlsx → CoatingWorkbookResult（不重算）。standard 由调用方传入，与结果 xlsx 不绑定。</summary>
    public static CoatingWorkbookResult Read(string resultXlsxPath, string standard)
    {
        if (!File.Exists(resultXlsxPath))
            throw new ArgumentException($"结果 xlsx 文件不存在：{resultXlsxPath}");

        using var wb = new XLWorkbook(resultXlsxPath);
        var result = CoatingResultMetadataSheet.Read(wb, standard);
        if (result.NBatches == 0)
            throw new InvalidOperationException(
                $"结果 xlsx 缺「{CoatingResultMetadataSheet.SheetName}」sheet 或无数据 —— 无法重建防火涂层结果。" +
                "请重新跑「数据处理」(coating.run) 生成结果 xlsx（旧版本生成的不带机读结果 sheet）。");
        return result;
    }
}
