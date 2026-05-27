// files.* RPC：文件树列举 + 文件元信息 + 增删改 + 复制移动 + 在系统打开。
//
// 与 src/civ_core/api/handlers/files.py 同协议：
//   files.list_dir(path, show_hidden=False) -> {entries: [...]}
//   files.exists(path) -> {exists, is_dir, is_file}
//   files.create_file(parent, name) -> {path}
//   files.create_folder(parent, name) -> {path}
//   files.rename(path, new_name) -> {path}
//   files.delete(path) -> {ok: true}                      （回收站 + 5 分钟内可 undo）
//   files.undo_delete() -> {restored_path, parent}
//   files.copy(src, dst_parent) -> {path}                 （同名追加 (2)/(3)）
//   files.move(src, dst_parent) -> {path}
//   files.reveal(path) -> {ok: true}                      （仅 Windows）

using System.Diagnostics;
using System.Runtime.Versioning;
using System.Text.Json;
using CivCore.Doc.Files;
using CivCore.Doc.Server;

namespace CivCore.Doc.Handlers;

public static class FilesHandlers
{
    public static void RegisterAll(Dispatcher d)
    {
        d.Register("files.list_dir", ListDir);
        d.Register("files.exists", Exists);
        d.Register("files.create_file", CreateFile);
        d.Register("files.create_folder", CreateFolder);
        d.Register("files.rename", Rename);
        if (OperatingSystem.IsWindows())
        {
            d.Register("files.delete", Delete);
            d.Register("files.undo_delete", UndoDelete);
        }
        d.Register("files.copy", Copy);
        d.Register("files.move", Move);
        d.Register("files.reveal", Reveal);
    }

    public static object ListDir(JsonElement? @params)
    {
        var path = RequireString(@params, "path");
        var showHidden = OptionalBool(@params, "show_hidden", false);
        var entries = FileTreeService.ListDir(path, showHidden);
        return new Dictionary<string, object?>
        {
            ["entries"] = entries.Select(e => new Dictionary<string, object?>
            {
                ["name"] = e.Name,
                ["path"] = e.Path,
                ["is_dir"] = e.IsDir,
                ["size"] = e.Size,
                ["mtime"] = e.Mtime,
            }).ToList(),
        };
    }

    public static object Exists(JsonElement? @params)
    {
        var path = RequireString(@params, "path");
        var r = FileTreeService.Exists(path);
        return new Dictionary<string, object?>
        {
            ["exists"] = r.Exists,
            ["is_dir"] = r.IsDir,
            ["is_file"] = r.IsFile,
        };
    }

    public static object CreateFile(JsonElement? @params)
    {
        var parent = RequireString(@params, "parent");
        var name = RequireString(@params, "name");
        NameValidator.Check(name);
        if (!Directory.Exists(parent))
            throw new ArgumentException($"父目录不存在：{parent}");
        var target = Path.Combine(parent, name);
        if (File.Exists(target) || Directory.Exists(target))
            throw new IOException($"已存在：{target}");
        File.Create(target).Dispose();
        return new Dictionary<string, object?> { ["path"] = target };
    }

    public static object CreateFolder(JsonElement? @params)
    {
        var parent = RequireString(@params, "parent");
        var name = RequireString(@params, "name");
        NameValidator.Check(name);
        if (!Directory.Exists(parent))
            throw new ArgumentException($"父目录不存在：{parent}");
        var target = Path.Combine(parent, name);
        if (File.Exists(target) || Directory.Exists(target))
            throw new IOException($"已存在：{target}");
        Directory.CreateDirectory(target);
        return new Dictionary<string, object?> { ["path"] = target };
    }

    public static object Rename(JsonElement? @params)
    {
        var path = RequireString(@params, "path");
        var newName = RequireString(@params, "new_name");
        NameValidator.Check(newName);
        if (!File.Exists(path) && !Directory.Exists(path))
            throw new FileNotFoundException($"不存在：{path}");

