// template.* RPC —— 字段清单查询 + 模板验证。
//
// 方法清单：
//   template.fields(catalog_id)
//     -> {fields: [{key, name, group, level, source, value_type, default_format, aliases}]}
//   template.validate(docx_path, catalog_id)
//     -> {matched, unrecognized, unused, markers, hints, summary}
//
// 解耦：字段定义统一从 CatalogStore（JSON）读取，不再硬编码 switch。
// 报告生成走 report.* RPC（见 ReportHandlers）。

using System.Text.Json;
using System.Text.RegularExpressions;
using CivCore.Doc.Catalog;
using CivCore.Doc.Server;
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

        string catalogId;
        if (p.TryGetProperty("catalog_id", out var ciEl) && ciEl.ValueKind == JsonValueKind.String)
            catalogId = ciEl.GetString() ?? "";
        else if (p.TryGetProperty("project_type", out var ptEl) && ptEl.ValueKind == JsonValueKind.String)
            catalogId = ptEl.GetString() ?? "";
        else
            throw new ArgumentException("缺少参数：catalog_id 或 project_type");

        if (string.IsNullOrWhiteSpace(catalogId))
            throw new ArgumentException("catalog_id 不可为空");

        var catalog = CatalogStore.Get(catalogId)
            ?? throw new ArgumentException(BuildCatalogNotFoundMessage(catalogId));

        return new Dictionary<string, object?>
        {
            ["fields"] = catalog.Fields.Select(f => new Dictionary<string, object?>
            {
                ["key"] = f.Key,
                ["name"] = f.Name,
                ["group"] = f.Group,
                ["level"] = f.Level,
                ["source"] = f.Source,
                ["value_type"] = f.ValueType,
                ["default_format"] = f.DefaultFormat,
                ["aliases"] = f.Aliases,
            }).ToList(),
        };
    }

    // ── template.validate ─────────────────────────────────────

    private static readonly Regex PlaceholderRx =
        new(@"\{\{([^{}\r\n]+?)\}\}", RegexOptions.Compiled);

    private static readonly Regex MarkerOpenRx =
        new(@"^\[\[([^\[\]/]+)\]\]$", RegexOptions.Compiled);

    private static readonly Regex MarkerCloseRx =
        new(@"^\[\[/([^\[\]]+)\]\]$", RegexOptions.Compiled);

    private static readonly Dictionary<string, string> MarkerToLevel = new(StringComparer.Ordinal)
    {
        ["检测项目"] = "detection_item",
        ["检测批"] = "batch",
        ["构件"] = "component",
        ["每根锚杆"] = "component",
        ["批次"] = "batch",
    };

    private static readonly Dictionary<string, string> LevelLabel = new()
    {
        ["report"] = "报告级",
        ["detection_item"] = "检测项目级",
        ["batch"] = "检测批级",
        ["component"] = "构件级",
    };

    private static readonly string[] LevelOrder = ["report", "detection_item", "batch", "component"];

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
            ?? throw new ArgumentException(BuildCatalogNotFoundMessage(catalogId));

        var (keyByName, keyByAlias) = BuildLookup(catalog);
        var scanResult = ScanDocx(docxPath);

        var matched = new List<Dictionary<string, object?>>();
        var unrecognized = new List<Dictionary<string, object?>>();
        var hints = new List<Dictionary<string, object?>>();
        var matchedKeys = new HashSet<string>();

        foreach (var item in scanResult.Placeholders)
        {
            var trimmed = item.Raw.Trim();
            var isImage = trimmed.StartsWith("img:", StringComparison.OrdinalIgnoreCase);
            var lookup = isImage ? trimmed.Substring(4).Trim() : trimmed;

            CatalogFieldDto? resolved = null;

            if (IsKeyLike(lookup))
                resolved = catalog.Fields.FirstOrDefault(f => f.Key == lookup);
            if (resolved == null)
                keyByName.TryGetValue(lookup, out resolved);
            if (resolved == null)
                keyByAlias.TryGetValue(lookup, out resolved);

            if (resolved != null)
            {
                matchedKeys.Add(resolved.Key);
                matched.Add(new Dictionary<string, object?>
                {
                    ["placeholder"] = $"{{{{{item.Raw}}}}}",
                    ["key"] = resolved.Key,
                    ["name"] = resolved.Name,
                    ["level"] = resolved.Level,
                    ["location"] = item.Location,
                    ["scope"] = item.Scope,
                    ["is_image"] = isImage,
                });

                var expectedLevel = resolved.Level;
                var actualScope = item.Scope;
                var hint = CheckLevelMatch(expectedLevel, actualScope, resolved.Name, item.Location);
                if (hint != null) hints.Add(hint);
            }
            else
            {
                unrecognized.Add(new Dictionary<string, object?>
                {
                    ["placeholder"] = $"{{{{{item.Raw}}}}}",
                    ["location"] = item.Location,
                    ["scope"] = item.Scope,
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
                ["level"] = f.Level,
            })
            .ToList();

        return new Dictionary<string, object?>
        {
            ["matched"] = matched,
            ["unrecognized"] = unrecognized,
            ["unused"] = unused,
            ["markers"] = scanResult.Markers.Select(m => new Dictionary<string, object?>
            {
                ["text"] = m.Text,
                ["type"] = m.IsOpen ? "open" : "close",
                ["level"] = m.Level,
                ["location"] = m.Location,
            }).ToList(),
            ["hints"] = hints,
            ["summary"] = new Dictionary<string, object?>
            {
                ["matched_count"] = matched.Count,
                ["unrecognized_count"] = unrecognized.Count,
                ["unused_count"] = unused.Count,
                ["hint_count"] = hints.Count,
                ["total_catalog_fields"] = catalog.Fields.Count,
            },
        };
    }

    private static Dictionary<string, object?>? CheckLevelMatch(
        string expectedLevel, string actualScope, string fieldName, string location)
    {
        var expectedIdx = Array.IndexOf(LevelOrder, expectedLevel);
        var actualIdx = Array.IndexOf(LevelOrder, actualScope);
        if (expectedIdx < 0 || actualIdx < 0) return null;
        if (expectedIdx == actualIdx) return null;

        // 外层字段写在内层 scope 是合法用法（比如批次级灌浆日期写在 [[每根锚杆]] 里，
        // 每根锚杆那行就重复出现该日期——预期行为，不报警）。
        // 只有相反方向是真错（内层字段写在外层，根本拿不到值）。
        if (expectedIdx < actualIdx) return null;

        var expectedLabel = LevelLabel.GetValueOrDefault(expectedLevel, expectedLevel);
        var actualLabel = LevelLabel.GetValueOrDefault(actualScope, actualScope);
        var message = $"「{fieldName}」是{expectedLabel}字段，但当前在{actualLabel}区域"
            + $"——重复区域内无法取到该值。建议移出到{expectedLabel}区域。";

        return new Dictionary<string, object?>
        {
            ["severity"] = "error",
            ["field_name"] = fieldName,
            ["expected_level"] = expectedLevel,
            ["actual_scope"] = actualScope,
            ["location"] = location,
            ["message"] = message,
        };
    }

    private static string MarkerLabelFor(string level) => level switch
    {
        "detection_item" => "检测项目",
        "batch" => "检测批",
        "component" => "构件",
        _ => level,
    };

    // ── 文档扫描（嵌套感知） ──

    private record FoundPlaceholder(string Raw, string Location, string Scope);
    private record FoundMarker(string Text, bool IsOpen, string Level, string Location);
    private record ScanOutput(List<FoundPlaceholder> Placeholders, List<FoundMarker> Markers);

    private static ScanOutput ScanDocx(string docxPath)
    {
        var placeholders = new List<FoundPlaceholder>();
        var markers = new List<FoundMarker>();

        using var doc = WordprocessingDocument.Open(docxPath, false);
        var mainPart = doc.MainDocumentPart;
        if (mainPart == null) return new ScanOutput(placeholders, markers);

        if (mainPart.Document?.Body != null)
        {
            var scope = new Stack<string>();
            ScanBody(mainPart.Document.Body, "正文", scope, placeholders, markers);
        }

        foreach (var hp in mainPart.HeaderParts)
            if (hp.Header != null)
                ScanStatic(hp.Header, "页眉", "report", placeholders);

        foreach (var fp in mainPart.FooterParts)
            if (fp.Footer != null)
                ScanStatic(fp.Footer, "页脚", "report", placeholders);

        return new ScanOutput(placeholders, markers);
    }

    private static void ScanBody(OpenXmlElement scope, string baseLocation,
        Stack<string> scopeStack, List<FoundPlaceholder> placeholders, List<FoundMarker> markers)
    {
        int tableIndex = 0;
        foreach (var child in scope.ChildElements)
        {
            if (child is Table table)
            {
                tableIndex++;
                ScanTable(table, baseLocation, tableIndex, scopeStack, placeholders, markers);
            }
            else if (child is Paragraph para)
            {
                var text = GetParagraphText(para);
                if (string.IsNullOrEmpty(text)) continue;

                var textTrimmed = text.Trim();
                var openMatch = MarkerOpenRx.Match(textTrimmed);
                if (openMatch.Success)
                {
                    var markerName = openMatch.Groups[1].Value;
                    if (MarkerToLevel.TryGetValue(markerName, out var level))
                    {
                        scopeStack.Push(level);
                        markers.Add(new FoundMarker($"[[{markerName}]]", true, level, baseLocation));
                    }
                    continue;
                }

                var closeMatch = MarkerCloseRx.Match(textTrimmed);
                if (closeMatch.Success)
                {
                    var markerName = closeMatch.Groups[1].Value;
                    if (MarkerToLevel.TryGetValue(markerName, out var level))
                    {
                        if (scopeStack.Count > 0 && scopeStack.Peek() == level)
                            scopeStack.Pop();
                        markers.Add(new FoundMarker($"[[/{markerName}]]", false, level, baseLocation));
                    }
                    continue;
                }

                var currentScope = scopeStack.Count > 0 ? scopeStack.Peek() : "report";
                foreach (Match m in PlaceholderRx.Matches(text))
                    placeholders.Add(new FoundPlaceholder(m.Groups[1].Value, baseLocation, currentScope));
            }
        }
    }

    private static void ScanTable(Table table, string baseLocation, int tableIndex,
        Stack<string> scopeStack, List<FoundPlaceholder> placeholders, List<FoundMarker> markers)
    {
        var currentScope = scopeStack.Count > 0 ? scopeStack.Peek() : "report";
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
                {
                    var text = GetParagraphText(para);
                    if (string.IsNullOrEmpty(text)) continue;
                    foreach (Match m in PlaceholderRx.Matches(text))
                        placeholders.Add(new FoundPlaceholder(m.Groups[1].Value, loc, currentScope));
                }
            }
        }
    }

    private static void ScanStatic(OpenXmlElement scope, string baseLocation,
        string fixedScope, List<FoundPlaceholder> placeholders)
    {
        foreach (var para in scope.Descendants<Paragraph>())
        {
            var text = GetParagraphText(para);
            if (string.IsNullOrEmpty(text)) continue;
            foreach (Match m in PlaceholderRx.Matches(text))
                placeholders.Add(new FoundPlaceholder(m.Groups[1].Value, baseLocation, fixedScope));
        }
    }

    private static string GetParagraphText(Paragraph para) =>
        string.Concat(para.Elements<Run>().SelectMany(r => r.Elements<Text>()).Select(t => t.Text));

    // ── helpers ──

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

    private static string BuildCatalogNotFoundMessage(string requested)
    {
        var available = CatalogStore.List().Select(c => c.Id).ToList();
        var hint = available.Count == 0
            ? "（当前没有任何字段目录）"
            : $"可选：{string.Join(", ", available)}";
        return $"字段目录不存在：{requested}。{hint}";
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
