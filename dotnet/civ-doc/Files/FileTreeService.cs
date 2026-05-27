// 文件树服务：列目录 / 检查存在。
//
// 与 src/civ_core/api/handlers/files.py 同：
//   - 默认隐藏 . 开头文件（VSCode Explorer 默认行为）
//   - .civ-core 永远隐藏（即使 show_hidden=True）—— 应用专属目录不应污染业务视图
//   - 目录在前 + 自然排序（"file2" < "file10" < "file100"）
//   - 单条目的 size/mtime 读失败返 null，不影响整体

using System.Text.RegularExpressions;

namespace CivCore.Doc.Files;

public static class FileTreeService
{
    /// <summary>应用专属隐藏目录（show_hidden=True 也不显示）。</summary>
    private static readonly HashSet<string> AlwaysHidden = new(StringComparer.Ordinal)
    {
        ".civ-core",
    };

    public record Entry(string Name, string Path, bool IsDir, long? Size, double? Mtime);

    public static List<Entry> ListDir(string path, bool showHidden = false)
    {
        if (!Directory.Exists(path))
            throw new ArgumentException($"不是目录：{path}");

        var entries = new List<Entry>();
        foreach (var child in new DirectoryInfo(path).EnumerateFileSystemInfos())
        {
            var name = child.Name;
            if (AlwaysHidden.Contains(name)) continue;
            if (!showHidden && name.StartsWith('.')) continue;

            long? size = null;
            double? mtime = null;
            bool isDir = false;
            try
            {
                isDir = (child.Attributes & FileAttributes.Directory) == FileAttributes.Directory;
                if (!isDir && child is FileInfo fi)
                    size = fi.Length;
                mtime = ToUnixTime(child.LastWriteTimeUtc);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // stat 失败 → 留 null
            }
            entries.Add(new Entry(name, child.FullName, isDir, size, mtime));
        }

        // 目录在前 + 自然排序
        entries.Sort((a, b) =>
        {
            if (a.IsDir != b.IsDir) return a.IsDir ? -1 : 1;
            return NaturalCompare(a.Name, b.Name);
        });
        return entries;
    }

    public record ExistsResult(bool Exists, bool IsDir, bool IsFile);

    public static ExistsResult Exists(string path) => new(
        File.Exists(path) || Directory.Exists(path),
        Directory.Exists(path),
        File.Exists(path));

    /// <summary>
    /// 自然排序：数字段按数值比较，字母段按 invariant ignore case。
    /// 对齐 Python `[int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]`。
    /// </summary>
    public static int NaturalCompare(string a, string b)
    {
        var partsA = Tokenize(a);
        var partsB = Tokenize(b);
        int n = Math.Min(partsA.Count, partsB.Count);
        for (int i = 0; i < n; i++)
        {
            var (isNumA, numA, strA) = partsA[i];
            var (isNumB, numB, strB) = partsB[i];
            if (isNumA && isNumB)
            {
                int cmp = numA.CompareTo(numB);
                if (cmp != 0) return cmp;
            }
            else if (isNumA != isNumB)
            {
                // 数字段排在字母段前 (与 Python re.split 后 int vs lower str 直接比的行为吻合)
                return isNumA ? -1 : 1;
            }
            else
            {
                int cmp = string.Compare(strA, strB, StringComparison.InvariantCultureIgnoreCase);
                if (cmp != 0) return cmp;
            }
        }
        return partsA.Count.CompareTo(partsB.Count);
    }

    private static readonly Regex DigitsRx = new(@"(\d+)", RegexOptions.Compiled);

    private static List<(bool IsNum, long Num, string Str)> Tokenize(string s)
    {
        var parts = DigitsRx.Split(s);
        var result = new List<(bool, long, string)>();
        foreach (var p in parts)
        {
            if (p.Length == 0) continue;
            if (char.IsDigit(p[0]) && long.TryParse(p, out var n))
                result.Add((true, n, p));
            else
                result.Add((false, 0, p));
        }
        return result;
    }

    private static double ToUnixTime(DateTime utc) =>
        (utc - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
}
