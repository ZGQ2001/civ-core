// TemplateHandlers RPC 测试 —— 模拟前端调参数（JsonElement）+ 校验返回结构。
// 跑真的 TemplateStorage 但用 tempRoot：无法注入，所以 list/load/save/delete 测在
// TemplateStorageTests.cs 已覆盖；这里只测 Parse + Fields 走 RPC 边界的逻辑。

using System.Text.Json;
using CivCore.Doc.Handlers;
using CivCore.Doc.Template;

namespace civ_doc.Tests;

public class TemplateHandlersTests : IDisposable
{
    private readonly TempDocx _docx = new();
    public void Dispose() { _docx.Dispose(); GC.SuppressFinalize(this); }

    private static JsonElement Json(string s) => JsonDocument.Parse(s).RootElement;

    // ── template.parse ──────────────────────────────────────

    [Fact]
    public void Parse_正常_返回rows_cols_signature_cells()
    {
        var path = _docx.Write("ok.docx", TemplateParser.AnchorMarker, b =>
            b.Row(new CellSpec("A1"), new CellSpec("B1"))
             .Row(new CellSpec("A2"), new CellSpec("B2")));
        var p = Json($"{{\"docx_path\":\"{path.Replace("\\", "\\\\")}\"}}");

        var raw = TemplateHandlers.Parse(p);
        var d = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(raw);

        Assert.Equal(2, d["row_count"]);
        Assert.Equal(2, d["col_count"]);
        Assert.StartsWith("rows:2_cols:2_hash:", (string)d["table_signature"]!);

        var cells = (List<Dictionary<string, object?>>)d["cells"]!;
        Assert.Equal(4, cells.Count);
        Assert.Contains(cells, c => (int)c["row"]! == 0 && (int)c["col"]! == 0 && (string)c["text"]! == "A1");
    }

    [Fact]
    public void Parse_缺docx_path_抛ArgumentException()
    {
        var ex = Assert.Throws<ArgumentException>(() => TemplateHandlers.Parse(Json("{}")));
        Assert.Contains("docx_path", ex.Message);
    }

    [Fact]
    public void Parse_文件不存在_抛ArgumentException()
    {
        var ex = Assert.Throws<ArgumentException>(() =>
            TemplateHandlers.Parse(Json("{\"docx_path\":\"C:/__nope__.docx\"}")));
        Assert.Contains("不存在", ex.Message);
    }

    // ── template.fields ─────────────────────────────────────

    [Fact]
    public void Fields_anchor_返回锚杆字段清单()
    {
        var raw = TemplateHandlers.Fields(Json("{\"project_type\":\"anchor\"}"));
        var d = (Dictionary<string, object?>)raw;
        var fields = (List<Dictionary<string, object?>>)d["fields"]!;

        Assert.NotEmpty(fields);
        // 关键 key 都在
        var keys = fields.Select(f => (string)f["key"]!).ToHashSet();
        Assert.Contains("anchor_id", keys);
        Assert.Contains("elastic_displacement", keys);
        Assert.Contains("judgement_result", keys);
        // 每条都有完整 schema
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

    // ── 参数边界 ────────────────────────────────────────────

    [Fact]
    public void Parse_params为null_抛ArgumentException()
    {
        Assert.Throws<ArgumentException>(() => TemplateHandlers.Parse(null));
    }

    [Fact]
    public void Parse_params为数组_抛ArgumentException()
    {
        Assert.Throws<ArgumentException>(() => TemplateHandlers.Parse(Json("[1,2]")));
    }
}
