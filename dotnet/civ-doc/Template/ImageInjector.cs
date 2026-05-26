// OpenXML 图片注入 helper —— 把磁盘上的图片嵌入到 Word docx 的指定段落里。
//
// 支持格式：PNG / JPG / JPEG / SVG
//   · PNG / JPG：直接 AddImagePart(Png|Jpeg) + 标准 Blip。
//   · SVG：用 ImagePartType.Svg + OpenXML 的 SVGBlip 扩展（asvg:svgBlip），
//     额外塞一张 1x1 透明 PNG 作 raster 兜底——Office 2019+ 显 SVG，旧版退到 1x1 PNG。
//     这样既能享受矢量保真度，又不破坏旧版打开能力。
//
// 自动读图片头部拿原始 width/height，按比例缩放到固定显示宽度（默认 14cm，
// 接近 A4 报告常见图宽），高度按原宽高比算 —— 不会变形。
//
// 关于 EMU（English Metric Unit）：
//   - 914400 EMU = 1 inch；360000 EMU = 1 cm
//   - OpenXML 所有尺寸都用 EMU；我们直接用 cm 做单位，避开 DPI 假设

using System.Buffers.Binary;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;
using SVG = DocumentFormat.OpenXml.Office2019.Drawing.SVG;

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

    /// <summary>SVG 扩展元素的 OpenXML 标准 URI（Office 2016+ 定义）。</summary>
    private const string SvgExtensionUri = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}";

    /// <summary>1x1 透明 PNG 作 SVG 的 raster 兜底（旧版 Word 不识 asvg 扩展时显这个，几乎不可见）。
    /// 来源：常见 minimal PNG，base64 解码后是合法 PNG 文件。</summary>
    private static readonly byte[] _placeholderPng = Convert.FromBase64String(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==");

    /// <summary>
    /// 读图片文件 → 加到 mainPart → 返回一个含 Drawing 的 Run，
    /// 调用方负责把它放进段落（替换占位符 Run）。
    ///
    /// 按文件扩展名分派：
    ///   .png         → ImagePartType.Png  + 标准 Blip
    ///   .jpg / .jpeg → ImagePartType.Jpeg + 标准 Blip
    ///   .svg         → ImagePartType.Svg  + 1x1 PNG 兜底 + asvg:svgBlip 扩展
    /// 其他扩展名 → ImageInjectionException。
    /// </summary>
    /// <param name="mainPart">docx 的 MainDocumentPart，图片资源挂在它上面。</param>
    /// <param name="imagePath">图片文件绝对路径。</param>
    /// <param name="widthEmu">显示宽度（EMU）；null = 用 DefaultWidthEmu。</param>
    /// <returns>一个 Run，含一个 Drawing element。</returns>
    public static Run CreateImageRun(
        MainDocumentPart mainPart,
        string imagePath,
        long? widthEmu = null)
    {
        if (!File.Exists(imagePath))
            throw new ImageInjectionException($"图片文件不存在：{imagePath}");

        var ext = Path.GetExtension(imagePath).ToLowerInvariant();
        long cx = widthEmu ?? DefaultWidthEmu;
        var imageName = Path.GetFileName(imagePath);

        return ext switch
        {
            ".png" => CreateRasterRun(mainPart, imagePath, imageName, cx, ImagePartType.Png, ReadPngSize),
            ".jpg" or ".jpeg" => CreateRasterRun(mainPart, imagePath, imageName, cx, ImagePartType.Jpeg, ReadJpegSize),
            ".svg" => CreateSvgRun(mainPart, imagePath, imageName, cx),
            _ => throw new ImageInjectionException(
                $"不支持的图片格式 {ext}（用户图片 {imageName}）——目前支持 png / jpg / jpeg / svg"),
        };
    }

    // ─────────────────────────────────────────────────────────────
    // 通用 raster 嵌入（PNG / JPG）
    // ─────────────────────────────────────────────────────────────
    private static Run CreateRasterRun(
        MainDocumentPart mainPart,
        string imagePath,
        string imageName,
        long cx,
        PartTypeInfo partType,
        Func<string, (int Width, int Height)> sizeReader)
    {
        var (origW, origH) = sizeReader(imagePath);
        if (origW <= 0 || origH <= 0)
            throw new ImageInjectionException(
                $"图片头部尺寸异常（{origW}x{origH}）：{imagePath}");

        var imagePart = mainPart.AddImagePart(partType);
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

        long cy = (long)Math.Round(cx * (double)origH / origW);
        var blip = BuildBlip(relId, svgRelId: null);
        var drawing = BuildImageDrawing(blip, imageName, cx, cy);
        return new Run(drawing);
    }

    // ─────────────────────────────────────────────────────────────
    // SVG 嵌入（带 1x1 PNG 兜底 + asvg:svgBlip 扩展）
    // ─────────────────────────────────────────────────────────────
    private static Run CreateSvgRun(
        MainDocumentPart mainPart,
        string imagePath,
        string imageName,
        long cx)
    {
        // 1) 读 SVG 尺寸（只看宽高比；具体单位无所谓，最终按 cx 缩放）
        var (origW, origH) = ReadSvgSize(imagePath);
        if (origW <= 0 || origH <= 0)
            throw new ImageInjectionException(
                $"SVG 尺寸读取失败（{origW}x{origH}）：{imagePath}");

        // 2) 添 SVG ImagePart
        var svgPart = mainPart.AddImagePart(ImagePartType.Svg);
        try
        {
            using var fs = File.OpenRead(imagePath);
            svgPart.FeedData(fs);
        }
        catch (Exception e)
        {
            throw new ImageInjectionException(
                $"读取 SVG 字节失败 {imagePath}：{e.Message}", e);
        }
        var svgRelId = mainPart.GetIdOfPart(svgPart);

        // 3) 添 1x1 PNG 兜底（旧版 Word 显这个；现代版会被 asvg:svgBlip 覆盖）
        var pngPart = mainPart.AddImagePart(ImagePartType.Png);
        using (var ms = new MemoryStream(_placeholderPng))
        {
            pngPart.FeedData(ms);
        }
        var pngRelId = mainPart.GetIdOfPart(pngPart);

        // 4) 构 blip：主引用 PNG，扩展引用 SVG
        long cy = (long)Math.Round(cx * origH / origW);
        var blip = BuildBlip(pngRelId, svgRelId);
        var drawing = BuildImageDrawing(blip, imageName, cx, cy);
        return new Run(drawing);
    }

    // ─────────────────────────────────────────────────────────────
    // 尺寸读取
    // ─────────────────────────────────────────────────────────────

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

    /// <summary>读 JPEG SOF 段拿 width/height。
    /// JPEG 结构：SOI(0xFFD8) → 若干段 [0xFFxx + length(2) + data]，SOF(0xC0~0xCF 排除 C4/C8/CC) 段含尺寸。
    /// SOF 数据布局：length(2) + precision(1) + height(2) + width(2) + ...
    /// </summary>
    private static (int Width, int Height) ReadJpegSize(string path)
    {
        using var fs = File.OpenRead(path);
        // SOI
        Span<byte> two = stackalloc byte[2];
        if (fs.Read(two) != 2 || two[0] != 0xFF || two[1] != 0xD8)
            throw new ImageInjectionException($"非 JPEG 文件（缺 SOI 0xFFD8）：{path}");

        while (fs.Position < fs.Length)
        {
            // 找下一个 marker：连续 0xFF 是填充，需跳过到一个非 0xFF 非 0x00 的字节
            int b = fs.ReadByte();
            if (b == -1) break;
            if (b != 0xFF) continue;

            // 吞掉连续 0xFF 填充
            while (b == 0xFF)
            {
                b = fs.ReadByte();
                if (b == -1) break;
            }
            if (b == -1 || b == 0x00) continue; // 0x00 是 stuffing，不是 marker

            byte marker = (byte)b;

            // SOF markers: 0xC0~0xCF，排除 0xC4(DHT) / 0xC8(JPG) / 0xCC(DAC)
            if (marker >= 0xC0 && marker <= 0xCF
                && marker != 0xC4 && marker != 0xC8 && marker != 0xCC)
            {
                Span<byte> sof = stackalloc byte[7];
                if (fs.Read(sof) != 7)
                    throw new ImageInjectionException($"JPEG SOF 段截断：{path}");
                int height = (sof[3] << 8) | sof[4];
                int width = (sof[5] << 8) | sof[6];
                return (width, height);
            }

            // EOI(0xD9) / SOS(0xDA)：图像数据开始，没拿到 SOF 算异常
            if (marker == 0xD9 || marker == 0xDA) break;

            // 其他段：跳过 length 指定的字节
            if (fs.Read(two) != 2)
                throw new ImageInjectionException($"JPEG 段长度读取失败：{path}");
            int segLen = (two[0] << 8) | two[1];
            if (segLen < 2) break;
            fs.Position += segLen - 2;
        }

        throw new ImageInjectionException($"JPEG 没找到 SOF 段（width/height 未知）：{path}");
    }

    /// <summary>读 SVG 根元素的 width/height 属性；缺则 fallback 到 viewBox。
    /// 单位（pt/px/cm/in/mm）一并去掉——只取数值比例，最终按 cx 等比缩放。
    /// 都缺时默认 800x600（4:3）。</summary>
    private static (double Width, double Height) ReadSvgSize(string path)
    {
        XDocument doc;
        try
        {
            doc = XDocument.Load(path);
        }
        catch (Exception e)
        {
            throw new ImageInjectionException($"SVG 解析失败 {path}：{e.Message}", e);
        }

        var root = doc.Root;
        if (root == null || root.Name.LocalName != "svg")
            throw new ImageInjectionException($"SVG 根元素不是 <svg>：{path}");

        var w = ParseSvgLength(root.Attribute("width")?.Value);
        var h = ParseSvgLength(root.Attribute("height")?.Value);
        if (w > 0 && h > 0) return (w, h);

        var viewBox = root.Attribute("viewBox")?.Value;
        if (!string.IsNullOrWhiteSpace(viewBox))
        {
            var parts = viewBox.Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 4
                && double.TryParse(parts[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var vw)
                && double.TryParse(parts[3], NumberStyles.Float, CultureInfo.InvariantCulture, out var vh)
                && vw > 0 && vh > 0)
                return (vw, vh);
        }

        return (800, 600); // 兜底 4:3
    }

    private static double ParseSvgLength(string? s)
    {
        if (string.IsNullOrWhiteSpace(s)) return 0;
        // 抓开头的数字（允许小数 + 负号；负数算异常但能被上面 >0 拦掉）
        var m = Regex.Match(s, @"^\s*(-?[\d.]+)");
        if (m.Success
            && double.TryParse(m.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var v))
            return v;
        return 0;
    }

    // ─────────────────────────────────────────────────────────────
    // OpenXML Drawing 构造
    // ─────────────────────────────────────────────────────────────

    /// <summary>构 a:blip。svgRelId 非 null 时挂 asvg:svgBlip 扩展元素。</summary>
    private static A.Blip BuildBlip(string rasterRelId, string? svgRelId)
    {
        var blip = new A.Blip
        {
            Embed = rasterRelId,
            CompressionState = A.BlipCompressionValues.Print,
        };
        if (svgRelId != null)
        {
            var ext = new A.BlipExtension { Uri = SvgExtensionUri };
            ext.AppendChild(new SVG.SVGBlip { Embed = svgRelId });
            blip.AppendChild(new A.BlipExtensionList(ext));
        }
        return blip;
    }

    /// <summary>
    /// 构造 OpenXML Drawing 树：Inline 模式（跟随段落字符流）。
    /// 结构按 ECMA-376 必填层级写够，不可省 — Word 解析时一个 child 缺都不开。
    /// </summary>
    private static Drawing BuildImageDrawing(A.Blip blip, string imageName, long cx, long cy)
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
                                blip,
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
