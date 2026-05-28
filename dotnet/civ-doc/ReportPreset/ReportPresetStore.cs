// 报告预设存储 —— 整份报告 user_inputs（+ 元数据）保存到 ~/.civ-core/report_presets/<id>.json，
// 用户下次新建同类报告一键载入。
//
// 设计取舍：
//   - **整份预设**而非按字段历史值（用户拍板：「整份报告一套预设」）。
//     按字段历史值在 P4-5 历史值下拉里基于这里的预设聚合实现，不单独存。
//   - **以 catalog_id 关联**：一个预设绑定一个 catalog（例：anchor / leeb）；列预设时
//     可按 catalog_id 过滤，避免给锚杆报告拉出钻芯的预设。
//   - **不存 word_template_path / excel_path 等会话级 state**：那些每次都不一样，
//     存 Tauri activatedFile 即可。预设只保存「会跨报告复用的部分」。

using System.Text.Json;
using System.Text.Json.Serialization;

namespace CivCore.Doc.ReportPreset;

public record ReportPresetDto
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("label")]
    public string Label { get; init; } = "";

    /// <summary>所属字段目录（anchor / leeb / ...）；列预设时按此过滤。</summary>
    [JsonPropertyName("catalog_id")]
    public string CatalogId { get; init; } = "";

    /// <summary>报告级 + 检测项目级 user_inputs（catalog 里 level=report/detection_item 的字段）。</summary>
    [JsonPropertyName("user_inputs")]
    public Dictionary<string, string> UserInputs { get; init; } = new();

    /// <summary>创建/更新时间戳（ISO 8601 UTC）；列预设时按此排序。</summary>
    [JsonPropertyName("updated_at")]
    public string UpdatedAt { get; init; } = "";
}

public record ReportPresetSummary
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("label")]
    public string Label { get; init; } = "";

    [JsonPropertyName("catalog_id")]
    public string CatalogId { get; init; } = "";

    [JsonPropertyName("updated_at")]
    public string UpdatedAt { get; init; } = "";

    [JsonPropertyName("field_count")]
    public int FieldCount { get; init; }
}

public static class ReportPresetStore
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static string PresetDir()
    {
        var home = Environment.GetEnvironmentVariable("USERPROFILE")
            ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var dir = Path.Combine(home, ".civ-core", "report_presets");
        if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
        return dir;
    }

    private static string PresetPath(string id) => Path.Combine(PresetDir(), $"{SafeFileName(id)}.json");

    public static List<ReportPresetSummary> List(string? catalogId = null)
    {
        var dir = PresetDir();
        var result = new List<ReportPresetSummary>();
        foreach (var file in Directory.GetFiles(dir, "*.json"))
        {
            try
            {
                var json = File.ReadAllText(file);
                var dto = JsonSerializer.Deserialize<ReportPresetDto>(json, JsonOpts);
                if (dto == null) continue;
                if (!string.IsNullOrEmpty(catalogId) && dto.CatalogId != catalogId) continue;
                result.Add(new ReportPresetSummary
                {
                    Id = dto.Id,
                    Label = dto.Label,
                    CatalogId = dto.CatalogId,
                    UpdatedAt = dto.UpdatedAt,
                    FieldCount = dto.UserInputs.Count,
                });
            }
            catch
            {
                // skip malformed presets
            }
        }
        return result.OrderByDescending(p => p.UpdatedAt).ToList();
    }

    public static ReportPresetDto? Get(string id)
    {
        var path = PresetPath(id);
        if (!File.Exists(path)) return null;
        var json = File.ReadAllText(path);
        return JsonSerializer.Deserialize<ReportPresetDto>(json, JsonOpts);
    }

    public static void Save(ReportPresetDto preset)
    {
        if (string.IsNullOrWhiteSpace(preset.Id))
            throw new ArgumentException("预设 id 不可为空");
        if (string.IsNullOrWhiteSpace(preset.Label))
            throw new ArgumentException("预设名称不可为空");
        var stamped = preset with { UpdatedAt = DateTime.UtcNow.ToString("o") };
        var json = JsonSerializer.Serialize(stamped, JsonOpts);
        File.WriteAllText(PresetPath(stamped.Id), json);
    }

    public static void Delete(string id)
    {
        var path = PresetPath(id);
        if (File.Exists(path)) File.Delete(path);
    }

    public static void Rename(string id, string newLabel)
    {
        var dto = Get(id) ?? throw new ArgumentException($"预设不存在：{id}");
        Save(dto with { Label = newLabel });
    }

    private static string SafeFileName(string s)
    {
        foreach (var c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
        return s;
    }
}
