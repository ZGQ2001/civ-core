// docx 测试 fixture 构造工具 —— 给 Template/Report 一系列测试复用。
//
// 不检入 binary docx，全部用 OpenXML SDK 程序化构造：fixture 配置精确可控，
// 测试自包含，git 仓库不囤二进制。
//
// 用法：
//   using var tmp = new TempDocx();
//   var path = tmp.Write("foo.docx", anchorText: "[[数据绑定区]]", b => b
//       .Row(new CellSpec("A1"), new CellSpec("B1", GridSpan: 2))
//       .Row(new CellSpec("A2", VMerge: VMergeMode.Restart), ...));

using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace civ_doc.Tests;

/// <summary>临时目录持有者：Dispose 时清空。整组 fixture 共用一个目录。</summary>
public sealed class TempDocx : IDisposable
{
    public string Dir { get; }
    public TempDocx()
    {
        Dir = Path.Combine(Path.GetTempPath(), "civ_core_docx_fixture_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Dir);
    }

    /// <summary>写一份 docx：先写 anchorText 段落（可选），再写一张 builder 描述的表。</summary>
    public string Write(string fileName, string? anchorText, Action<DocxTableBuilder> build)
    {
        var path = Path.Combine(Dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body());
        var body = mainPart.Document.Body!;

        if (anchorText != null)
            body.AppendChild(new Paragraph(new Run(new Text(anchorText))));

        var tb = new DocxTableBuilder();
        build(tb);
        body.AppendChild(tb.Build());

        return path;
    }

    /// <summary>只写锚点段落、不写表 —— 测「缺表」场景用。</summary>
    public string WriteAnchorOnly(string fileName, string anchorText)
    {
        var path = Path.Combine(Dir, fileName);
        using var doc = WordprocessingDocument.Create(path, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body(
            new Paragraph(new Run(new Text(anchorText)))
        ));
        return path;
    }

    public void Dispose()
    {
        if (Directory.Exists(Dir)) Directory.Delete(Dir, true);
    }
}

/// <summary>流式构造 Word 表：链式 Row(...) 添加，Build() 出 Table 节点。</summary>
public class DocxTableBuilder
{
    private readonly List<List<CellSpec>> _rows = new();

    public DocxTableBuilder Row(params CellSpec[] cells)
    {
        _rows.Add(cells.ToList());
        return this;
    }

    public Table Build()
    {
        var table = new Table();
        foreach (var row in _rows)
        {
            var tr = new TableRow();
            foreach (var c in row) tr.AppendChild(c.ToCell());
            table.AppendChild(tr);
        }
        return table;
    }
}

/// <summary>单元格规约：内容 + 合并配置 + 加粗。</summary>
public record CellSpec(string Text, int GridSpan = 1, VMergeMode VMerge = VMergeMode.None, bool Bold = false)
{
    public TableCell ToCell()
    {
        var props = new TableCellProperties();
        if (GridSpan > 1) props.AppendChild(new GridSpan { Val = GridSpan });
        if (VMerge == VMergeMode.Restart)
            props.AppendChild(new VerticalMerge { Val = MergedCellValues.Restart });
        else if (VMerge == VMergeMode.Continue)
            props.AppendChild(new VerticalMerge()); // 无 val 默认 continue

        var runProps = new RunProperties();
        if (Bold) runProps.AppendChild(new Bold());
        var run = new Run(runProps, new Text(Text) { Space = SpaceProcessingModeValues.Preserve });
        return new TableCell(props, new Paragraph(run));
    }
}

public enum VMergeMode { None, Restart, Continue }
