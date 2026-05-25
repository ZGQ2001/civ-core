// 模板配置 —— 纯数据 + JSON 序列化（不管存哪里）。
//
// 存储路径、目录管理在 TemplateStorage.cs 里。两层解耦：
// 序列化逻辑（这里）不依赖文件系统，可以拿去做内存测试 / 网络传输。

using System.Text.Json;
using System.Text.Json.Serialization;

namespace CivCore.Doc.Template;

/// <summary>报告生成时的"表重复策略"。</summary>
public enum RepeatStrategy
{
    /// <summary>一根锚杆一张表（最常见，per_anchor）。</summary>
    PerRow,

    /// <summary>一批一张表（多根锚杆汇总到一张表里，未来再实现）。</summary>
    PerBatch,
}

/// <summary>单元格→字段绑定。</summary>
/// <param name="Row">主格 0-based 行号（视觉网格）。</param>
/// <param name="Col">主格 0-based 列号（视觉网格）。</param>
/// <param name="FieldKey">绑的字段 Key（不存 Name —— Name 可改 Key 不变）。</param>
/// <param name="Format">.NET 数字格式串，null 走 FieldDef.DefaultFormat。</param>
public record CellBinding(int Row, int Col, string FieldKey, string? Format = null);

/// <summary>
/// 一份模板的完整配置（对应磁盘上的 config.json）。
/// </summary>
public record TemplateConfig
{
    /// <summary>schema 版本，预留破坏性改动用。</summary>
    public int Version { get; init; } = 1;

    /// <summary>所属检测类型："anchor" / "drilling" / "rebound" / ...</summary>
    public string ProjectType { get; init; } = "";

    /// <summary>给用户看的中文名："锚杆抗拔试验报告"。</summary>
    public string DisplayName { get; init; } = "";

    /// <summary>解析时算出的表格签名，生成时比对，防模板被偷改。</summary>
    public string TableSignature { get; init; } = "";

    /// <summary>表重复策略。</summary>
    public RepeatStrategy Repeat { get; init; } = RepeatStrategy.PerRow;

    /// <summary>所有单元格绑定（顺序无意义；填表时按 FieldKey 查）。</summary>
    public List<CellBinding> Bindings { get; init; } = new();

    // ── 序列化 ──────────────────────────────────────────────

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public string ToJson() => JsonSerializer.Serialize(this, JsonOpts);

    public static TemplateConfig FromJson(string json)
    {
        var cfg = JsonSerializer.Deserialize<TemplateConfig>(json, JsonOpts)
            ?? throw new TemplateConfigException("模板配置 JSON 反序列化失败：得到 null");
        Validate(cfg);
        return cfg;
    }

    /// <summary>反序列化后基础校验 —— 拒绝坏 JSON 沉默通过。</summary>
    private static void Validate(TemplateConfig cfg)
    {
        if (string.IsNullOrWhiteSpace(cfg.ProjectType))
            throw new TemplateConfigException("模板配置缺 projectType");
        if (string.IsNullOrWhiteSpace(cfg.DisplayName))
            throw new TemplateConfigException("模板配置缺 displayName");
        if (string.IsNullOrWhiteSpace(cfg.TableSignature))
            throw new TemplateConfigException("模板配置缺 tableSignature（保存时应由 TemplateParser 写入）");

        // 同一格不能绑两个字段 & 同一字段不能绑两个格
        var cellSet = new HashSet<(int, int)>();
        var keySet = new HashSet<string>();
        foreach (var b in cfg.Bindings)
        {
            if (!cellSet.Add((b.Row, b.Col)))
                throw new TemplateConfigException($"单元格 ({b.Row},{b.Col}) 重复绑定");
            if (!keySet.Add(b.FieldKey))
                throw new TemplateConfigException($"字段 {b.FieldKey} 重复绑定到多个单元格");
        }
    }
}

/// <summary>配置不合法时抛 —— 给 handler 翻成 RPC -32602。</summary>
public class TemplateConfigException : Exception
{
    public TemplateConfigException(string msg) : base(msg) { }
}
