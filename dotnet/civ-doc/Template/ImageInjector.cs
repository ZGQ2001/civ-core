// OpenXML 图片注入 helper —— 把磁盘上的 PNG 嵌入到 Word docx 的指定段落里。
//
// 设计要点：
//   - 只支持 PNG（plot_curves 输出 PNG）。其他格式 → 抛 ImageInjectionException。
//   - 自动读 PNG 头部拿原始 width/height，按比例缩放到固定显示宽度（默认 14cm，
//     接近 A4 报告常见图宽），高度按原宽高比算 —— 不会变形。
//   - 一张图调一次 mainPart.AddImagePart，每次都是新的 rId，多张图互不影响。
//
// 关于 EMU（English Metric Unit）：
//   - 914400 EMU = 1 inch；360000 EMU = 1 cm
//   - OpenXML 所有尺寸都用 EMU；px → EMU 要除 DPI（PNG 默认 96 dpi）
//   - 我们直接用 cm 做单位，避开 DPI 假设

using System.Buffers.Binary;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;

namespace CivCore.Doc.Template;

public class ImageInjectionException : Exception
{
    public ImageInjectionException(string msg) : base(msg) { }
    public ImageInjectionException(string msg, Exception inner) : base(msg, inner) { }
}

public static class ImageInjector
{
    /// <summary>1 cm = 360000 EMU。</summary>
    private const long EmuPerCm = 360000;

    /// <summary>默认图片宽度 14cm —— 接近 A4 报告常见图宽，留侧边距。</summary>
    private const long DefaultWidthEmu = 14 * EmuPerCm;

    /// <summary>
    /// 读 PNG 文件 → 加到 mainPart → 返回一个含 Drawing 的 Run，
    /// 调用方负责把它放进段落（替换占位符 Run）。
    /// </summary>
    /// <param name="mainPart">docx 的 MainDocumentPart，图片资源挂在它上面。</param>
    /// <param name="imagePath">PNG 文件绝对路径。</param>
    /// <param name="widthEmu">显示宽度（EMU）；null = 用 DefaultWidthEmu。</param>
    /// <returns>一个 Run，含一个 Drawing element。</returns>
    public static Run CreateImageRun(
        MainDocumentPart mainPart,
        string imagePath,
        long? widthEmu = null)
    {
        if (!File.Exists(imagePath))
            throw new ImageInjectionException($"图片文件不存在：{imagePath}");

        // 当前只支持 PNG（plot_curves 输出 PNG）
        var ext = Path.GetExtension(imagePath).ToLowerInvariant();
        if (ext != ".png")
            throw new ImageInjectionException(
                $"暂只支持 PNG 格式图片（用户图片 {Path.GetFileName(imagePath)} 是 {ext}）—— " +
                $"若需 JPG/GIF 请先转换，或反馈给开发加 ImagePartType 分支");

        // 读原始尺寸（PNG 头部固定布局）
        var (origW, origH) = ReadPngSize(imagePath);
        if (origW <= 0 || origH <= 0)
            throw new ImageInjectionException(
                $"PNG 头部尺寸异常（{origW}x{origH}）：{imagePath}");

        // 加图片资源
        var imagePart = mainPart.AddImagePart(ImagePartType.Png);
        try
        {
            using var fs = File.OpenRead(imagePath);
            imagePart.FeedData(fs);
        }
        catch (Exception e)
        {
            throw new ImageInjectionException(
                $"读取图片字节失败 {imagePath}：{e.Message}", e);
        }
        var relId = mainPart.GetIdOfPart(imagePart);

        // 按宽度等比缩放
        long cx = widthEmu ?? DefaultWidthEmu;
        long cy = (long)Math.Round(cx * (double)origH / origW);

        var drawing = BuildImageDrawing(relId, Path.GetFileName(imagePath), cx, cy);
        return new Run(drawing);
    }

    /// <summary>读 PNG 头部 16~23 字节得 width/height（big-endian uint32）。</summary>
    private static (int Width, int Height) ReadPngSize(string path)
    {
        using var fs = File.OpenRead(path);
        // PNG 签名 8 字节 + IHDR length 4 字节 + IHDR type 4 字节 = 跳 16 字节
        Span<byte> buf = stackalloc byte[8];
        fs.Position = 16;
        if (fs.Read(buf) != 8)
            throw new ImageInjectionException(
                $"PNG 文件太短（无 IHDR）：{path}");
        int w = BinaryPrimitives.ReadInt32BigEndian(buf[..4]);
        int h = BinaryPrimitives.ReadInt32BigEndian(buf[4..8]);
        return (w, h);
    }

    /// <summary>
    /// 构造 OpenXML Drawing 树：Inline 模式（跟随段落字符流）。
    /// 结构按 ECMA-376 必填层级写够，不可省 — Word 解析时一个 child 缺都不开。
    /// </summary>
    private static Drawing BuildImageDrawing(string relId, string imageName, long cx, long cy)
    {
        // DocProperties.Id 需要全 docx 唯一（不能跟其他 drawing 撞）；
        // 这里用 Guid hashcode 取正数；Word 不要求严格连续，只要别重复。
        uint docPrId = (uint)(Guid.NewGuid().GetHashCode() & 0x7FFFFFFF);

        return new Drawing(
            new DW.Inline(
                new DW.Extent { Cx = cx, Cy = cy },
                new DW.EffectExtent
                {
                    LeftEdge = 0L,
                    TopEdge = 0L,
                    RightEdge = 0L,
                    BottomEdge = 0L,
                },
                new DW.DocProperties { Id = docPrId, Name = imageName },
                new DW.NonVisualGraphicFrameDrawingProperties(
                    new A.GraphicFrameLocks { NoChangeAspect = true }),
                new A.Graphic(
                    new A.GraphicData(
                        new PIC.Picture(
                            new PIC.NonVisualPictureProperties(
                                new PIC.NonVisualDrawingProperties
                                {
                                    Id = 0U,
                                    Name = imageName,
                                },
                                new PIC.NonVisualPictureDrawingProperties()),
                            new PIC.BlipFill(
                                new A.Blip
                                {
                                    Embed = relId,
                                    CompressionState = A.BlipCompressionValues.Print,
                                },
                                new A.Stretch(new A.FillRectangle())),
                            new PIC.ShapeProperties(
                                new A.Transform2D(
                                    new A.Offset { X = 0L, Y = 0L },
                                    new A.Extents { Cx = cx, Cy = cy }),
                                new A.PresetGeometry(new A.AdjustValueList())
                                {
                                    Preset = A.ShapeTypeValues.Rectangle,
                                }))
                    ) { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" })
            )
            {
                DistanceFromTop = 0U,
                DistanceFromBottom = 0U,
                DistanceFromLeft = 0U,
                DistanceFromRight = 0U,
            });
    }
}
