// report.* RPC —— 报告生成（占位符主路径）。
//
// 方法清单：
//   report.render_placeholder(docx_path, project_type, values, output_path)
//     -> {output_path, replaced, unknown_keys}
//
// 解耦：handler 只做 wire 解析 + IFieldResolver 适配；具体替换在 PlaceholderRenderer。
// project_type → 字段 catalog 派发（跟 TemplateHandlers.Fields 同套）；未来加钻芯/回弹只
// 在 GetCatalog 加一行。

using System.Text.Json;
using CivCore.Doc.Calc.Anchor;
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
        var projectType = RequireString(p, "project_type");
        var outputPath = RequireString(p, "output_path");

        if (!p.TryGetProperty("values", out var valuesEl)
            || valuesEl.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("缺少 values 字段值字典");

        var values = ParseValues(valuesEl);
        var catalog = GetCatalog(projectType);
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

    // ── 内部：JSON values → Dict<string,object?> ──────────

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

    /// <summary>通用 IFieldResolver：字典查表。给 RPC 调用方传字段值用，不耦合具体 calc 类型。</summary>
    private class DictionaryResolver : IFieldResolver
    {
        private readonly IReadOnlyDictionary<string, object?> _values;
        public DictionaryResolver(IReadOnlyDictionary<string, object?> values) => _values = values;
        public object? GetValue(string fieldKey)
            => _values.TryGetValue(fieldKey, out var v) ? v : null;
    }

    private static IReadOnlyList<FieldDef> GetCatalog(string projectType) => projectType switch
    {
        "anchor" => AnchorFieldCatalog.All,
        _ => throw new ArgumentException($"未知 project_type：{projectType}（当前支持：anchor）"),
    };

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
