// template.* RPC 接入 —— 薄 adapter，不写业务逻辑。
//
// 方法清单（report.generate 留给 Phase 3 跟 anchor 流程对接时再加）：
//   template.parse(docx_path)
//     -> {cells, row_count, col_count, table_signature}
//   template.fields(project_type)
//     -> {fields: [{key, name, source, value_type, default_format}]}
//   template.save(name, source_docx_path, config)
//     -> {ok: true}
//   template.list()
//     -> {templates: [{name, project_type, display_name}]}
//   template.load(name)
//     -> {config, source_docx_path, parsed}
//   template.delete(name)
//     -> {ok: true}
//
// 解耦：handler 不直接 new ParsedCell —— 全部转字典做 JSON 投影。
// 锚杆字段清单走 AnchorFieldCatalog；未来加钻芯/回弹只在 GetCatalog 加分支。

using System.Text.Json;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Server;
using CivCore.Doc.Template;

namespace CivCore.Doc.Handlers;

public static class TemplateHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("template.parse", Parse);
        d.Register("template.fields", Fields);
        d.Register("template.save", Save);
        d.Register("template.list", List);
        d.Register("template.load", Load);
        d.Register("template.delete", Delete);
    }

    public static object Parse(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var docxPath = RequireString(p, "docx_path");
        try
        {
            var parsed = TemplateParser.Parse(docxPath);
            return ProjectParsed(parsed);
        }
        catch (TemplateParseException e) { throw new ArgumentException(e.Message); }
    }

    public static object Fields(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var projectType = RequireString(p, "project_type");
        return new Dictionary<string, object?>
        {
            ["fields"] = GetCatalog(projectType).Select(ProjectField).ToList(),
        };
    }

    public static object Save(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var name = RequireString(p, "name");
        var docxPath = RequireString(p, "source_docx_path");
        if (!p.TryGetProperty("config", out var cfgEl) || cfgEl.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("缺 config 对象");

        TemplateConfig config;
        try { config = TemplateConfig.FromJson(cfgEl.GetRawText()); }
        catch (TemplateConfigException e) { throw new ArgumentException(e.Message); }

        try { TemplateStorage.Save(name, docxPath, config); }
        catch (TemplateStorageException e) { throw new ArgumentException(e.Message); }
        return new Dictionary<string, object?> { ["ok"] = true, ["name"] = name };
    }

    public static object List(JsonElement? @params)
    {
        var names = TemplateStorage.ListNames();
        var rows = new List<Dictionary<string, object?>>();
        foreach (var n in names)
        {
            try
            {
                var (cfg, _) = TemplateStorage.Load(n);
                rows.Add(new()
                {
                    ["name"] = n,
                    ["project_type"] = cfg.ProjectType,
                    ["display_name"] = cfg.DisplayName,
                });
            }
            catch
            {
                // 坏掉的模板目录不阻塞列表 —— 标 broken 让前端能感知
                rows.Add(new() { ["name"] = n, ["broken"] = true });
            }
        }
        return new Dictionary<string, object?> { ["templates"] = rows };
    }

    public static object Load(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var name = RequireString(p, "name");
        try
        {
            var (cfg, docxPath) = TemplateStorage.Load(name);
            var parsed = TemplateParser.Parse(docxPath);
            return new Dictionary<string, object?>
            {
                ["config"] = JsonSerializer.Deserialize<JsonElement>(cfg.ToJson()),
                ["source_docx_path"] = docxPath,
                ["parsed"] = ProjectParsed(parsed),
            };
        }
        catch (TemplateStorageException e) { throw new ArgumentException(e.Message); }
        catch (TemplateParseException e) { throw new ArgumentException(e.Message); }
        catch (TemplateConfigException e) { throw new ArgumentException(e.Message); }
    }

    public static object Delete(JsonElement? @params)
    {
        var p = RequireObject(@params);
        var name = RequireString(p, "name");
        try
        {
            var deleted = TemplateStorage.Delete(name);
            return new Dictionary<string, object?> { ["ok"] = deleted };
        }
        catch (TemplateStorageException e) { throw new ArgumentException(e.Message); }
    }

    // ── JSON 投影 helpers（保持 wire 格式跟前端约定一致） ──

    private static Dictionary<string, object?> ProjectParsed(ParsedTable t) => new()
    {
        ["row_count"] = t.RowCount,
        ["col_count"] = t.ColCount,
        ["table_signature"] = t.TableSignature,
        ["cells"] = ProjectCells(t),
    };

    private static List<Dictionary<string, object?>> ProjectCells(ParsedTable t)
    {
        var list = new List<Dictionary<string, object?>>();
        for (int r = 0; r < t.Rows.Count; r++)
        {
            foreach (var (c, cell) in t.Rows[r])
            {
                list.Add(new()
                {
                    ["row"] = r,
                    ["col"] = c,
                    ["text"] = cell.Text,
                    ["row_span"] = cell.RowSpan,
                    ["col_span"] = cell.ColSpan,
                    ["bold"] = cell.Bold,
                    ["font_size"] = cell.FontSize,
                });
            }
        }
        return list;
    }

    private static Dictionary<string, object?> ProjectField(FieldDef f) => new()
    {
        ["key"] = f.Key,
        ["name"] = f.Name,
        ["source"] = f.Source.ToString().ToLowerInvariant(),
        ["value_type"] = f.ValueType,
        ["default_format"] = f.DefaultFormat,
    };

    /// <summary>按 project_type 返回字段清单。加新检测类型只在这里加分支。</summary>
    private static IEnumerable<FieldDef> GetCatalog(string projectType) => projectType switch
    {
        "anchor" => AnchorFieldCatalog.All,
        _ => throw new ArgumentException($"未知 project_type：{projectType}（当前支持：anchor）"),
    };

    // ── 参数解析 ────────────────────────────────────────────

    private static JsonElement RequireObject(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        return @params.Value;
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
