// report_preset.* RPC：报告填充 user_inputs 预设 CRUD。
//
// 方法清单：
//   report_preset.list(catalog_id?)        -> {presets: [ReportPresetSummary]}
//   report_preset.get(id)                  -> {preset: ReportPresetDto}
//   report_preset.save(preset)             -> {ok, id, updated_at}
//   report_preset.delete(id)               -> {ok}
//   report_preset.rename(id, label)        -> {ok}

using System.Text.Json;
using CivCore.Doc.ReportPreset;
using CivCore.Doc.Server;

namespace CivCore.Doc.Handlers;

public static class ReportPresetHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("report_preset.list", List);
        d.Register("report_preset.get", Get);
        d.Register("report_preset.save", Save);
        d.Register("report_preset.delete", Delete);
        d.Register("report_preset.rename", Rename);
    }

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static object List(JsonElement? @params)
    {
        string? catalogId = null;
        if (@params is { ValueKind: JsonValueKind.Object } p
            && p.TryGetProperty("catalog_id", out var cEl)
            && cEl.ValueKind == JsonValueKind.String)
            catalogId = cEl.GetString();
        return new Dictionary<string, object?>
        {
            ["presets"] = ReportPresetStore.List(catalogId),
        };
    }

    private static object Get(JsonElement? @params)
    {
        var id = RequireString(@params, "id");
        var preset = ReportPresetStore.Get(id)
            ?? throw new ArgumentException($"预设不存在：{id}");
        return new Dictionary<string, object?> { ["preset"] = preset };
    }

    private static object Save(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;

        if (!p.TryGetProperty("preset", out var presetEl))
            throw new ArgumentException("缺少参数: preset");

        var dto = JsonSerializer.Deserialize<ReportPresetDto>(presetEl.GetRawText(), JsonOpts)
            ?? throw new ArgumentException("preset 格式错误");

        ReportPresetStore.Save(dto);
        // 重新读一次拿带时间戳的版本
        var saved = ReportPresetStore.Get(dto.Id);
        return new Dictionary<string, object?>
        {
            ["ok"] = true,
            ["id"] = dto.Id,
            ["updated_at"] = saved?.UpdatedAt ?? "",
        };
    }

    private static object Delete(JsonElement? @params)
    {
        var id = RequireString(@params, "id");
        ReportPresetStore.Delete(id);
        return new Dictionary<string, object?> { ["ok"] = true };
    }

    private static object Rename(JsonElement? @params)
    {
        var id = RequireString(@params, "id");
        var label = RequireString(@params, "label");
        ReportPresetStore.Rename(id, label);
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
