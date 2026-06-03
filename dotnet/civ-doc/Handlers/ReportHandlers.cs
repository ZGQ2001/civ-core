// report.* RPC —— 报告生成（占位符主路径）。
//
// 方法清单：
//   report.render_placeholder(docx_path, catalog_id|project_type, values, output_path)
//     -> {output_path, replaced, unknown_keys}
//   report.run_from_result(result_xlsx, word_template_path, ...) -> {output, ...}
//     直接读 anchor.run 已经算好的结果 xlsx 出 Word，不再重新计算。
//     锚杆表由程序按规范建「逐根 表2.4」插进模板的 {{表格:锚杆}} 占位符（不再用 marker/专用模板）。
//
// 解耦：字段目录从 CatalogStore（JSON）读取，不再硬编码 switch。
// handler 只做 wire 解析；建表走 AnchorWordTable、装配走 DocxReportAssembler。

using System.Text.Json;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Calc.Coating;
using CivCore.Doc.Catalog;
using CivCore.Doc.ReportTables;
using CivCore.Doc.Server;
using CivCore.Doc.Template;

namespace CivCore.Doc.Handlers;

public static class ReportHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("report.render_placeholder", RenderPlaceholder);
        d.Register("report.run_from_result", RunFromResult);
        d.Register("report.assemble", Assemble);
    }

    public static object RenderPlaceholder(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var docxPath = RequireString(p, "docx_path");
        var outputPath = RequireString(p, "output_path");

        // 兼容 catalog_id 和旧的 project_type 参数
        string catalogId;
        if (p.TryGetProperty("catalog_id", out var ciEl) && ciEl.ValueKind == JsonValueKind.String)
            catalogId = ciEl.GetString() ?? "";
        else if (p.TryGetProperty("project_type", out var ptEl) && ptEl.ValueKind == JsonValueKind.String)
            catalogId = ptEl.GetString() ?? "";
        else
            throw new ArgumentException("缺少参数：catalog_id 或 project_type");

        if (string.IsNullOrWhiteSpace(catalogId))
            throw new ArgumentException("catalog_id 不可为空");

        if (!p.TryGetProperty("values", out var valuesEl)
            || valuesEl.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("缺少 values 字段值字典");

        var values = ParseValues(valuesEl);
        var catalogDto = CatalogStore.Get(catalogId)
            ?? throw new ArgumentException($"字段目录不存在：{catalogId}");
        var catalog = CatalogStore.ToFieldDefs(catalogDto);
        var resolver = new DictionaryResolver(values);

        try
        {
            var res = PlaceholderRenderer.Render(docxPath, outputPath, resolver, catalog);
            return new Dictionary<string, object?>
            {
                ["output_path"] = outputPath,
                ["replaced"] = res.Replaced,
                ["unknown_keys"] = res.UnknownKeys.ToList(),
            };
        }
        catch (PlaceholderRenderException e) { throw new ArgumentException(e.Message); }
    }

    /// <summary>
    /// 从结果 xlsx 直接出 Word —— 不重新跑 AnchorCalculator，复用 AnchorHandlers 的
    /// Word 生成路径（含按批次分发 / 页眉填充 / 图片占位符）。
    /// 参数与 anchor.run 的 Word 输出部分对齐（少了 params_by_batch，因为从 metadata 读）。
    /// </summary>
    public static object RunFromResult(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var resultXlsx = RequireString(p, "result_xlsx");
        var wordTemplatePath = RequireString(p, "word_template_path");
        string standard = p.TryGetProperty("standard", out var sEl)
            && sEl.ValueKind == JsonValueKind.String
            ? sEl.GetString() ?? AnchorStandards.GB_50086_2015
            : AnchorStandards.GB_50086_2015;
        string? wordOutputDir = p.TryGetProperty("word_output_dir", out var woEl)
            && woEl.ValueKind == JsonValueKind.String ? woEl.GetString() : null;
        string? curveImageDir = p.TryGetProperty("curve_image_dir", out var ciEl)
            && ciEl.ValueKind == JsonValueKind.String ? ciEl.GetString() : null;
        string? reportName = p.TryGetProperty("report_name", out var rnEl)
            && rnEl.ValueKind == JsonValueKind.String ? rnEl.GetString() : null;
        string sectionNo = p.TryGetProperty("section_no", out var snEl)
            && snEl.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(snEl.GetString())
            ? snEl.GetString()!
            : AnchorWordTable.DefaultSectionNo;

        var userInputs = p.TryGetProperty("user_inputs", out var uiEl)
            && uiEl.ValueKind == JsonValueKind.Object
            ? ParseStringMap(uiEl)
            : new Dictionary<string, string>();
        var batchUserInputs = p.TryGetProperty("batch_user_inputs", out var buiEl)
            && buiEl.ValueKind == JsonValueKind.Object
            ? ParseStringMapNested(buiEl)
            : new Dictionary<string, Dictionary<string, string>>();

        if (!File.Exists(resultXlsx))
            throw new ArgumentException($"结果 xlsx 文件不存在：{resultXlsx}");
        if (!File.Exists(wordTemplatePath))
            throw new ArgumentException($"Word 模板不存在：{wordTemplatePath}");

        // 反序列化结果 xlsx → AnchorWorkbookResult（不再算）+ 持久化的灌浆日期
        var result = AnchorResultReader.Read(resultXlsx, standard, out var persistedGroutingDates);
        if (result.NRowsTotal == 0)
            throw new ArgumentException(
                $"结果 xlsx 没有任何数据行：{resultXlsx} —— 文件可能已损坏或是空模板");

        // 灌浆日期回退：结果 xlsx 的 metadata sheet 已持久化各批灌浆日期。把它并入
        // batchUserInputs，让 result 路径自带日期、不再依赖 GUI/预设。优先级跟
        // anchor.run 的「批次信息」sheet 回退一致：GUI/预设传入 > 结果 xlsx（TryAdd 不覆盖）。
        foreach (var (batchId, date) in persistedGroutingDates)
        {
            if (string.IsNullOrWhiteSpace(date)) continue;
            if (!batchUserInputs.TryGetValue(batchId, out var bui))
            {
                bui = new Dictionary<string, string>();
                batchUserInputs[batchId] = bui;
            }
            bui.TryAdd("grouting_date", date);
        }

        // Word 输出目录：默认在结果 xlsx 同级
        var src = new FileInfo(resultXlsx);
        var wordDir = !string.IsNullOrWhiteSpace(wordOutputDir)
            ? wordOutputDir
            : Path.Combine(src.DirectoryName ?? "",
                $"{Path.GetFileNameWithoutExtension(src.Name)}_Word报告");
        Directory.CreateDirectory(wordDir);

        var wordFileName = !string.IsNullOrWhiteSpace(reportName)
            ? (reportName!.EndsWith(".docx", StringComparison.OrdinalIgnoreCase)
                ? reportName!
                : $"{reportName}.docx")
            : "锚杆抗拔报告.docx";
        var wordOut = Path.Combine(wordDir, SafeFileName(wordFileName));

        // 程序按规范建「逐根 表2.4」插进模板的 {{表格:锚杆}} 占位符 + 填薄壳（不再 marker/专用模板）。
        var genResult = AnchorWordTable.GenerateReport(
            wordTemplatePath, wordOut, result, userInputs, batchUserInputs, curveImageDir, sectionNo);

        return new Dictionary<string, object?>
        {
            ["batches"] = result.NBatches,
            ["anchors_total"] = result.NRowsTotal,
            ["anchors_qualified"] = result.NQualifiedTotal,
            ["output"] = resultXlsx, // 与 anchor.run 的 output 字段语义对齐：当前数据所在 xlsx
            ["word_outputs"] = new List<string> { wordOut },
            ["word_unknown_keys"] = genResult.UnknownKeys.ToList(),
            ["word_missing_images"] = genResult.MissingImages.ToList(),
        };
    }

    /// <summary>
    /// 多检测类型组装：一份薄壳模板里写多个 {{表格:xxx}}，按 sections 提供的数据各建表插入，
    /// 没提供数据的占位符清掉，其余 {{}} 按 user_inputs 填。锚杆段读结果 xlsx、防火涂层段读测点 xlsx。
    /// </summary>
    public static object Assemble(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var wordTemplate = RequireString(p, "word_template_path");
        var outputDocx = RequireString(p, "output_docx");
        if (!File.Exists(wordTemplate))
            throw new ArgumentException($"Word 模板不存在：{wordTemplate}");

        var userInputs = p.TryGetProperty("user_inputs", out var uiEl) && uiEl.ValueKind == JsonValueKind.Object
            ? ParseStringMap(uiEl)
            : new Dictionary<string, string>();

        if (!p.TryGetProperty("sections", out var secEl) || secEl.ValueKind != JsonValueKind.Array)
            throw new ArgumentException("缺少 sections 数组（每项 {type:'anchor'|'coating', ...数据源参数}）");

        var sections = new List<ReportSection>();
        var sectionTypes = new List<string>();
        foreach (var sec in secEl.EnumerateArray())
        {
            if (sec.ValueKind != JsonValueKind.Object)
                throw new ArgumentException("sections 每项必须是对象");
            var type = OptString(sec, "type")
                ?? throw new ArgumentException("section 缺少 type（anchor / coating）");
            sections.Add(type switch
            {
                "anchor" => BuildAnchorSection(sec, userInputs),
                "coating" => BuildCoatingSection(sec),
                _ => throw new ArgumentException($"未知 section type：{type}（支持 anchor / coating）"),
            });
            sectionTypes.Add(type);
        }

        var r = DocxReportAssembler.Generate(
            wordTemplate, outputDocx, sections, userInputs, catalog: AnchorFieldCatalog.All);

        return new Dictionary<string, object?>
        {
            ["output"] = outputDocx,
            ["tables"] = r.TablesInserted,
            ["replaced"] = r.Replaced,
            ["unknown_keys"] = r.UnknownKeys.ToList(),
            ["missing_images"] = r.MissingImages.ToList(),
            ["sections"] = sectionTypes,
        };
    }

    /// <summary>锚杆 section：读结果 xlsx（含持久化灌浆日期回退）→ 逐根 表2.4 建表委托。</summary>
    private static ReportSection BuildAnchorSection(
        JsonElement sec, IReadOnlyDictionary<string, string> userInputs)
    {
        var resultXlsx = RequireString(sec, "result_xlsx");
        if (!File.Exists(resultXlsx))
            throw new ArgumentException($"锚杆结果 xlsx 不存在：{resultXlsx}");
        string standard = OptString(sec, "standard") ?? AnchorStandards.GB_50086_2015;
        string? curveImageDir = OptString(sec, "curve_image_dir");
        string sectionNo = OptNonBlank(sec, "section_no") ?? AnchorWordTable.DefaultSectionNo;
        var batchUserInputs = sec.TryGetProperty("batch_user_inputs", out var b) && b.ValueKind == JsonValueKind.Object
            ? ParseStringMapNested(b)
            : new Dictionary<string, Dictionary<string, string>>();

        var result = AnchorResultReader.Read(resultXlsx, standard, out var persisted);
        foreach (var (batchId, date) in persisted)
        {
            if (string.IsNullOrWhiteSpace(date)) continue;
            if (!batchUserInputs.TryGetValue(batchId, out var bui))
            {
                bui = new Dictionary<string, string>();
                batchUserInputs[batchId] = bui;
            }
            bui.TryAdd("grouting_date", date);
        }

        var detectionLabel = OptNonBlank(sec, "detection_label") ?? AnchorWordTable.DetectionLabel(userInputs);
        return new ReportSection(
            AnchorWordTable.TablePlaceholder,
            mp => AnchorWordTable.BuildSection(
                result, userInputs, batchUserInputs, curveImageDir, sectionNo, detectionLabel, mp));
    }

    /// <summary>防火涂层 section：读结果 xlsx（coating.run 产出）→ 按规范格式建表委托（不重算，对齐锚杆 section）。</summary>
    private static ReportSection BuildCoatingSection(JsonElement sec)
    {
        var resultXlsx = RequireString(sec, "result_xlsx");
        if (!File.Exists(resultXlsx))
            throw new ArgumentException($"防火涂层结果 xlsx 不存在：{resultXlsx}");
        string standard = OptString(sec, "standard") ?? CoatingStandards.GB_50205_2020;

        FileGuard.CheckExcelSize(resultXlsx);
        CoatingStandards.Validate(standard);

        var result = CoatingResultReader.Read(resultXlsx, standard);
        var members = result.BatchResults.SelectMany(br => br.MembersWithResults).ToList();

        return new ReportSection(
            CoatingDocxReport.TablePlaceholder,
            _ => SectionBuild.Plain(CoatingWordTable.BuildAll(members, standard)));
    }

    // ── 内部 ──

    private static Dictionary<string, string> ParseStringMap(JsonElement el)
    {
        var d = new Dictionary<string, string>();
        foreach (var prop in el.EnumerateObject())
        {
            if (prop.Value.ValueKind == JsonValueKind.String)
                d[prop.Name] = prop.Value.GetString() ?? "";
        }
        return d;
    }

    private static Dictionary<string, Dictionary<string, string>> ParseStringMapNested(JsonElement el)
    {
        var d = new Dictionary<string, Dictionary<string, string>>();
        foreach (var batchProp in el.EnumerateObject())
        {
            if (batchProp.Value.ValueKind != JsonValueKind.Object) continue;
            d[batchProp.Name] = ParseStringMap(batchProp.Value);
        }
        return d;
    }

    private static string SafeFileName(string s)
    {
        foreach (var c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
        return s;
    }

    private static string? OptString(JsonElement p, string name)
        => p.TryGetProperty(name, out var el) && el.ValueKind == JsonValueKind.String ? el.GetString() : null;

    private static string? OptNonBlank(JsonElement p, string name)
    {
        var s = OptString(p, name);
        return string.IsNullOrWhiteSpace(s) ? null : s;
    }

    // ── 旧：ParseValues / DictionaryResolver（render_placeholder 专用，object? 值类型）──

    private static Dictionary<string, object?> ParseValues(JsonElement obj)
    {
        var d = new Dictionary<string, object?>();
        foreach (var prop in obj.EnumerateObject())
        {
            d[prop.Name] = prop.Value.ValueKind switch
            {
                JsonValueKind.String => prop.Value.GetString(),
                JsonValueKind.Number => prop.Value.TryGetInt64(out var i) ? i : prop.Value.GetDouble(),
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                JsonValueKind.Null => null,
                _ => prop.Value.GetRawText(),
            };
        }
        return d;
    }

    private class DictionaryResolver : IFieldResolver
    {
        private readonly IReadOnlyDictionary<string, object?> _values;
        public DictionaryResolver(IReadOnlyDictionary<string, object?> values) => _values = values;
        public object? GetValue(string fieldKey)
            => _values.TryGetValue(fieldKey, out var v) ? v : null;
    }

    private static string RequireString(JsonElement p, string key)
    {
        if (!p.TryGetProperty(key, out var el) || el.ValueKind != JsonValueKind.String)
            throw new ArgumentException($"缺少或非法参数：{key}");
        var v = el.GetString();
        if (string.IsNullOrWhiteSpace(v))
            throw new ArgumentException($"参数 {key} 不可为空");
        return v;
    }
}
