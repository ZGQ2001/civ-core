/**
 * TableView —— 纯展示组件，渲染 ParsedTable 为 HTML &lt;table&gt;。
 *
 * 解耦：只接受 props，不直接调用 useTemplateEditor —— 父组件传 bindings/selectedCell 进来。
 * 这样 TableView 可以独立测试，未来想做 read-only preview 也能直接复用。
 */
import { useMemo } from 'react';

import { cn } from '../../../lib/cn';
import type { ParsedCell, ParsedTable } from '../types';

interface Props {
  table: ParsedTable;
  /** 已绑定的格子集合 —— key="r-c"，value=字段中文名（前端组装好传进来）。 */
  boundLabels: Record<string, string>;
  selected: { row: number; col: number } | null;
  onCellClick: (row: number, col: number) => void;
}

export function TableView({
  table,
  boundLabels,
  selected,
  onCellClick,
}: Props) {
  // 主格按 (row,col) 索引 + 被合并覆盖的格集合
  const { masterAt, hidden } = useMemo(() => buildIndex(table), [table]);

  // 用 0..rowCount × 0..colCount 双层遍历做视觉网格；hidden 跳过、master 渲染
  const rows: number[] = Array.from({ length: table.row_count }, (_, i) => i);
  const cols: number[] = Array.from({ length: table.col_count }, (_, i) => i);

  return (
    <div className="overflow-auto">
      <table className="border-vscode-border w-max border-collapse border text-xs">
        <tbody>
          {rows.map((r) => (
            <tr key={r}>
              {cols.map((c) => {
                if (hidden.has(`${r}-${c}`)) return null;
                const cell = masterAt.get(`${r}-${c}`);
                if (!cell) return <EmptyTd key={c} />;
                const k = `${r}-${c}`;
                const label = boundLabels[k];
                const isSelected = selected?.row === r && selected?.col === c;
                return (
                  <CellTd
                    key={c}
                    cell={cell}
                    boundLabel={label}
                    isSelected={isSelected}
                    onClick={() => onCellClick(r, c)}
                  />
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CellTd({
  cell,
  boundLabel,
  isSelected,
  onClick,
}: {
  cell: ParsedCell;
  boundLabel: string | undefined;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <td
      rowSpan={cell.row_span}
      colSpan={cell.col_span}
      onClick={onClick}
      className={cn(
        'border-vscode-border min-w-[60px] cursor-pointer border px-2 py-1 align-middle transition-colors',
        boundLabel
          ? 'bg-[#1e3a5f] hover:bg-[#264c7a]'
          : 'bg-vscode-bg hover:bg-vscode-hover',
        isSelected && 'outline outline-2 -outline-offset-2 outline-red-400',
        cell.bold && 'font-semibold',
      )}
      style={cell.font_size ? { fontSize: `${cell.font_size}pt` } : undefined}
    >
      <div className="text-vscode-text whitespace-pre-wrap">{cell.text}</div>
      {boundLabel && (
        <div className="mt-0.5 text-[10px] text-blue-300">
          <i className="codicon codicon-symbol-field !text-[10px]" />{' '}
          {boundLabel}
        </div>
      )}
    </td>
  );
}

function EmptyTd() {
  // 视觉网格里既不是主格也不是 hidden（不应发生）——兜底渲染空格
  return <td className="border-vscode-border border bg-[#1a1a1a]" />;
}

/** ParsedTable → 主格索引 + hidden 集合（hidden = 被合并覆盖的格）。 */
function buildIndex(table: ParsedTable): {
  masterAt: Map<string, ParsedCell>;
  hidden: Set<string>;
} {
  const masterAt = new Map<string, ParsedCell>();
  const hidden = new Set<string>();
  for (const cell of table.cells) {
    masterAt.set(`${cell.row}-${cell.col}`, cell);
    for (let dr = 0; dr < cell.row_span; dr++) {
      for (let dc = 0; dc < cell.col_span; dc++) {
        if (dr === 0 && dc === 0) continue;
        hidden.add(`${cell.row + dr}-${cell.col + dc}`);
      }
    }
  }
  return { masterAt, hidden };
}
