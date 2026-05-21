/**
 * word2pdf 工具的前端类型契约。后端真源 api/handlers/word2pdf.py。
 */
export interface DocxFileInfo {
  path: string;
  size_kb?: number;
  paragraphs?: number;
  /** 仅 Word 真打开保存过的 docx 才有 docProps/app.xml 的 Pages 缓存 */
  pages?: number;
  error?: string;
}

export interface InspectRes {
  files: DocxFileInfo[];
}

export interface ConvertRes {
  written: string[];
  failed: { path: string; error: string }[];
  total: number;
}
