// Word 表格解析结果 —— 通用引擎层（纯数据，无 IO）。
//
// TemplateParser 读完一份 docx 输出 ParsedTable；前端 TableView 渲染它；
// ReportGenerator 用 TableSignature 做模板版本校验。
//
// 设计要点：
//   - 网格坐标体系：0-based (row, col)，按 OpenXML 视觉网格展开。
//     合并单元格只占主格（左上角）；被合并覆盖的格子用 IsHidden=true 标记，
//     前端 <td> 直接 return null 跳过即可。
//   - 不包含 binding / fieldKey —— 绑定信息走 TemplateConfig.json，跟 Parse 解耦。
//   - 不包含像素级行高列宽 —— Word 排版按比例还原即可（产品决定）。

namespace CivCore.Doc.Template;

/// <summary>
/// 单元格坐标（0-based）。引擎全程用这一种坐标，OpenXML 的 gridCol/cellRef 在 Parser 内部转换好。
/// </summary>
public record CellPosition(int Row, int Col);

/// <summary>单个可见单元格的解析结果。</summary>
public record ParsedCell
{
    /// <summary>单元格内文本（多 Run 已拼接）。空格保留。</summary>
    public string Text { get; init; } = "";

    /// <summary>跨多少行（≥1）。1 = 不跨行。</summary>
    public int RowSpan { get; init; } = 1;

    /// <summary>跨多少列（≥1）。1 = 不跨列。</summary>
    public int ColSpan { get; init; } = 1;

    /// <summary>是否含粗体 Run。前端可用来还原视觉。</summary>
    public bool Bold { get; init; }

    /// <summary>字号（Word "size half-points" / 2，即 21 = 10.5 磅）。null = 未显式设置。</summary>
    public double? FontSize { get; init; }
}

/// <summary>
/// 整张表的解析结果。
///
/// <para>Rows 是 0-based 行数组，每行是 0-based 列字典：只放主格（合并左上角），
/// 被合并覆盖的格在 HiddenCells 里。前端遍历时用 IsHidden(r,c) 判断跳过。</para>
/// <para>TableSignature 用来防"模板被改"——保存时记录，生成时比对。</para>
/// </summary>
public class ParsedTable
{
    /// <summary>主格内容。Rows[r][c] 存在 ⇒ (r,c) 是合并主格或独立格。</summary>
    public List<Dictionary<int, ParsedCell>> Rows { get; } = new();

    /// <summary>被合并覆盖的格集合（不是主格但被某个合并区覆盖）。</summary>
    private readonly HashSet<(int row, int col)> _hidden = new();

    /// <summary>表格总行数（按视觉网格）。</summary>
    public int RowCount { get; set; }

    /// <summary>表格总列数（按视觉网格的最大列数）。</summary>
    public int ColCount { get; set; }

    /// <summary>"rows:{N}_cols:{M}_hash:{6 hex}" — 防模板被改的版本指纹。</summary>
    public string TableSignature { get; set; } = "";

    /// <summary>该格是否被某个合并区覆盖（即不是主格）。</summary>
    public bool IsHidden(int row, int col) => _hidden.Contains((row, col));

    /// <summary>标记被合并覆盖的格（Parser 内部用）。</summary>
    public void MarkHidden(int row, int col) => _hidden.Add((row, col));

    /// <summary>把单元格放进主格表（自动按需扩 Rows 长度）。</summary>
    public void PutCell(int row, int col, ParsedCell cell)
    {
        while (Rows.Count <= row) Rows.Add(new Dictionary<int, ParsedCell>());
        Rows[row][col] = cell;
    }
}
