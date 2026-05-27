// ~/.civ-core/workspace.json 读写。
//
// 与 src/civ_core/api/handlers/workspace.py 同：简单 JSON 文件跨进程读写，比 QSettings/注册表
// 调试可视。读失败（不存在/损坏 JSON）一律返回空 dict，由调用方决定如何处理。

using System.Text.Json;

namespace CivCore.Doc.Workspace;

public static class WorkspaceStore
{
    private const string LastWorkspaceKey = "last_workspace";

    /// <summary>
    /// 用户家目录。优先读 USERPROFILE（Windows）→ HOME（Unix），与 Python 的
    /// Path.expanduser() 在 Windows 上的行为对齐。env var 优先而非
    /// SpecialFolder.UserProfile，方便测试通过环境变量重定向。
    /// </summary>
    public static string HomeDir =>
        Environment.GetEnvironmentVariable("USERPROFILE")
            ?? Environment.GetEnvironmentVariable("HOME")
            ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);

    private static string StorePath =>
        Path.Combine(HomeDir, ".civ-core", "workspace.json");

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    /// <summary>读全量 store。文件不存在/损坏 → 空字典。</summary>
    public static Dictionary<string, string> Read()
    {
        if (!File.Exists(StorePath))
            return new Dictionary<string, string>();
        try
        {
            var text = File.ReadAllText(StorePath);
            return JsonSerializer.Deserialize<Dictionary<string, string>>(text)
                ?? new Dictionary<string, string>();
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            return new Dictionary<string, string>();
        }
    }

    /// <summary>写全量 store；父目录缺失会自动建。</summary>
    public static void Write(Dictionary<string, string> data)
    {
        var dir = Path.GetDirectoryName(StorePath);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);
        File.WriteAllText(StorePath, JsonSerializer.Serialize(data, JsonOpts));
    }

    /// <summary>返回上次工作区路径；不存在 / 路径已失效 → null。</summary>
    public static string? GetLastWorkspace()
    {
        var data = Read();
        if (!data.TryGetValue(LastWorkspaceKey, out var raw) || string.IsNullOrWhiteSpace(raw))
            return null;
        return Directory.Exists(raw) ? raw : null;
    }

    public static void SetLastWorkspace(string path)
    {
        var data = Read();
        data[LastWorkspaceKey] = path;
        Write(data);
    }

    public static void ClearLastWorkspace()
    {
        var data = Read();
        data.Remove(LastWorkspaceKey);
        Write(data);
    }
}
