// Windows 文件名校验：非法字符 + 保留名 + 首尾空格。
// 与 src/civ_core/api/handlers/files.py: _check_name 对齐。

namespace CivCore.Doc.Files;

public static class NameValidator
{
    private static readonly HashSet<char> ForbiddenChars = new("<>:\"/\\|?*");

    private static readonly HashSet<string> ForbiddenNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    /// <summary>校验失败抛 ArgumentException，被 dispatcher 包成 -32602。</summary>
    public static void Check(string name)
    {
        if (string.IsNullOrEmpty(name) || string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("名称不能为空");
        if (name.Trim() != name)
            throw new ArgumentException("名称首尾不能含空格");
        foreach (var c in name)
            if (ForbiddenChars.Contains(c))
                throw new ArgumentException($"名称含非法字符 <>:\"/\\|?*：'{name}'");

        var stem = name.IndexOf('.') < 0 ? name : name[..name.IndexOf('.')];
        if (ForbiddenNames.Contains(stem))
            throw new ArgumentException($"Windows 保留名：'{name}'");
    }
}
