// 文件 IO 安全工具：原子写入 + 大文件守卫。

namespace CivCore.Doc.Server;

public static class FileGuard
{
    private const long MaxExcelBytes = 50 * 1024 * 1024; // 50 MB

    /// <summary>
    /// 检查 Excel 文件大小，超过阈值抛友好提示。
    /// 土木检测 Excel 通常 &lt; 1MB；超过 50MB 几乎肯定是误传。
    /// </summary>
    public static void CheckExcelSize(string path)
    {
        var info = new FileInfo(path);
        if (info.Exists && info.Length > MaxExcelBytes)
            throw new ArgumentException(
                $"文件过大（{info.Length / 1024 / 1024} MB），请确认是否选错了文件");
    }
}

public static class AtomicFile
{
    /// <summary>
    /// 原子保存 ClosedXML workbook。写到同目录临时文件后原子替换目标。
    /// </summary>
    public static void SaveWorkbook(ClosedXML.Excel.XLWorkbook wb, string targetPath)
    {
        var dir = Path.GetDirectoryName(targetPath) ?? ".";
        if (!Directory.Exists(dir))
            Directory.CreateDirectory(dir);

        var fileName = Path.GetFileName(targetPath);
        var tmpPath = Path.Combine(dir, $".{fileName}.{Guid.NewGuid():N}.tmp");

        try
        {
            wb.SaveAs(tmpPath);
            File.Move(tmpPath, targetPath, overwrite: true);
        }
        catch
        {
            try { File.Delete(tmpPath); } catch { }
            throw;
        }
    }
}
