// template.* RPC 接入 —— 薄 adapter，目前只剩"字段清单查询"。
//
// 方法清单：
//   template.fields(project_type)
//     -> {fields: [{key, name, source, value_type, default_format}]}
//
// 历史包袱清理（占位符驱动后这些不再需要）：
//   template.parse/save/list/load/delete 已删 —— 模板就是用户的 Word 文件本身，
//   没 JSON 配置 / 没 ~/.civ-core/templates/ 存储 / 没 bindings 数组。
//
// 报告生成走 report.* RPC（见 ReportHandlers）。

using System.Text.Json;
using CivCore.Doc.Calc.Anchor;
using CivCore.Doc.Server;
using CivCore.Doc.Template;

namespace CivCore.Doc.Handlers;

public static class TemplateHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("template.fields", Fields);
    }

    public static object Fields(JsonElement? @params)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("操作参数格式错误，请重试");
        var p = @params.Value;
        if (!p.TryGetProperty("project_type", out var ptEl) || ptEl.ValueKind != JsonValueKind.String)
            throw new ArgumentException("缺少或非法参数：project_type");
        var projectType = ptEl.GetString();
        if (string.IsNullOrWhiteSpace(projectType))
            throw new ArgumentException("project_type 不可为空");

        return new Dictionary<string, object?>
        {
            ["fields"] = GetCatalog(projectType).Select(ProjectField).ToList(),
        };
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
}
