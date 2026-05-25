// OpenXML 表格的视觉网格遍历器 —— Parser 和 Generator 共用底座。
//
// 解决「gridSpan + vMerge 让 TableCell 数组下标 ≠ 视觉网格列下标」的麻烦。
// 调用方拿到 (Row, Col, masterCell, RowSpan, ColSpan)，直接按视觉坐标定位。

using DocumentFormat.OpenXml.Wordprocessing;

namespace CivCore.Doc.Template;

public static class TableGridWalker
{
    /// <summary>遍历表的每个主格（合并单元格的左上角）。被合并覆盖的 TableCell 不 yield。</summary>
    public static IEnumerable<(int Row, int Col, TableCell Cell, int RowSpan, int ColSpan)> WalkMasters(Table table)
    {
        var rows = table.Elements<TableRow>().ToList();

        for (int r = 0; r < rows.Count; r++)
        {
            int c = 0;
            foreach (var cell in rows[r].Elements<TableCell>())
            {
                int gridSpan = GetGridSpan(cell);
                var vMerge = GetVMergeKind(cell);

                if (vMerge == VMergeKind.Continue)
                {
                    c += gridSpan;
                    continue;
                }

                int rowSpan = vMerge == VMergeKind.Restart
                    ? CountVMergeContinuations(rows, r, c, gridSpan) + 1
                    : 1;

                yield return (r, c, cell, rowSpan, gridSpan);
                c += gridSpan;
            }
        }
    }

    /// <summary>找指定视觉坐标的主格 TableCell。找不到返回 null（坐标对应合并覆盖区或越界）。</summary>
    public static TableCell? FindMasterAt(Table table, int row, int col)
    {
        foreach (var (r, c, cell, _, _) in WalkMasters(table))
            if (r == row && c == col) return cell;
        return null;
    }

    // ── 内部 ────────────────────────────────────────────────

    public static int GetGridSpan(TableCell cell)
    {
        var v = cell.TableCellProperties?.GridSpan?.Val?.Value;
        return v.HasValue && v.Value > 0 ? v.Value : 1;
    }

    public enum VMergeKind { None, Restart, Continue }

    public static VMergeKind GetVMergeKind(TableCell cell)
    {
        var vm = cell.TableCellProperties?.VerticalMerge;
        if (vm == null) return VMergeKind.None;
        return vm.Val?.Value == MergedCellValues.Restart ? VMergeKind.Restart : VMergeKind.Continue;
    }

    private static int CountVMergeContinuations(List<TableRow> rows, int startRow, int gridCol, int gridSpan)
    {
        int count = 0;
        for (int r = startRow + 1; r < rows.Count; r++)
        {
            int c = 0;
            TableCell? aligned = null;
            foreach (var cell in rows[r].Elements<TableCell>())
            {
                int gs = GetGridSpan(cell);
                if (c == gridCol && gs == gridSpan) { aligned = cell; break; }
                if (c >= gridCol) break;
                c += gs;
            }
            if (aligned == null) return count;
            if (GetVMergeKind(aligned) != VMergeKind.Continue) return count;
            count++;
        }
        return count;
    }
}
