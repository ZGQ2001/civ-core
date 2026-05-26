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
