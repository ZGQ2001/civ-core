// TemplateHandlers RPC 测试 —— 占位符驱动后只剩 template.fields。

using System.Text.Json;
using CivCore.Doc.Handlers;

namespace civ_doc.Tests;

public class TemplateHandlersTests
{
    private static JsonElement Json(string s) => JsonDocument.Parse(s).RootElement;

    [Fact]
    public void Fields_anchor_返回锚杆字段清单()
    {
        var raw = TemplateHandlers.Fields(Json("{\"project_type\":\"anchor\"}"));
        var d = (Dictionary<string, object?>)raw;
        var fields = (List<Dictionary<string, object?>>)d["fields"]!;

        Assert.NotEmpty(fields);
        var keys = fields.Select(f => (string)f["key"]!).ToHashSet();
        Assert.Contains("anchor_id", keys);
        Assert.Contains("elastic_displacement", keys);
        Assert.Contains("judgement_result", keys);
        Assert.All(fields, f =>
        {
            Assert.True(f.ContainsKey("name"));
            Assert.True(f.ContainsKey("source"));
            Assert.True(f.ContainsKey("value_type"));
            Assert.True(f.ContainsKey("default_format"));
        });
    }

    [Fact]
    public void Fields_未知project_type_抛ArgumentException()
    {
        var ex = Assert.Throws<ArgumentException>(() =>
            TemplateHandlers.Fields(Json("{\"project_type\":\"alien\"}")));
        Assert.Contains("alien", ex.Message);
        Assert.Contains("anchor", ex.Message);
    }

    [Fact]
    public void Fields_缺project_type_抛ArgumentException()
    {
        var ex = Assert.Throws<ArgumentException>(() =>
            TemplateHandlers.Fields(Json("{}")));
        Assert.Contains("project_type", ex.Message);
    }

    [Fact]
    public void Fields_params为null_抛ArgumentException()
    {
        Assert.Throws<ArgumentException>(() => TemplateHandlers.Fields(null));
    }
}
