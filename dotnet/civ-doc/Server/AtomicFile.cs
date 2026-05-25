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
        => WriteAtomically(targetPath, tmp => wb.SaveAs(tmp));

    /// <summary>
    /// 原子写文本（UTF-8 无 BOM）。给 JSON 配置之类小文件用。
    /// </summary>
    public static void WriteAllText(string targetPath, string contents)
        => WriteAtomically(targetPath, tmp => File.WriteAllText(tmp, contents, new System.Text.UTF8Encoding(false)));

    private static void WriteAtomically(string targetPath, Action<string> writeToTmp)
    {
        var dir = Path.GetDirectoryName(targetPath) ?? ".";
        if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);

        // 保留原扩展名 —— ClosedXML.SaveAs / OpenXML 等会按扩展名校验，".tmp"
        // 会被拒。原来的命名是 ".{name}.{Guid}.tmp" 直接卡死 SaveWorkbook。
        var baseName = Path.GetFileNameWithoutExtension(targetPath);
        var ext = Path.GetExtension(targetPath); // 含 "." 前缀，如 ".xlsx"
        var tmpPath = Path.Combine(dir, $".{baseName}.{Guid.NewGuid():N}{ext}");

        try
        {
            writeToTmp(tmpPath);
            File.Move(tmpPath, targetPath, overwrite: true);
        }
        catch
        {
            try { File.Delete(tmpPath); } catch { }
            throw;
        }
    }
}
