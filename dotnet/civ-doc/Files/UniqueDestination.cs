// 同名冲突 → 追加 (2)/(3)/...，跟 Windows 资源管理器一致。
// 与 src/civ_core/api/handlers/files.py: _unique_dst 对齐。

namespace CivCore.Doc.Files;

public static class UniqueDestination
{
    public static string Resolve(string parent, string name)
    {
        var candidate = Path.Combine(parent, name);
        if (!File.Exists(candidate) && !Directory.Exists(candidate))
            return candidate;

        var dotIdx = name.LastIndexOf('.');
        string stem;
        string ext;
        if (dotIdx <= 0)
        {
            stem = name;
            ext = string.Empty;
        }
        else
        {
            stem = name[..dotIdx];
            ext = name[dotIdx..];
        }

        for (int i = 2; i < 1000; i++)
        {
            candidate = Path.Combine(parent, $"{stem} ({i}){ext}");
            if (!File.Exists(candidate) && !Directory.Exists(candidate))
                return candidate;
        }
        throw new IOException($"无法生成不冲突的名字（已尝试 1000 次）：{Path.Combine(parent, name)}");
    }
}
