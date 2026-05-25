// TemplateParser xUnit 测试 —— fixture 构造工具拆到 DocxTestFixtures.cs。
//
// 必测覆盖（plan 强制）：
//   - 锚点缺失 / 锚点后无表 / 文件不存在
//   - gridSpan（横向合并）
//   - vMerge（纵向合并）
//   - 真实锚杆报告风格：横纵合并混用
//   - 签名稳定性 + 格式约束 + 与 Parse 一致

using CivCore.Doc.Template;

namespace civ_doc.Tests;

public class TemplateParserTests : IDisposable
{
    private readonly TempDocx _tmp = new();
    public void Dispose() { _tmp.Dispose(); GC.SuppressFinalize(this); }

    // ── 错误路径 ────────────────────────────────────────────

    [Fact]
    public void Parse_无文件_抛带路径的异常()
    {
        var ex = Assert.Throws<TemplateParseException>(() =>
            TemplateParser.Parse(Path.Combine(_tmp.Dir, "does_not_exist.docx")));
        Assert.Contains("不存在", ex.Message);
    }

    [Fact]
    public void Parse_缺锚点段落_抛异常带提示()
    {
        var path = _tmp.Write("no_anchor.docx", anchorText: null, b =>
            b.Row(new CellSpec("A1"), new CellSpec("B1")));
        var ex = Assert.Throws<TemplateParseException>(() => TemplateParser.Parse(path));
        Assert.Contains("锚点", ex.Message);
        Assert.Contains(TemplateParser.AnchorMarker, ex.Message);
    }

    [Fact]
    public void Parse_锚点后无表_抛异常()
    {
        var path = _tmp.WriteAnchorOnly("anchor_only.docx", TemplateParser.AnchorMarker);
        var ex = Assert.Throws<TemplateParseException>(() => TemplateParser.Parse(path));
        Assert.Contains("未找到表格", ex.Message);
    }

    // ── 简单 3×3 ────────────────────────────────────────────

    [Fact]
    public void Parse_简单3x3_所有格全部展开()
    {
        var path = _tmp.Write("simple_3x3.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("A1"), new CellSpec("B1"), new CellSpec("C1"))
            .Row(new CellSpec("A2"), new CellSpec("B2"), new CellSpec("C2"))
            .Row(new CellSpec("A3"), new CellSpec("B3"), new CellSpec("C3")));

        var t = TemplateParser.Parse(path);

        Assert.Equal(3, t.RowCount);
        Assert.Equal(3, t.ColCount);
        Assert.Equal("A1", t.Rows[0][0].Text);
        Assert.Equal("B2", t.Rows[1][1].Text);
        Assert.Equal("C3", t.Rows[2][2].Text);
        Assert.False(t.IsHidden(0, 0));
        Assert.All(t.Rows.SelectMany(r => r.Values),
            cell => Assert.Equal((1, 1), (cell.RowSpan, cell.ColSpan)));
    }

    // ── 横向合并（gridSpan） ────────────────────────────────

    [Fact]
    public void Parse_横向合并_主格colSpan正确_覆盖格hidden()
    {
        var path = _tmp.Write("hmerge.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("标题", GridSpan: 3, Bold: true))
            .Row(new CellSpec("A2"), new CellSpec("B2"), new CellSpec("C2")));

        var t = TemplateParser.Parse(path);

        Assert.Equal(2, t.RowCount);
        Assert.Equal(3, t.ColCount);
        Assert.Equal("标题", t.Rows[0][0].Text);
        Assert.Equal(3, t.Rows[0][0].ColSpan);
        Assert.Equal(1, t.Rows[0][0].RowSpan);
        Assert.True(t.Rows[0][0].Bold);
        Assert.True(t.IsHidden(0, 1));
        Assert.True(t.IsHidden(0, 2));
        Assert.Equal("B2", t.Rows[1][1].Text);
    }

    // ── 纵向合并（vMerge） ──────────────────────────────────

    [Fact]
    public void Parse_纵向合并_主格rowSpan正确_覆盖格hidden()
    {
        var path = _tmp.Write("vmerge.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("批次", VMerge: VMergeMode.Restart), new CellSpec("B1"), new CellSpec("C1"))
            .Row(new CellSpec("",     VMerge: VMergeMode.Continue), new CellSpec("B2"), new CellSpec("C2"))
            .Row(new CellSpec("",     VMerge: VMergeMode.Continue), new CellSpec("B3"), new CellSpec("C3")));

        var t = TemplateParser.Parse(path);

        Assert.Equal(3, t.RowCount);
        Assert.Equal(3, t.ColCount);
        Assert.Equal("批次", t.Rows[0][0].Text);
        Assert.Equal(3, t.Rows[0][0].RowSpan);
        Assert.Equal(1, t.Rows[0][0].ColSpan);
        Assert.True(t.IsHidden(1, 0));
        Assert.True(t.IsHidden(2, 0));
        Assert.False(t.IsHidden(1, 1));
        Assert.Equal("B3", t.Rows[2][1].Text);
    }

