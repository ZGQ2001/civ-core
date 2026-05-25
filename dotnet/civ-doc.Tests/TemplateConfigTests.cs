// TemplateConfig + TemplateStorage 测试。
// Config = 序列化 + 校验；Storage = 文件系统持久化（用 tempRoot 注入避免污染真实 ~/.civ-core/）。

using CivCore.Doc.Template;

namespace civ_doc.Tests;

public class TemplateConfigTests
{
    private static TemplateConfig SampleConfig() => new()
    {
        ProjectType = "anchor",
        DisplayName = "锚杆抗拔试验报告",
        TableSignature = "rows:4_cols:4_hash:ABCDEF",
        Repeat = RepeatStrategy.PerRow,
        Bindings =
        {
            new CellBinding(2, 0, "anchor_id"),
            new CellBinding(2, 1, "elastic_displacement", Format: "0.00"),
        },
    };

    // ── JSON 序列化 ─────────────────────────────────────────

    [Fact]
    public void ToJson_FromJson_往返一致()
    {
        var original = SampleConfig();
        var json = original.ToJson();
        var restored = TemplateConfig.FromJson(json);

        Assert.Equal(original.ProjectType, restored.ProjectType);
        Assert.Equal(original.DisplayName, restored.DisplayName);
        Assert.Equal(original.TableSignature, restored.TableSignature);
        Assert.Equal(original.Repeat, restored.Repeat);
        Assert.Equal(2, restored.Bindings.Count);
        Assert.Equal("anchor_id", restored.Bindings[0].FieldKey);
        Assert.Equal("0.00", restored.Bindings[1].Format);
    }

    [Fact]
    public void ToJson_输出蛇形key_中文不转义()
    {
        var json = SampleConfig().ToJson();
        Assert.Contains("\"project_type\"", json);
        Assert.Contains("\"table_signature\"", json);
        Assert.Contains("\"field_key\"", json);
        Assert.Contains("\"per_row\"", json);
        Assert.Contains("锚杆抗拔试验报告", json); // 中文未转 \uXXXX
    }

    [Fact]
    public void FromJson_缺projectType_抛异常()
    {
        var json = """
            {"version":1,"display_name":"x","table_signature":"y","repeat":"per_row","bindings":[]}
            """;
        var ex = Assert.Throws<TemplateConfigException>(() => TemplateConfig.FromJson(json));
        Assert.Contains("projectType", ex.Message);
    }

    [Fact]
    public void FromJson_重复绑定同一格_抛异常()
    {
        var bad = SampleConfig() with
        {
            Bindings = [new CellBinding(2, 0, "anchor_id"), new CellBinding(2, 0, "anchor_id_dup")],
        };
        var ex = Assert.Throws<TemplateConfigException>(() => TemplateConfig.FromJson(bad.ToJson()));
        Assert.Contains("重复绑定", ex.Message);
    }

    [Fact]
    public void FromJson_同字段绑两格_抛异常()
    {
        var bad = SampleConfig() with
        {
            Bindings = [new CellBinding(2, 0, "anchor_id"), new CellBinding(3, 0, "anchor_id")],
        };
        var ex = Assert.Throws<TemplateConfigException>(() => TemplateConfig.FromJson(bad.ToJson()));
        Assert.Contains("anchor_id", ex.Message);
    }
}

public class TemplateStorageTests : IDisposable
{
    private readonly string _root;
    private readonly TempDocx _docx = new();

    public TemplateStorageTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "civ_core_storage_test_" + Guid.NewGuid().ToString("N"));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
        _docx.Dispose();
        GC.SuppressFinalize(this);
    }

    private string MakeSampleDocx() => _docx.Write("source.docx", TemplateParser.AnchorMarker, b =>
        b.Row(new CellSpec("A1"), new CellSpec("B1")));

    private static TemplateConfig MakeConfig(string sig = "rows:1_cols:2_hash:ABCDEF") => new()
    {
        ProjectType = "anchor",
        DisplayName = "测试模板",
        TableSignature = sig,
        Repeat = RepeatStrategy.PerRow,
        Bindings = { new CellBinding(0, 0, "anchor_id") },
    };

    [Fact]
    public void Save_Load_往返一致()
    {
        var src = MakeSampleDocx();
        var cfg = MakeConfig();
        TemplateStorage.Save("锚杆模板", src, cfg, _root);

        var (loaded, docxPath) = TemplateStorage.Load("锚杆模板", _root);
        Assert.Equal(cfg.TableSignature, loaded.TableSignature);
        Assert.True(File.Exists(docxPath));
        Assert.Equal(TemplateStorage.SourceDocxName, Path.GetFileName(docxPath));
    }

    [Fact]
    public void Save_覆盖已有_新内容生效()
    {
        var src = MakeSampleDocx();
        TemplateStorage.Save("dup", src, MakeConfig("rows:1_cols:2_hash:OLDSIG"), _root);
        TemplateStorage.Save("dup", src, MakeConfig("rows:1_cols:2_hash:NEWSIG"), _root);

        var (loaded, _) = TemplateStorage.Load("dup", _root);
        Assert.Equal("rows:1_cols:2_hash:NEWSIG", loaded.TableSignature);
    }

    [Fact]
    public void ListNames_按字母序返回()
    {
        var src = MakeSampleDocx();
        TemplateStorage.Save("zebra", src, MakeConfig(), _root);
        TemplateStorage.Save("alpha", src, MakeConfig(), _root);
        TemplateStorage.Save("mango", src, MakeConfig(), _root);

        var names = TemplateStorage.ListNames(_root);
        Assert.Equal(new[] { "alpha", "mango", "zebra" }, names);
    }

    [Fact]
    public void Delete_存在则真删_不存在返回false()
    {
        var src = MakeSampleDocx();
        TemplateStorage.Save("toDelete", src, MakeConfig(), _root);
        Assert.True(TemplateStorage.Delete("toDelete", _root));
        Assert.False(Directory.Exists(TemplateStorage.GetTemplateDir("toDelete", _root)));
        Assert.False(TemplateStorage.Delete("toDelete", _root)); // 幂等
    }

    [Fact]
    public void Save_非法字符名_抛异常()
    {
        var src = MakeSampleDocx();
        var ex = Assert.Throws<TemplateStorageException>(() =>
            TemplateStorage.Save("bad/name", src, MakeConfig(), _root));
        Assert.Contains("非法字符", ex.Message);
    }

    [Fact]
    public void Load_不存在的模板_抛异常()
    {
        var ex = Assert.Throws<TemplateStorageException>(() => TemplateStorage.Load("nope", _root));
        Assert.Contains("不存在", ex.Message);
    }

    [Fact]
    public void Save_原始docx不存在_抛异常带路径()
    {
        var ex = Assert.Throws<TemplateStorageException>(() =>
            TemplateStorage.Save("x", Path.Combine(_root, "ghost.docx"), MakeConfig(), _root));
        Assert.Contains("不存在", ex.Message);
    }
}
