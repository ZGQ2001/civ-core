using System.Text.Json;
using CivCore.Doc.Catalog;
using CivCore.Doc.Server;

namespace CivCore.Doc.Handlers;

public static class CatalogHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("catalog.list", ListCatalogs);
        d.Register("catalog.get", GetCatalog);
        d.Register("catalog.save", SaveCatalog);
        d.Register("catalog.delete", DeleteCatalog);
    }

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static object ListCatalogs(JsonElement? @params)
    {
        return new Dictionary<string, object?>
        {
            ["catalogs"] = CatalogStore.List(),
        };
    }

    private static object GetCatalog(JsonElement? @params)
    {
        var id = RequireString(@params, "id");
        var catalog = CatalogStore.Get(id)
            ?? throw new ArgumentException($"字段目录不存在：{id}");
        return new Dictionary<string, object?>
        {
            ["catalog"] = catalog,
        };
    }

    private static object SaveCatalog(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        if (!p.TryGetProperty("catalog", out var catEl))
            throw new ArgumentException("缺少参数: catalog");

        var catalog = JsonSerializer.Deserialize<FieldCatalogDto>(catEl.GetRawText(), JsonOpts)
            ?? throw new ArgumentException("catalog 格式错误");

        CatalogStore.Save(catalog);
        return new Dictionary<string, object?> { ["ok"] = true };
    }

    private static object DeleteCatalog(JsonElement? @params)
    {
        var id = RequireString(@params, "id");
        CatalogStore.Delete(id);
        return new Dictionary<string, object?> { ["ok"] = true };
    }

    private static string RequireString(JsonElement? @params, string key)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;
        if (!p.TryGetProperty(key, out var el) || el.ValueKind != JsonValueKind.String)
            throw new ArgumentException($"缺少或非法参数：{key}");
        var v = el.GetString();
        if (string.IsNullOrWhiteSpace(v))
            throw new ArgumentException($"参数 {key} 不可为空");
        return v;
    }
}
