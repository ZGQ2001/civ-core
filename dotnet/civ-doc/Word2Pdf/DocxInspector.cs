// docx 体量检视：文件大小 + 段落数 + （可选）缓存页数。
//
// 与 src/civ_core/api/handlers/word2pdf.py: inspect 同：
//   - 段落数走 OpenXML SDK 数 Paragraph 元素（对齐 python-docx 的 len(doc.paragraphs)）
//   - 缓存页数读 docProps/app.xml 里 <Pages> 字段；Word 真正打开保存过才有，
//     纯生成的 docx 多半没有，缺失就只返段落数
//   - 单文件失败 → item 带 error 字段，不影响整体批量

using System.IO.Compression;
using System.Xml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Word2Pdf;

public static class DocxInspector
{
    public record Item(
        string Path,
        double? SizeKb,
        int? Paragraphs,
        int? Pages,
        string? Error);

    public static Item Inspect(string path)
    {
        if (!File.Exists(path))
            return new Item(path, null, null, null, $"文件不存在：{path}");

        double? sizeKb;
        try
        {
            sizeKb = Math.Round(new FileInfo(path).Length / 1024.0, 1);
        }
        catch (IOException e)
        {
            return new Item(path, null, null, null, $"读文件大小失败：{e.Message}");
        }

        int? paragraphs;
        try
        {
            using var doc = WordprocessingDocument.Open(path, false);
            var body = doc.MainDocumentPart?.Document?.Body;
            paragraphs = body?.Descendants<Paragraph>().Count() ?? 0;
        }
        catch (Exception e) when (e is IOException or InvalidOperationException
                                  or System.IO.FileFormatException
                                  or DocumentFormat.OpenXml.Packaging.OpenXmlPackageException)
        {
            return new Item(path, sizeKb, null, null,
                $"解析失败：{e.GetType().Name}: {e.Message}");
        }

        var pages = ReadCachedPages(path);
        return new Item(path, sizeKb, paragraphs, pages, null);
    }

    /// <summary>
    /// 从 docx 的 docProps/app.xml 读 <Pages>。Word 真正打开保存时会写这个字段；
    /// 纯生成（OpenXML SDK / python-docx）通常没有，返 null。
    /// </summary>
    private static int? ReadCachedPages(string path)
    {
        try
        {
            using var zip = ZipFile.OpenRead(path);
            var entry = zip.GetEntry("docProps/app.xml");
            if (entry == null) return null;

            using var stream = entry.Open();
            var xml = new XmlDocument();
            xml.Load(stream);
            // 遍历所有元素，找以 Pages 结尾的（绕过命名空间版本差异，跟 Python 端一致）
            foreach (XmlNode node in xml.SelectNodes("//*")!)
            {
                var localName = node.LocalName;
                if (localName == "Pages")
                {
                    var text = node.InnerText?.Trim();
                    if (!string.IsNullOrEmpty(text) && int.TryParse(text, out var n))
                        return n;
                }
            }
            return null;
        }
        catch (Exception ex) when (ex is IOException or InvalidDataException or XmlException)
        {
            return null;
        }
    }
}
