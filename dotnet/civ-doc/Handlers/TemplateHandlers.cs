// template.* RPC —— 字段清单查询 + 模板验证。
//
// 方法清单：
//   template.fields(project_type)
//     -> {fields: [{key, name, source, value_type, default_format}]}
//   template.validate(docx_path, catalog_id)
//     -> {matched, unrecognized, unused, summary}
//
// 报告生成走 report.* RPC（见 ReportHandlers）。

using System.Text.Json;
using System.Text.RegularExpressions;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Catalog;
using CivCore.Doc.Server;
using CivCore.Doc.Template;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Handlers;

public static class TemplateHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("template.fields", Fields);
        d.Register("template.validate", Validate);
    }

    // ── template.fields ───────────────────────────────────────

    public static object Fields(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;
        if (!p.TryGetProperty("project_type", out var ptEl) || ptEl.ValueKind != JsonValueKind.String)
            throw new ArgumentException("缺少或非法参数：project_type");
        var projectType = ptEl.GetString();
        if (string.IsNullOrWhiteSpace(projectType))
            throw new ArgumentException("project_type 不可为空");

        return new Dictionary<string, object?>
        {
            ["fields"] = GetCatalog(projectType).Select(ProjectField).ToList(),
        };
    }

    private static Dictionary<string, object?> ProjectField(FieldDef f) => new()
    {
        ["key"] = f.Key,
        ["name"] = f.Name,
        ["source"] = f.Source.ToString().ToLowerInvariant(),
        ["value_type"] = f.ValueType,
        ["default_format"] = f.DefaultFormat,
    };

    private static IEnumerable<FieldDef> GetCatalog(string projectType) => projectType switch
    {
        "anchor" => AnchorFieldCatalog.All,
        _ => throw new ArgumentException($"未知 project_type：{projectType}（当前支持：anchor）"),
    };

    // ── template.validate ─────────────────────────────────────

    private static readonly Regex PlaceholderRx =
        new(@"\{\{([^{}\r\n]+?)\}\}", RegexOptions.Compiled);

    private static readonly Regex MarkerRx =
        new(@"\[\[(.+?)\]\]", RegexOptions.Compiled);

    public static object Validate(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        var docxPath = RequireString(p, "docx_path");
        var catalogId = RequireString(p, "catalog_id");

        if (!File.Exists(docxPath))
            throw new ArgumentException($"模板文件不存在：{docxPath}");

        var catalog = CatalogStore.Get(catalogId)
            ?? throw new ArgumentException($"字段目录不存在：{catalogId}");

        var (keyByName, keyByAlias) = BuildLookup(catalog);
        var found = ScanDocx(docxPath);

        var matched = new List<Dictionary<string, object?>>();
        var unrecognized = new List<Dictionary<string, object?>>();
        var matchedKeys = new HashSet<string>();

        foreach (var (raw, location) in found)
        {
            var trimmed = raw.Trim();
            var isImage = trimmed.StartsWith("img:", StringComparison.OrdinalIgnoreCase);
            var lookup = isImage ? trimmed.Substring(4).Trim() : trimmed;

            string? resolvedKey = null;
            string? resolvedName = null;

            if (IsKeyLike(lookup))
            {
                var field = catalog.Fields.FirstOrDefault(f => f.Key == lookup);
                if (field != null)
                {
                    resolvedKey = field.Key;
                    resolvedName = field.Name;
                }
            }
            if (resolvedKey == null && keyByName.TryGetValue(lookup, out var byName))
            {
                resolvedKey = byName.Key;
                resolvedName = byName.Name;
            }
            if (resolvedKey == null && keyByAlias.TryGetValue(lookup, out var byAlias))
            {
                resolvedKey = byAlias.Key;
                resolvedName = byAlias.Name;
            }

            if (resolvedKey != null)
            {
                matchedKeys.Add(resolvedKey);
                matched.Add(new Dictionary<string, object?>
                {
                    ["placeholder"] = $"{{{{{raw}}}}}",
                    ["key"] = resolvedKey,
                    ["name"] = resolvedName,
                    ["location"] = location,
                    ["is_image"] = isImage,
                });
            }
            else
            {
                unrecognized.Add(new Dictionary<string, object?>
                {
                    ["placeholder"] = $"{{{{{raw}}}}}",
                    ["location"] = location,
                });
            }
        }

        var unused = catalog.Fields
            .Where(f => !matchedKeys.Contains(f.Key))
            .Select(f => new Dictionary<string, object?>
            {
                ["key"] = f.Key,
                ["name"] = f.Name,
                ["group"] = f.Group,
            })
            .ToList();

        return new Dictionary<string, object?>
        {
            ["matched"] = matched,
            ["unrecognized"] = unrecognized,
            ["unused"] = unused,
            ["summary"] = new Dictionary<string, object?>
            {
                ["matched_count"] = matched.Count,
                ["unrecognized_count"] = unrecognized.Count,
                ["unused_count"] = unused.Count,
                ["total_catalog_fields"] = catalog.Fields.Count,
            },
        };
    }

    private static List<(string Raw, string Location)> ScanDocx(string docxPath)
    {
        var results = new List<(string, string)>();
        using var doc = WordprocessingDocument.Open(docxPath, false);
        var mainPart = doc.MainDocumentPart;
        if (mainPart == null) return results;

        if (mainPart.Document?.Body != null)
            ScanElement(mainPart.Document.Body, "正文", results);

        foreach (var hp in mainPart.HeaderParts)
            if (hp.Header != null)
                ScanElement(hp.Header, "页眉", results);

        foreach (var fp in mainPart.FooterParts)
            if (fp.Footer != null)
                ScanElement(fp.Footer, "页脚", results);

        return results;
    }

    private static void ScanElement(OpenXmlElement scope, string baseLocation,
        List<(string Raw, string Location)> results)
    {
        int tableIndex = 0;
        foreach (var child in scope.ChildElements)
        {
            if (child is Table table)
            {
                tableIndex++;
                ScanTable(table, baseLocation, tableIndex, results);
            }
            else if (child is Paragraph para)
            {
                ScanParagraph(para, baseLocation, results);
            }
        }
    }

    private static void ScanTable(Table table, string baseLocation, int tableIndex,
        List<(string Raw, string Location)> results)
    {
        int rowIndex = 0;
        foreach (var row in table.Elements<TableRow>())
        {
            rowIndex++;
            int cellIndex = 0;
            foreach (var cell in row.Elements<TableCell>())
            {
                cellIndex++;
                var loc = $"{baseLocation} > 表格{tableIndex} > 第{rowIndex}行第{cellIndex}列";
                foreach (var para in cell.Elements<Paragraph>())
                    ScanParagraph(para, loc, results);
            }
        }
    }

    private static void ScanParagraph(Paragraph para, string location,
        List<(string Raw, string Location)> results)
    {
        var text = string.Concat(para.Elements<Run>()
            .SelectMany(r => r.Elements<Text>())
            .Select(t => t.Text));
        if (string.IsNullOrEmpty(text)) return;

        foreach (Match m in PlaceholderRx.Matches(text))
            results.Add((m.Groups[1].Value, location));

        foreach (Match m in MarkerRx.Matches(text))
            results.Add(($"marker:{m.Groups[1].Value}", location));
    }

    private static (Dictionary<string, CatalogFieldDto> ByName,
        Dictionary<string, CatalogFieldDto> ByAlias) BuildLookup(FieldCatalogDto catalog)
    {
        var byName = new Dictionary<string, CatalogFieldDto>(StringComparer.Ordinal);
        var byAlias = new Dictionary<string, CatalogFieldDto>(StringComparer.Ordinal);
        foreach (var f in catalog.Fields)
        {
            byName[f.Name] = f;
            foreach (var alias in f.Aliases)
                byAlias[alias] = f;
        }
        return (byName, byAlias);
    }

    private static bool IsKeyLike(string s)
    {
        foreach (var c in s)
        {
            bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                || (c >= '0' && c <= '9') || c == '_';
            if (!ok) return false;
        }
        return s.Length > 0;
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
