// 原子文件写入：先写临时文件，成功后 File.Move 替换目标。
// 断电/崩溃只丢临时文件，原文件完好。与 Python atomic_writer 同设计。

namespace CivCore.Doc.Server;

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
