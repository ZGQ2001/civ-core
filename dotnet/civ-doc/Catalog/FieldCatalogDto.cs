using System.Text.Json.Serialization;

namespace CivCore.Doc.Catalog;

public record CatalogFieldDto
{
    [JsonPropertyName("key")]
    public string Key { get; init; } = "";

    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("group")]
    public string Group { get; init; } = "";

    /// <summary>
    /// 字段层级：report（报告级）| detection_item（检测项目级）| batch（检测批级）| component（构件级）。
    /// 模板验证器据此检查占位符是否放在正确的重复标记区域内。
    /// </summary>
    [JsonPropertyName("level")]
    public string Level { get; init; } = "report";

    [JsonPropertyName("source")]
    public string Source { get; init; } = "user_input";

    [JsonPropertyName("value_type")]
    public string ValueType { get; init; } = "string";

    [JsonPropertyName("default_format")]
    public string? DefaultFormat { get; init; }

    [JsonPropertyName("aliases")]
    public List<string> Aliases { get; init; } = new();
}

public record FieldCatalogDto
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("label")]
    public string Label { get; init; } = "";

    [JsonPropertyName("fields")]
    public List<CatalogFieldDto> Fields { get; init; } = new();
}

public record CatalogSummary
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("label")]
    public string Label { get; init; } = "";

    [JsonPropertyName("field_count")]
    public int FieldCount { get; init; }
}
