// coating.* RPC（GB 50205-2020 §13.4.3 防火涂料涂层厚度验收）。
//
// 流程（构件清单驱动）：
//   coating.generate_template(output_xlsx, standard?)              -> {ok, path}   出「类型预设」+「构件清单」模板
//   （用户填构件清单）
//   coating.expand_template(input_xlsx, output_xlsx?, standard?)   -> {ok, path, members, total_sections, sheets}  展开「测点数据-<类型>」网格
//   （用户在网格里填实测数字）
//   coating.run(input_xlsx, output_xlsx?, standard?, sheet?, batch_id_column?)
//                                                                  -> {batches, members_total, members_qualified, members_pending, output}
//   coating.list_batches(input_xlsx, sheet?, batch_id_column?)     -> {batches}    信息性
//
// 涂层类型按设计厚度自动分级：厚型按 80%+最薄85%；膨胀型(薄/超薄)按构件均值 ≥ 设计×0.95。
// 国标膨胀型按 5 处×3 点布点；地标按截面，间距随地标（国标 3m / 北京地标 1m）驱动 expand 截面数。

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.ReportTables;
using CivCore.Doc.Server;
using static CivCore.Doc.Server.AtomicFile;

namespace CivCore.Doc.Handlers;

public static class CoatingHandlers
{
    private const string CalcTypeSuffix = "防火涂层";

    public static void RegisterAll(Dispatcher d)
    {
        d.Register("coating.generate_template", GenerateTemplate);
        d.Register("coating.expand_template", ExpandTemplate);
        d.Register("coating.list_batches", ListBatches);
        d.Register("coating.run", Run);
        d.Register("coating.report", Report);
    }

    /// <summary>生成空白模板（类型预设 + 构件清单）。</summary>
    public static object GenerateTemplate(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var outputXlsx = p.GetProperty("output_xlsx").GetString()
            ?? throw new ArgumentException("未指定输出文件路径");
        string standard = OptString(p, "standard") ?? CoatingStandards.GB_50205_2020;

        var outDir = Path.GetDirectoryName(outputXlsx);
        if (!string.IsNullOrEmpty(outDir) && !Directory.Exists(outDir))
            throw new ArgumentException($"输出目录不存在：{outDir}");

        CoatingTemplateWriter.Write(outputXlsx, standard);
        return new Dictionary<string, object?> { ["ok"] = true, ["path"] = outputXlsx };
    }

    /// <summary>读「构件清单」展开成「测点数据-&lt;类型&gt;」网格（output 缺省写回 input）。</summary>
    public static object ExpandTemplate(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string standard = OptString(p, "standard") ?? CoatingStandards.GB_50205_2020;
        string outputXlsx = OptString(p, "output_xlsx") ?? inputXlsx;

        FileGuard.CheckExcelSize(inputXlsx);
        var r = CoatingTemplateExpander.Expand(inputXlsx, outputXlsx, standard);

        return new Dictionary<string, object?>
        {
            ["ok"] = true,
            ["path"] = outputXlsx,
            ["members"] = r.Members,
            ["total_sections"] = r.TotalSections,
            ["sheets"] = r.Sheets,
        };
    }

    /// <summary>读「测点数据」返回所有批次 ID（信息性）。</summary>
    public static object ListBatches(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? sheet = OptString(p, "sheet");
        string batchCol = OptString(p, "batch_id_column") ?? CoatingColumns.Batch;

        FileGuard.CheckExcelSize(inputXlsx);
        var batches = CoatingExcelReader.ListBatchIds(inputXlsx, sheet, batchCol);
        return new Dictionary<string, object?> { ["batches"] = batches };
    }