        var parent = Path.GetDirectoryName(path)
            ?? throw new ArgumentException($"无法解析父目录：{path}");
        var dst = Path.Combine(parent, newName);
        if (string.Equals(dst, path, StringComparison.Ordinal))
            return new Dictionary<string, object?> { ["path"] = path };
        if (File.Exists(dst) || Directory.Exists(dst))
            throw new IOException($"已存在：{dst}");

        if (Directory.Exists(path))
            Directory.Move(path, dst);
        else
            File.Move(path, dst);
        return new Dictionary<string, object?> { ["path"] = dst };
    }

    [SupportedOSPlatform("windows")]
    public static object Delete(JsonElement? @params)
    {
        var path = RequireString(@params, "path");
        RecycleBin.SendToTrash(path);
        return new Dictionary<string, object?> { ["ok"] = true };
    }

    [SupportedOSPlatform("windows")]
    public static object UndoDelete(JsonElement? @params)
    {
        var (restored, parent) = RecycleBin.UndoDelete();
        return new Dictionary<string, object?>
        {
            ["restored_path"] = restored,
            ["parent"] = parent,
        };
    }

    public static object Copy(JsonElement? @params)
    {
        var src = RequireString(@params, "src");
        var dstParent = RequireString(@params, "dst_parent");
        if (!File.Exists(src) && !Directory.Exists(src))
            throw new FileNotFoundException($"源不存在：{src}");
        if (!Directory.Exists(dstParent))
            throw new ArgumentException($"目标目录不存在：{dstParent}");

        var name = Path.GetFileName(src.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
        var target = UniqueDestination.Resolve(dstParent, name);

        if (Directory.Exists(src))
            CopyDirectoryRecursive(src, target);
        else
            File.Copy(src, target);
        return new Dictionary<string, object?> { ["path"] = target };
    }

    public static object Move(JsonElement? @params)
    {
        var src = RequireString(@params, "src");
        var dstParent = RequireString(@params, "dst_parent");
        if (!File.Exists(src) && !Directory.Exists(src))
            throw new FileNotFoundException($"源不存在：{src}");
        if (!Directory.Exists(dstParent))
            throw new ArgumentException($"目标目录不存在：{dstParent}");

        var srcParent = Path.GetDirectoryName(src.TrimEnd(
            Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)) ?? "";
        if (string.Equals(
                Path.GetFullPath(srcParent),
                Path.GetFullPath(dstParent),
                StringComparison.OrdinalIgnoreCase))
            return new Dictionary<string, object?> { ["path"] = src };

        var name = Path.GetFileName(src.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
        var target = UniqueDestination.Resolve(dstParent, name);

        if (Directory.Exists(src))
            Directory.Move(src, target);
        else
            File.Move(src, target);
        return new Dictionary<string, object?> { ["path"] = target };
    }

    public static object Reveal(JsonElement? @params)
    {
        var path = RequireString(@params, "path");
        if (!File.Exists(path) && !Directory.Exists(path))
            throw new FileNotFoundException($"不存在：{path}");
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("reveal 当前仅支持 Windows");
        RevealInExplorer(path);
        return new Dictionary<string, object?> { ["ok"] = true };
    }

    [SupportedOSPlatform("windows")]
    private static void RevealInExplorer(string path)
    {
        var normalized = Path.GetFullPath(path);
        // explorer.exe /select,"absolute path" — /select 后无空格，逗号分隔
        Process.Start(new ProcessStartInfo
        {
            FileName = "explorer.exe",
            Arguments = $"/select,\"{normalized}\"",
            UseShellExecute = false,
        });
    }

    private static void CopyDirectoryRecursive(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var dir in Directory.GetDirectories(src))
        {
            var name = Path.GetFileName(dir);
            CopyDirectoryRecursive(dir, Path.Combine(dst, name));
        }
        foreach (var file in Directory.GetFiles(src))
        {
            var name = Path.GetFileName(file);
            File.Copy(file, Path.Combine(dst, name));
        }
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

    private static bool OptionalBool(JsonElement? @params, string key, bool defaultValue)
    {
        if (@params is null || @params.Value.ValueKind != JsonValueKind.Object) return defaultValue;
        if (!@params.Value.TryGetProperty(key, out var el)) return defaultValue;
        return el.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => defaultValue,
        };
    }
}
