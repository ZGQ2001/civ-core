// report.* RPC —— 报告生成（占位符主路径）。
//
// 方法清单：
//   report.render_placeholder(docx_path, catalog_id|project_type, values, output_path)
//     -> {output_path, replaced, unknown_keys}
//
// 解耦：字段目录从 CatalogStore（JSON）读取，不再硬编码 switch。
// handler 只做 wire 解析 + IFieldResolver 适配；具体替换在 PlaceholderRenderer。

using System.Text.Json;
using CivCore.Doc.Catalog;
using CivCore.Doc.Server;
using CivCore.Doc.Template;

namespace CivCore.Doc.Handlers;

public static class ReportHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("report.render_placeholder", RenderPlaceholder);
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

    // ── 内部 ──

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
