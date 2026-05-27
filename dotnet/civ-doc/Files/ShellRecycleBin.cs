// 回收站还原：用 Shell.Application COM 调 "undelete" verb。
//
// Windows 没有公开 API 让程序还原回收站项，只能走 Shell.Application（同 Explorer 内部用的）。
// 与 src/civ_core/api/handlers/files.py: undo_delete 内的逻辑对齐：
//   1. 取 NameSpace(10) = 回收站
//   2. 倒序遍历 Items（找最近删除的匹配项）
//   3. 比对 Name + GetDetailsOf(item, 1) ＝ 原始目录（剥 LRM/RLM unicode 控制字符）
//   4. 调 InvokeVerb("undelete")；失败则按动词名查"还原"/"Restore"

using System.Diagnostics.CodeAnalysis;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace CivCore.Doc.Files;

[SupportedOSPlatform("windows")]
internal static class ShellRecycleBin
{
    private const int SsfBitbucket = 10;
    private const int DetailIndexOriginalLocation = 1;

    /// <summary>
    /// 倒序查找 Name + 原始目录都匹配的回收站项，调 undelete verb。
    /// 找到并还原成功返 true；找不到返 false。COM 调用失败抛 COMException。
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "dynamic COM interop")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "dynamic COM interop")]
    public static bool TryRestore(string origName, string origDir)
    {
        var shellType = Type.GetTypeFromProgID("Shell.Application")
            ?? throw new InvalidOperationException("无法实例化 Shell.Application COM");
        dynamic shell = Activator.CreateInstance(shellType)!;
        try
        {
            dynamic? bin = shell.NameSpace(SsfBitbucket);
            if (bin == null) return false;

            dynamic items = bin.Items();
            int count = items.Count;
            for (int i = count - 1; i >= 0; i--)
            {
                dynamic item = items.Item(i);
                string name = item.Name;
                if (name != origName) continue;

                string detail = bin.GetDetailsOf(item, DetailIndexOriginalLocation);
                detail = detail.Replace("‎", string.Empty).Replace("‏", string.Empty);
                if (!string.Equals(detail, origDir, StringComparison.OrdinalIgnoreCase))
                    continue;

                // 首选直接调 undelete verb；失败回退到按名字查动词
                try
                {
                    item.InvokeVerb("undelete");
                    return true;
                }
                catch (Exception)
                {
                    dynamic verbs = item.Verbs();
                    int vc = verbs.Count;
                    for (int v = 0; v < vc; v++)
                    {
                        dynamic verb = verbs.Item(v);
                        string vname = verb.Name;
                        if (vname.Contains("还原") || vname.Contains("Restore"))
                        {
                            verb.DoIt();
                            return true;
                        }
                    }
                }
            }
            return false;
        }
        finally
        {
            if (shell is not null && Marshal.IsComObject(shell))
                Marshal.FinalReleaseComObject(shell);
        }
    }
}
