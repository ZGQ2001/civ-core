// 回收站：发送 + 5 分钟内撤销还原。
//
// 与 src/civ_core/api/handlers/files.py 的 delete/undo_delete 同：
//   - delete 走 Microsoft.VisualBasic.FileIO.FileSystem（.NET 标准 API，无 P/Invoke）
//   - undo 调 Shell.Application COM（dynamic）NameSpace(10) = 回收站；
//     倒序找最近一项匹配 Name + 原始目录，调 "undelete" verb 还原
//   - _undoStack 是进程内 5 分钟窗口；UI 关掉重开就丢，跟 Python 端一致

using System.Runtime.Versioning;
using Microsoft.VisualBasic.FileIO;
using FileSystem = Microsoft.VisualBasic.FileIO.FileSystem;

namespace CivCore.Doc.Files;

[SupportedOSPlatform("windows")]
public static class RecycleBin
{
    private record UndoItem(string OriginalPath, string Name, DateTime DeletedAtUtc);

    private static readonly object Sync = new();
    private static readonly List<UndoItem> UndoStack = new();
    private static readonly TimeSpan UndoWindow = TimeSpan.FromMinutes(5);

    /// <summary>发到回收站；记录原始路径以支持 5 分钟内撤销。</summary>
    public static void SendToTrash(string path)
    {
        if (!File.Exists(path) && !Directory.Exists(path))
            throw new FileNotFoundException($"不存在：{path}");

        var name = Path.GetFileName(path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));

        if (Directory.Exists(path))
            FileSystem.DeleteDirectory(path, UIOption.OnlyErrorDialogs, RecycleOption.SendToRecycleBin);
        else
            FileSystem.DeleteFile(path, UIOption.OnlyErrorDialogs, RecycleOption.SendToRecycleBin);

        lock (Sync)
            UndoStack.Add(new UndoItem(path, name, DateTime.UtcNow));
    }

    /// <summary>
    /// 从回收站还原最近一次删除；超过 5 分钟或栈空 → ArgumentException。
    /// 原位置被占用 → InvalidOperationException（项目塞回栈以便再试）。
    /// 找不到匹配项 → FileNotFoundException。
    /// </summary>
    public static (string RestoredPath, string Parent) UndoDelete()
    {
        UndoItem item;
        lock (Sync)
        {
            if (UndoStack.Count == 0)
                throw new ArgumentException("没有可撤销的删除操作");
            item = UndoStack[^1];
            UndoStack.RemoveAt(UndoStack.Count - 1);
        }

        if (DateTime.UtcNow - item.DeletedAtUtc > UndoWindow)
        {
            lock (Sync) UndoStack.Clear();
            throw new ArgumentException("超过 5 分钟的删除不支持在 App 内撤销，请前往系统回收站手动还原。");
        }

        if (File.Exists(item.OriginalPath) || Directory.Exists(item.OriginalPath))
        {
            // 原位置被占用 → 撤销失败，塞回去让用户改名后再试
            lock (Sync) UndoStack.Add(item);
            throw new InvalidOperationException($"无法还原：目标位置已有同名文件 {item.Name}");
        }

        var origDir = Path.GetDirectoryName(item.OriginalPath) ?? "";
        if (!ShellRecycleBin.TryRestore(item.Name, origDir))
            throw new FileNotFoundException("在回收站中未找到匹配的文件，可能已被彻底删除。");

        return (item.OriginalPath, origDir);
    }

    /// <summary>测试用：清空 undo 栈。</summary>
    public static void ResetUndoStack()
    {
        lock (Sync) UndoStack.Clear();
    }
}
