// 模板字段元数据 —— 通用引擎层。
//
// 这里只放跟具体计算类型（锚杆/钻芯/回弹/...）无关的通用类型。
// 每种 calc 类型自己的字段清单放在 Calc/<Type>/<Type>FieldCatalog.cs，
// 通过 FieldDef 接入引擎；引擎本身永不出现 "anchor_id" 这种硬编码 key。
//
// 解耦要点：
//   - Key 是绑定主键，永不变（规范改名/换术语时只换 Name，不动 Key）
//   - 模板 JSON 里只存 fieldKey；规范涉及的中文显示走 catalog 查表
//   - FieldSource 给前端 BindingPanel 分组用，引擎不依赖

namespace CivCore.Doc.Template;

/// <summary>字段来源——给前端 UI 分组用（参数 / 计算结果 / 用户输入）。</summary>
public enum FieldSource
{
    /// <summary>来自工程参数（同批次共享）：轴向拉力设计值、自由段长度等。</summary>
    Parameter,

    /// <summary>来自计算结果：弹性位移量、判定结果等。</summary>
    Calculated,

    /// <summary>来自单行原始输入：锚杆编号、位移读数等。</summary>
    RawInput,

    /// <summary>用户在前端表单额外填入：委托方、试验日期等。</summary>
    UserInput,
}

/// <summary>
/// 单个可绑定字段的元数据。
///
/// <para>Key 是唯一主键，模板 JSON 永远存这个；改名只换 Name 不动 Key。</para>
/// <para>Format 是默认格式串（仅 Numeric 类型有意义），如 "0.00"；模板里也能 override。</para>
/// </summary>
/// <param name="Key">主键，绝不变。snake_case，如 "elastic_displacement"。</param>
/// <param name="Name">中文显示名（给前端 BindingPanel 看的），如 "弹性位移量"。</param>
/// <param name="Source">字段来源（分组用）。</param>
/// <param name="ValueType">值类型："string" | "double" | "int" | "bool"。引擎只用来选默认格式。</param>
/// <param name="DefaultFormat">默认 .NET 数字格式串（仅 double/int 有意义），如 "0.00"。</param>
public record FieldDef(
    string Key,
    string Name,
    FieldSource Source,
    string ValueType,
    string? DefaultFormat = null
)
{
    public static FieldDef Create(
        string key,
        string name,
        FieldSource source,
        string valueType,
        string? defaultFormat = null)
    {
        if (string.IsNullOrWhiteSpace(key))
            throw new ArgumentException("字段 Key 不可为空");
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException($"字段 {key} 缺中文名");
        if (valueType is not ("string" or "double" or "int" or "bool"))
            throw new ArgumentException($"字段 {key} 的 ValueType 不合法：{valueType}");
        return new FieldDef(key, name, source, valueType, defaultFormat);
    }
}
