namespace CivCore.Doc.Calc;

/// <summary>
/// Excel sheet 名规整：非法字符 / \ ? * [ ] : 替换为下划线，超 31 字符截断。
/// 跟 Python 端 _safe_sheet_name 等价。收敛 Anchor/Coating/Leeb Handlers 与
/// CoatingTemplateExpander 此前各自重复的 SafeSheetName（行为完全一致）。
/// </summary>
public static class SheetNameUtil
{
    public static string Safe(string name)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var c in name)
            sb.Append("/\\?*[]:".Contains(c) ? '_' : c);
        var safe = sb.ToString();
        return safe.Length > 31 ? safe.Substring(0, 31) : safe;
    }
}
