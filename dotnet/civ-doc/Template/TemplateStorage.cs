// 模板磁盘存储 —— 跟 TemplateConfig 解耦的薄文件系统层。
//
// 存储布局（每个模板一个目录，按名字隔离）：
//   ~/.civ-core/templates/
//   └── <name>/
//       ├── source.docx     原始 Word 副本（保存时拷贝进来；生成报告时基于此 docx 填值）
//       └── config.json     TemplateConfig
//
// 名字隔离：禁止 / \ : * ? " < > | 等文件系统非法字符；用户输入的名字直接当目录名。
//
// 原子写：跟 Server/AtomicFile.cs 风格一致 —— 写 .tmp 再 Move，防意外关机半写。

using CivCore.Doc.Server;

namespace CivCore.Doc.Template;

public static class TemplateStorage
{
    public const string SourceDocxName = "source.docx";
    public const string ConfigJsonName = "config.json";

    /// <summary>模板根目录 —— 默认 ~/.civ-core/templates/，测试可注入。</summary>
    public static string GetRoot()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return Path.Combine(home, ".civ-core", "templates");
    }

    /// <summary>列出所有已保存模板的名字（按字母序，目录形式存在的才算）。</summary>
    public static List<string> ListNames(string? rootOverride = null)
    {
        var root = rootOverride ?? GetRoot();
        if (!Directory.Exists(root)) return new();
        return Directory.EnumerateDirectories(root)
            .Select(Path.GetFileName)
            .Where(n => !string.IsNullOrEmpty(n))
            .Select(n => n!)
            .OrderBy(n => n, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    /// <summary>
    /// 保存模板：把 sourceDocxPath 拷贝到模板目录 + 写 config.json（原子）。
    /// 名字已存在则覆盖 docx + 覆盖 config。
    /// </summary>
    public static void Save(string name, string sourceDocxPath, TemplateConfig config, string? rootOverride = null)
    {
        ValidateName(name);
        if (!File.Exists(sourceDocxPath))
            throw new TemplateStorageException($"原始 Word 文件不存在：{sourceDocxPath}");

        var dir = GetTemplateDir(name, rootOverride);
        Directory.CreateDirectory(dir);

        var docxDest = Path.Combine(dir, SourceDocxName);
        File.Copy(sourceDocxPath, docxDest, overwrite: true);

        var configPath = Path.Combine(dir, ConfigJsonName);
        AtomicFile.WriteAllText(configPath, config.ToJson());
    }

    /// <summary>加载模板：读 config.json + 返回 source.docx 绝对路径。</summary>
    public static (TemplateConfig Config, string SourceDocxPath) Load(string name, string? rootOverride = null)
    {
        ValidateName(name);
        var dir = GetTemplateDir(name, rootOverride);
        if (!Directory.Exists(dir))
            throw new TemplateStorageException($"模板 {name} 不存在");

        var configPath = Path.Combine(dir, ConfigJsonName);
        if (!File.Exists(configPath))
            throw new TemplateStorageException($"模板 {name} 缺 config.json");
        var docxPath = Path.Combine(dir, SourceDocxName);
        if (!File.Exists(docxPath))
            throw new TemplateStorageException($"模板 {name} 缺 source.docx");

        return (TemplateConfig.FromJson(File.ReadAllText(configPath)), docxPath);
    }

    /// <summary>删除模板（整个目录）。不存在直接返回 false（幂等）。</summary>
    public static bool Delete(string name, string? rootOverride = null)
    {
        ValidateName(name);
        var dir = GetTemplateDir(name, rootOverride);
        if (!Directory.Exists(dir)) return false;
        Directory.Delete(dir, recursive: true);
        return true;
    }

    /// <summary>测试用：拼模板目录路径但不创建。</summary>
    public static string GetTemplateDir(string name, string? rootOverride = null)
    {
        var root = rootOverride ?? GetRoot();
        return Path.Combine(root, name);
    }

    // ── 内部 ────────────────────────────────────────────────

    private static readonly char[] InvalidNameChars =
        ['/', '\\', ':', '*', '?', '"', '<', '>', '|'];

    private static void ValidateName(string name)
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new TemplateStorageException("模板名不可为空");
        if (name.IndexOfAny(InvalidNameChars) >= 0)
            throw new TemplateStorageException($"模板名 {name} 含非法字符（不能包含 / \\ : * ? \" < > |）");
        if (name.StartsWith('.'))
            throw new TemplateStorageException("模板名不能以 . 开头");
    }
}

public class TemplateStorageException : Exception
{
    public TemplateStorageException(string msg) : base(msg) { }
}
