// 模板引擎跟具体计算类型的解耦点 —— 由调用方提供 row 数据，引擎绝不 switch fieldKey。
//
// 实现示例：Calc/Anchor/AnchorRowResolver.cs（锚杆专属）。
// 未来加钻芯/回弹只需要新增一个 IFieldResolver 实现，PlaceholderRenderer 零改动。

namespace CivCore.Doc.Template;

public interface IFieldResolver
{
    /// <summary>
    /// 给定 fieldKey 返回该 row 对应的原始值（string / double / int / bool / null）。
    /// 数字格式化由 PlaceholderRenderer 按 catalog DefaultFormat 处理，resolver 不要 ToString("0.00")。
    /// 未知 key 返回 null（PlaceholderRenderer 留原文 + 计入 unknownKeys）。
    /// </summary>
    object? GetValue(string fieldKey);
}
