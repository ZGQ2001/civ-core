// workspace.* RPC handler：当前工作区路径的读/写/新建标准结构。
//
// 与 src/civ_core/api/handlers/workspace.py 同协议：
//   workspace.last() -> { path: string | null }
//   workspace.set(path) -> { ok: true, path: string }
//   workspace.clear() -> { ok: true }
//   workspace.create_standard(parent_dir, name) -> { ok: true, path: string }

using System.Text.Json;
using CivCore.Doc.Server;
using CivCore.Doc.Workspace;

namespace CivCore.Doc.Handlers;

public static class WorkspaceHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("workspace.last", Last);
        d.Register("workspace.set", Set);
        d.Register("workspace.clear", Clear);
        d.Register("workspace.create_standard", CreateStandard);
    }

    public static object Last(JsonElement? @params)
    {
        return new Dictionary<string, object?> { ["path"] = WorkspaceStore.GetLastWorkspace() };
    }

    public static object Set(JsonElement? @params)
    {
        var path = RequireString(@params, "path");
        if (!Directory.Exists(path))
            throw new ArgumentException($"工作区必须是已存在的目录：{path}");
        WorkspaceStore.SetLastWorkspace(path);
        return new Dictionary<string, object?> { ["ok"] = true, ["path"] = path };
    }

    public static object Clear(JsonElement? @params)
    {
        WorkspaceStore.ClearLastWorkspace();
        return new Dictionary<string, object?> { ["ok"] = true };
    }

    public static object CreateStandard(JsonElement? @params)
    {
        var parentDir = RequireString(@params, "parent_dir");
        var name = RequireString(@params, "name");
        if (!Directory.Exists(parentDir))
            throw new ArgumentException($"父目录不存在：{parentDir}");
        var trimmed = name.Trim();
        if (string.IsNullOrEmpty(trimmed) || trimmed.Contains('/') || trimmed.Contains('\\'))
            throw new ArgumentException($"项目名不合法：'{name}'");
        var root = Path.Combine(parentDir, trimmed);
        StandardScaffold.Create(root);
        return new Dictionary<string, object?> { ["ok"] = true, ["path"] = root };
    }

    private static string RequireString(JsonElement? @params, string key)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException($"缺少参数：{key}");
        if (!@params.Value.TryGetProperty(key, out var el) || el.ValueKind != JsonValueKind.String)
            throw new ArgumentException($"缺少参数：{key}");
        var s = el.GetString();
        if (string.IsNullOrEmpty(s))
            throw new ArgumentException($"参数 {key} 不能为空");
        return s;
    }
}