    /// <summary>读「测点数据」宽表 + 按构件聚合判定 + 每批写一个宽表 sheet。</summary>
    public static object Run(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? outputXlsx = OptString(p, "output_xlsx");
        string standard = OptString(p, "standard") ?? CoatingStandards.GB_50205_2020;
        string? sheet = OptString(p, "sheet");
        string batchCol = OptString(p, "batch_id_column") ?? CoatingColumns.Batch;

        FileGuard.CheckExcelSize(inputXlsx);
        CoatingStandards.Validate(standard);

        var src = new FileInfo(inputXlsx);
        string outPath = outputXlsx
            ?? Path.Combine(src.DirectoryName ?? "",
                $"{Path.GetFileNameWithoutExtension(src.Name)}_{CalcTypeSuffix}_结果.xlsx");

        var batchMembers = CoatingExcelReader.ReadRows(inputXlsx, sheet, batchCol);
        var batches = batchMembers
            .Select(b => new CoatingBatchInput(b.BatchId, b.Members.ToArray()))
            .ToArray();
        var workbook = new CoatingWorkbookInput(standard, batches);

        var result = CoatingCalculator.Calc(workbook);

        XLWorkbook wb = File.Exists(outPath) ? new XLWorkbook(outPath) : new XLWorkbook();
        using (wb)
        {
            foreach (var br in result.BatchResults)
            {
                var name = Calc.SheetNameUtil.Safe($"{br.BatchId}-数据分析");
                if (wb.Worksheets.TryGetWorksheet(name, out var old)) old.Delete();
                CoatingAnalysisSheet.Write(wb.Worksheets.Add(name), br, standard);
            }
            SaveWorkbook(wb, outPath);
        }

        return new Dictionary<string, object?>
        {
            ["batches"] = result.NBatches,
            ["members_total"] = result.NMembersTotal,
            ["members_qualified"] = result.NQualifiedTotal,
            ["members_pending"] = result.NPendingTotal,
            ["output"] = outPath,
        };
    }

    /// <summary>读「测点数据」+ 计算 + 把数据表填进 docx 薄壳模板（{{表格:防火涂层}} 占位符）→ 一键出 Word。</summary>
    public static object Report(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        var wordTemplate = p.TryGetProperty("word_template_path", out var wt)
            && wt.ValueKind == JsonValueKind.String ? wt.GetString() : null;
        if (string.IsNullOrWhiteSpace(wordTemplate))
            throw new ArgumentException("未指定 word_template_path（带 {{表格:防火涂层}} 占位符的 docx 薄壳模板）");
        string standard = OptString(p, "standard") ?? CoatingStandards.GB_50205_2020;
        string? sheet = OptString(p, "sheet");
        string batchCol = OptString(p, "batch_id_column") ?? CoatingColumns.Batch;
        string? outputDocx = OptString(p, "output_docx");
        var userInputs = ParseUserInputs(p);

        FileGuard.CheckExcelSize(inputXlsx);
        CoatingStandards.Validate(standard);
        if (!File.Exists(wordTemplate))
            throw new ArgumentException($"Word 模板不存在：{wordTemplate}");

        var batchMembers = CoatingExcelReader.ReadRows(inputXlsx, sheet, batchCol);
        var batches = batchMembers
            .Select(b => new CoatingBatchInput(b.BatchId, b.Members.ToArray()))
            .ToArray();
        var result = CoatingCalculator.Calc(new CoatingWorkbookInput(standard, batches));
        var members = result.BatchResults.SelectMany(br => br.MembersWithResults).ToList();

        var src = new FileInfo(inputXlsx);
        string outPath = outputDocx
            ?? Path.Combine(src.DirectoryName ?? "",
                $"{Path.GetFileNameWithoutExtension(src.Name)}_{CalcTypeSuffix}_报告.docx");

        var r = CoatingDocxReport.Generate(wordTemplate, outPath, members, standard, userInputs);

        return new Dictionary<string, object?>
        {
            ["output"] = outPath,
            ["tables"] = r.TablesInserted,
            ["replaced"] = r.Replaced,
            ["unknown_keys"] = r.UnknownKeys.ToList(),
            ["members"] = members.Count,
        };
    }

    // ── helpers ──

    private static Dictionary<string, string> ParseUserInputs(JsonElement p)
    {
        var d = new Dictionary<string, string>();
        if (p.TryGetProperty("user_inputs", out var el) && el.ValueKind == JsonValueKind.Object)
            foreach (var prop in el.EnumerateObject())
                if (prop.Value.ValueKind == JsonValueKind.String)
                    d[prop.Name] = prop.Value.GetString() ?? "";
        return d;
    }

    private static JsonElement RequireObject(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        return @params.Value;
    }

    private static string? OptString(JsonElement p, string name)
        => p.TryGetProperty(name, out var el) && el.ValueKind == JsonValueKind.String
            ? el.GetString()
            : null;
}
