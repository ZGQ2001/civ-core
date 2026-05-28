// report.* RPC —— 报告生成（占位符主路径）。
//
// 方法清单：
//   report.render_placeholder(docx_path, catalog_id|project_type, values, output_path)
//     -> {output_path, replaced, unknown_keys}
//   report.run_from_result(result_xlsx, word_template_path, ...) -> {output, ...}
//     直接读 anchor.run 已经算好的结果 xlsx 出 Word，不再重新计算。
//     解决用户反馈 #2+#7「报告填充不应再重算 / 应该消费结果文件」。
//
// 解耦：字段目录从 CatalogStore（JSON）读取，不再硬编码 switch。
// handler 只做 wire 解析 + IFieldResolver 适配；具体替换在 PlaceholderRenderer。

using System.Text.Json;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Catalog;
using CivCore.Doc.Server;
using CivCore.Doc.Template;
using DocumentFormat.OpenXml.Packaging;

namespace CivCore.Doc.Handlers;

public static class ReportHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("report.render_placeholder", RenderPlaceholder);
        d.Register("report.run_from_result", RunFromResult);
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

        // 反序列化结果 xlsx → AnchorWorkbookResult（不再算）
        var result = AnchorResultReader.Read(resultXlsx, standard);
        if (result.NRowsTotal == 0)
            throw new ArgumentException(
                $"结果 xlsx 没有任何数据行：{resultXlsx} —— 文件可能已损坏或是空模板");

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

        // 模板探测：三层 [[检测项目]] / 两层 [[批次]] / 单层
        var useMultiDetectionItem = TemplateHasMarker(wordTemplatePath, "[[检测项目]]");
        var useMultiBatch = TemplateHasMarker(wordTemplatePath, "[[批次]]");
        ReportGenerateResult genResult;
        if (useMultiDetectionItem)
        {
            // 三层：把所有批次包成一个 detection item（当前只 anchor 一种 calc）
            var itemLevel = new Dictionary<string, string>(userInputs);
            itemLevel["detection_type"] = "锚杆抗拔";
            itemLevel.TryAdd("inspection_item", "锚杆抗拔力（验收）检测");

            var sections = new List<BatchSection>();
            int anchorIndex = 0;
            foreach (var br in result.BatchResults)
            {
                var batchLevel = new Dictionary<string, string>(itemLevel);
                if (batchUserInputs.TryGetValue(br.BatchId, out var bui))
                {
                    foreach (var kv in bui) batchLevel[kv.Key] = kv.Value;
                }
                batchLevel["batch_id"] = br.BatchId;

                var batchRowResolvers = new List<IFieldResolver>();
                foreach (var rw in br.RowsWithResults)
                {
                    anchorIndex++;
                    batchRowResolvers.Add(new AnchorRowResolver(
                        rw.Input, rw.Result, br.Params, batchLevel,
                        anchorIndex: anchorIndex,
                        curveImageDir: curveImageDir));
                }
                sections.Add(new BatchSection(
                    new DictionaryResolverStr(batchLevel),
                    batchRowResolvers));
            }
            var items = new List<DetectionItemSection>
            {
                new(new DictionaryResolverStr(itemLevel), sections),
            };
            var globalResolver = new DictionaryResolverStr(userInputs);
            genResult = ReportGenerator.GenerateMultiDetectionItem(
                wordTemplatePath, globalResolver, items, wordOut,
                catalog: AnchorFieldCatalog.All);
        }
        else if (useMultiBatch)
        {
            var sections = new List<BatchSection>();
            int anchorIndex = 0;
            foreach (var br in result.BatchResults)
            {
                var batchLevel = new Dictionary<string, string>(userInputs);
                if (batchUserInputs.TryGetValue(br.BatchId, out var bui))
                {
                    foreach (var kv in bui) batchLevel[kv.Key] = kv.Value;
                }
                batchLevel["batch_id"] = br.BatchId;

                var batchRowResolvers = new List<IFieldResolver>();
                foreach (var rw in br.RowsWithResults)
                {
                    anchorIndex++;
                    batchRowResolvers.Add(new AnchorRowResolver(
                        rw.Input, rw.Result, br.Params, batchLevel,
                        anchorIndex: anchorIndex,
                        curveImageDir: curveImageDir));
                }
                sections.Add(new BatchSection(
                    new DictionaryResolverStr(batchLevel),
                    batchRowResolvers));
            }
            var globalResolver = new DictionaryResolverStr(userInputs);
            genResult = ReportGenerator.GenerateMultiBatch(
                wordTemplatePath, globalResolver, sections, wordOut,
                catalog: AnchorFieldCatalog.All);
        }
        else
        {
            // 单批兼容：把 batch_user_inputs 里第一个有值的 grouting_date 灌入项目级
            var mergedInputs = new Dictionary<string, string>(userInputs);
            foreach (var bui in batchUserInputs.Values)
            {
                if (bui.TryGetValue("grouting_date", out var v)
                    && !string.IsNullOrWhiteSpace(v)
                    && !mergedInputs.ContainsKey("grouting_date"))
                {
                    mergedInputs["grouting_date"] = v;
                    break;
                }
            }
            var projectResolver = new DictionaryResolverStr(mergedInputs);
            var rowResolvers = new List<IFieldResolver>();
            int anchorIndex = 0;
            foreach (var br in result.BatchResults)
            {
                foreach (var rw in br.RowsWithResults)
                {
                    anchorIndex++;
                    rowResolvers.Add(new AnchorRowResolver(
                        rw.Input, rw.Result, br.Params, mergedInputs,
                        anchorIndex: anchorIndex,
                        curveImageDir: curveImageDir));
                }
            }
            genResult = ReportGenerator.Generate(
                wordTemplatePath, projectResolver, rowResolvers, wordOut,
                catalog: AnchorFieldCatalog.All);
        }

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

    // ── 内部 ──

    /// <summary>
    /// 检测模板里有没有指定 marker 字符串 —— 跟 AnchorHandlers 同口径。
    /// 解析失败时 fallback 到 false。
    /// </summary>
    private static bool TemplateHasMarker(string templatePath, string marker)
    {
        try
        {
            using var doc = WordprocessingDocument.Open(templatePath, false);
            var body = doc.MainDocumentPart?.Document?.Body;
            return body?.InnerText.Contains(marker) ?? false;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(
                $"[report.run_from_result] 探测 marker {marker} 失败：{ex.Message}");
            return false;
        }
    }

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

    /// <summary>字符串字典适配为 IFieldResolver。跟 AnchorHandlers.DictionaryResolver 同语义但接 string。</summary>
    private class DictionaryResolverStr : IFieldResolver
    {
        private readonly IReadOnlyDictionary<string, string> _v;
        public DictionaryResolverStr(IReadOnlyDictionary<string, string> v) => _v = v;
        public object? GetValue(string key) => _v.TryGetValue(key, out var s) ? s : null;
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
