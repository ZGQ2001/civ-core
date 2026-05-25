// anchor.* RPC 方法注册与实现（GB 50086-2015 锚杆抗拔试验）。
//
// 方法清单：
//   anchor.generate_template(output_xlsx, standard?)
//     -> {ok, path}
//   anchor.list_batches(input_xlsx, sheet?, batch_id_column?)
//     -> {batches: [str, ...]}
//   anchor.run(input_xlsx, output_xlsx?, standard, batch_id_column?, params_by_batch)
//     -> {batches, anchors_total, anchors_qualified, output}
//
// 输出 xlsx 由 anchor.run 直接写（不像 leeb 那样拆 Python+C# 两步——这里全 C#，
// 没有跨 sidecar 协作）。每批 2 sheet：「<批>-数据分析」+「<批>-报告内插表」。

using System.Text.Json;
using ClosedXML.Excel;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.ReportTables;
using CivCore.Doc.Server;
using CivCore.Doc.Template;
using static CivCore.Doc.Server.AtomicFile;

namespace CivCore.Doc.Handlers;

public static class AnchorHandlers
{
    private const string CalcTypeSuffix = "锚杆";

    public static void RegisterAll(Dispatcher d)
    {
        d.Register("anchor.generate_template", GenerateTemplate);
        d.Register("anchor.list_batches", ListBatches);
        d.Register("anchor.run", Run);
    }

    /// <summary>生成空白输入模板。前端「生成模板」按钮调。</summary>
    public static object GenerateTemplate(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var outputXlsx = p.GetProperty("output_xlsx").GetString()
            ?? throw new ArgumentException("未指定输出文件路径");
        string standard = p.TryGetProperty("standard", out var sEl)
            && sEl.ValueKind == JsonValueKind.String
            ? sEl.GetString() ?? AnchorStandards.GB_50086_2015
            : AnchorStandards.GB_50086_2015;

        var outDir = Path.GetDirectoryName(outputXlsx);
        if (!string.IsNullOrEmpty(outDir) && !Directory.Exists(outDir))
            throw new ArgumentException($"输出目录不存在：{outDir}");

        AnchorTemplateWriter.Write(outputXlsx, standard);

        return new Dictionary<string, object?>
        {
            ["ok"] = true,
            ["path"] = outputXlsx,
        };
    }

    /// <summary>读输入 Excel 返回所有批次 ID（前端 SettingsForm 按批次填参数前用）。</summary>
    public static object ListBatches(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? sheet = p.TryGetProperty("sheet", out var sEl)
            && sEl.ValueKind == JsonValueKind.String ? sEl.GetString() : null;
        string batchCol = p.TryGetProperty("batch_id_column", out var bEl)
            && bEl.ValueKind == JsonValueKind.String
            ? bEl.GetString() ?? AnchorColumns.DefaultBatchIdColumn
            : AnchorColumns.DefaultBatchIdColumn;

        FileGuard.CheckExcelSize(inputXlsx);
        var batches = AnchorExcelReader.ListBatchIds(inputXlsx, sheet, batchCol);
        return new Dictionary<string, object?> { ["batches"] = batches };
    }