    // ── 混合：锚杆报告风格 ──────────────────────────────────

    [Fact]
    public void Parse_锚杆报告风_横纵合并混用_全部解析正确()
    {
        // 行 0: [委托方信息（跨 4 列）]
        // 行 1: [客户][值][日期][值]
        // 行 2: [锚杆编号(跨2行)][0.1Nt][0.4Nt][0.7Nt]
        // 行 3: [继续              ][1.45][1.82][2.15]
        var path = _tmp.Write("anchor_report.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("委托方信息", GridSpan: 4, Bold: true))
            .Row(new CellSpec("客户"), new CellSpec("ABC 集团"), new CellSpec("日期"), new CellSpec("2026-05-25"))
            .Row(new CellSpec("锚杆编号", VMerge: VMergeMode.Restart), new CellSpec("0.1Nt"), new CellSpec("0.4Nt"), new CellSpec("0.7Nt"))
            .Row(new CellSpec("",          VMerge: VMergeMode.Continue), new CellSpec("1.45"), new CellSpec("1.82"), new CellSpec("2.15")));

        var t = TemplateParser.Parse(path);

        Assert.Equal(4, t.RowCount);
        Assert.Equal(4, t.ColCount);

        Assert.Equal("委托方信息", t.Rows[0][0].Text);
        Assert.Equal(4, t.Rows[0][0].ColSpan);
        Assert.True(t.IsHidden(0, 1));
        Assert.True(t.IsHidden(0, 3));

        Assert.Equal("锚杆编号", t.Rows[2][0].Text);
        Assert.Equal(2, t.Rows[2][0].RowSpan);
        Assert.Equal(1, t.Rows[2][0].ColSpan);
        Assert.True(t.IsHidden(3, 0));

        Assert.Equal("1.82", t.Rows[3][2].Text);
    }

    // ── 签名 ────────────────────────────────────────────────

    [Fact]
    public void ComputeSignature_相同表_签名相同()
    {
        Action<DocxTableBuilder> sameTable = b => b
            .Row(new CellSpec("A1"), new CellSpec("B1"))
            .Row(new CellSpec("A2"), new CellSpec("B2"));

        var p1 = _tmp.Write("sig1.docx", TemplateParser.AnchorMarker, sameTable);
        var p2 = _tmp.Write("sig2.docx", TemplateParser.AnchorMarker, sameTable);

        Assert.Equal(TemplateParser.ComputeSignature(p1), TemplateParser.ComputeSignature(p2));
    }

    [Fact]
    public void ComputeSignature_改了表内容_签名变化()
    {
        var p1 = _tmp.Write("sig_a.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("A1"), new CellSpec("B1")));
        var p2 = _tmp.Write("sig_b.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("A1"), new CellSpec("CHANGED")));

        Assert.NotEqual(TemplateParser.ComputeSignature(p1), TemplateParser.ComputeSignature(p2));
    }

    [Fact]
    public void ComputeSignature_格式严格符合_rows_cols_hash_6位hex()
    {
        var path = _tmp.Write("sig_format.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("A1"), new CellSpec("B1"), new CellSpec("C1"))
            .Row(new CellSpec("A2"), new CellSpec("B2"), new CellSpec("C2")));
        var sig = TemplateParser.ComputeSignature(path);

        Assert.StartsWith("rows:2_cols:3_hash:", sig);
        var hashPart = sig["rows:2_cols:3_hash:".Length..];
        Assert.Equal(6, hashPart.Length);
        Assert.All(hashPart, ch => Assert.Contains(ch, "0123456789ABCDEF"));
    }

    [Fact]
    public void Parse_的TableSignature_与ComputeSignature一致()
    {
        var path = _tmp.Write("sig_consistency.docx", TemplateParser.AnchorMarker, b => b
            .Row(new CellSpec("X"), new CellSpec("Y")));
        var parsed = TemplateParser.Parse(path);
        var direct = TemplateParser.ComputeSignature(path);
        Assert.Equal(direct, parsed.TableSignature);
    }
}
