/**
 * pdf_tools 工具的前端类型契约。后端真源 api/handlers/pdf_tools.py。
 */
export type Mode = 'merge' | 'split_by_ranges';

export const MODE_LABELS: Record<Mode, string> = {
  merge: '合并',
  split_by_ranges: '拆分',
};

export interface PdfFileInfo {
  path: string;
  pages?: number;
  size_kb?: number;
  error?: string;
}

export interface InspectRes {
  files: PdfFileInfo[];
  total_pages: number;
}

export interface MergeRes {
  output: string;
  count: number;
}

export interface SplitRes {
  written: string[];
  count: number;
}