    /// <summary>读 Excel + 按批次套参数 + 算 + 写两个 sheet/批 输出。</summary>
    public static object Run(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var inputXlsx = p.GetProperty("input_xlsx").GetString()
            ?? throw new ArgumentException("未指定输入 Excel 文件");
        string? outputXlsx = p.TryGetProperty("output_xlsx", out var outEl)
            && outEl.ValueKind == JsonValueKind.String ? outEl.GetString() : null;
        string standard = p.TryGetProperty("standard", out var sEl)
            && sEl.ValueKind == JsonValueKind.String
            ? sEl.GetString() ?? AnchorStandards.GB_50086_2015
            : AnchorStandards.GB_50086_2015;
        string? sheet = p.TryGetProperty("sheet", out var shEl)
            && shEl.ValueKind == JsonValueKind.String ? shEl.GetString() : null;
        string batchCol = p.TryGetProperty("batch_id_column", out var bEl)
            && bEl.ValueKind == JsonValueKind.String
            ? bEl.GetString() ?? AnchorColumns.DefaultBatchIdColumn
            : AnchorColumns.DefaultBatchIdColumn;

        FileGuard.CheckExcelSize(inputXlsx);

        // 可选 Word 模板路径（带占位符 + [[每根锚杆]] 锚点）。给了就出 Word 报告。
        string? wordTemplatePath = p.TryGetProperty("word_template_path", out var wtEl)
            && wtEl.ValueKind == JsonValueKind.String ? wtEl.GetString() : null;
        string? wordOutputDir = p.TryGetProperty("word_output_dir", out var woEl)
            && woEl.ValueKind == JsonValueKind.String ? woEl.GetString() : null;
        // 项目级用户输入字段（可选）：{ client_name, project_name, test_date, ... }
        var userInputs = p.TryGetProperty("user_inputs", out var uiEl) && uiEl.ValueKind == JsonValueKind.Object
            ? ParseUserInputs(uiEl)
            : new Dictionary<string, string>();

        // params_by_batch: { "B1": {P,Lf,La,A,E}, "B2": {...}, ... }
        var paramsByBatch = ParseParamsByBatch(p.GetProperty("params_by_batch"));

        AnchorStandards.Validate(standard);

        var src = new FileInfo(inputXlsx);
        string outPath = outputXlsx
            ?? Path.Combine(src.DirectoryName ?? "",
                $"{Path.GetFileNameWithoutExtension(src.Name)}_{CalcTypeSuffix}_结果.xlsx");

        // 读输入
        var batchRows = AnchorExcelReader.ReadRows(inputXlsx, sheet, batchCol);

        // 缺参数批次 → 报错（前端应在 list_batches 后引导用户填齐）
        var missing = batchRows.Where(b => !paramsByBatch.ContainsKey(b.BatchId))
            .Select(b => b.BatchId).ToList();
        if (missing.Count > 0)
            throw new ArgumentException(
                $"以下批次缺工程参数：{string.Join(", ", missing)}");

        // 装配 workbook
        var batches = batchRows.Select(b => new AnchorBatchInput(
            b.BatchId, paramsByBatch[b.BatchId], b.Rows.ToArray())).ToArray();
        var workbook = new AnchorWorkbookInput(standard, batches);

        // 算
        var result = AnchorCalculator.Calc(workbook);

        // 写 Excel 输出：每批 1 sheet（数据分析）。报告内插表语义已迁到 Word，不再 Excel 出。
        XLWorkbook wb = File.Exists(outPath) ? new XLWorkbook(outPath) : new XLWorkbook();
        using (wb)
        {
            foreach (var br in result.BatchResults)
            {
                var analysisName = SafeSheetName($"{br.BatchId}-数据分析");
                if (wb.Worksheets.TryGetWorksheet(analysisName, out var old1)) old1.Delete();
                AnchorAnalysisSheet.Write(wb.Worksheets.Add(analysisName), br);
            }
            SaveWorkbook(wb, outPath);
        }

        // 可选 Word 报告：每批一份 docx，按 [[每根锚杆]] 锚点克隆 N 张表
        var wordOutputs = new List<string>();
        if (!string.IsNullOrWhiteSpace(wordTemplatePath))
        {
            var wordDir = !string.IsNullOrWhiteSpace(wordOutputDir)
                ? wordOutputDir
                : Path.Combine(src.DirectoryName ?? "", $"{Path.GetFileNameWithoutExtension(src.Name)}_Word报告");
            Directory.CreateDirectory(wordDir);
            foreach (var br in result.BatchResults)
            {
                var batchUserInputs = MergeBatchInputs(userInputs, br.BatchId);
                var projectResolver = new AnchorBatchResolver(br.Params, batchUserInputs);
                var rowResolvers = br.RowsWithResults
                    .Select(rw => (IFieldResolver)new AnchorRowResolver(rw.Input, rw.Result, br.Params, batchUserInputs))
                    .ToList();

                var wordOut = Path.Combine(wordDir, SafeFileName($"{br.BatchId}_锚杆抗拔报告.docx"));
                ReportGenerator.Generate(
                    wordTemplatePath, projectResolver, rowResolvers, wordOut,
                    catalog: AnchorFieldCatalog.All);
                wordOutputs.Add(wordOut);
            }
        }

        var res = new Dictionary<string, object?>
        {
            ["batches"] = result.NBatches,
            ["anchors_total"] = result.NRowsTotal,
            ["anchors_qualified"] = result.NQualifiedTotal,
            ["output"] = outPath,
        };
        if (wordOutputs.Count > 0) res["word_outputs"] = wordOutputs;
        return res;
    }

    private static Dictionary<string, string> ParseUserInputs(JsonElement el)
    {
        var d = new Dictionary<string, string>();
        foreach (var prop in el.EnumerateObject())
        {
            if (prop.Value.ValueKind == JsonValueKind.String)
                d[prop.Name] = prop.Value.GetString() ?? "";
        }
        return d;
    }

    /// <summary>把"批次维度的用户输入"扁平化（暂未提供；预留接口）。</summary>
    private static IReadOnlyDictionary<string, string> MergeBatchInputs(
        IReadOnlyDictionary<string, string> projectInputs, string batchId)
    {
        // 当前实现：项目级直接用。未来若想"按批次定制 client_name 等"可在此扩展。
        _ = batchId;
        return projectInputs;
    }

    private static string SafeFileName(string s)
    {
        foreach (var c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
        return s;
    }

    private static Dictionary<string, AnchorParams> ParseParamsByBatch(JsonElement el)
    {
        if (el.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("各批次工程参数格式错误");
        var result = new Dictionary<string, AnchorParams>();
        foreach (var prop in el.EnumerateObject())
        {
            var ap = prop.Value;
            if (ap.ValueKind != JsonValueKind.Object)
                throw new ArgumentException($"批次「{prop.Name}」的工程参数格式错误");
            double p = ap.GetProperty("P").GetDouble();
            double lf = ap.GetProperty("Lf").GetDouble();
            double la = ap.GetProperty("La").GetDouble();
            double a = ap.GetProperty("A").GetDouble();
            double e = ap.GetProperty("E").GetDouble();
            result[prop.Name] = AnchorParams.Create(p, lf, la, a, e);
        }
        return result;
    }

    private static string SafeSheetName(string name)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var c in name)
            sb.Append("/\\?*[]:".Contains(c) ? '_' : c);
        var safe = sb.ToString();
        return safe.Length > 31 ? safe.Substring(0, 31) : safe;
    }
}
