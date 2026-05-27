/**
 * pdf_tools 右侧 RightPanel「调参」tab：只放高级参数。
 *   - merge: 无（输出 PDF 路径已搬到中间区顶部）
 *   - split_per_page: 拆后的文件名
 *   - split_by_ranges: 拆后的文件名 + 要拆哪几页
 *
 * 输出位置（合并/拆分）现在在 Page.tsx 顶部条直接选，不进右栏。
 */
import { Field } from '../_shared/forms';
import { usePdfTools } from './controller';

export function PdfToolsSettingsForm() {
  const c = usePdfTools();

  if (c.mode === 'merge') {
    return (
      <div className="text-vscode-text-faint p-4 text-xs leading-relaxed">
        合并 PDF 没有高级参数。
        <br />
        在工具页顶部选好「输出到」和要合并的 PDF，再点「开始合并」即可。
      </div>
    );
  }

  // 拆分模式：文件名 + （仅 ranges）哪几页
  return (
    <div className="flex h-full flex-col space-y-4 overflow-auto p-4 text-xs">
      {c.mode === 'split_by_ranges' && (
        <Field
          label="要拆哪几页"
          hint="按页号分段写，逗号分隔。例如填 1-3,5,7-9 会拆成 3 个 PDF：第 1~3 页一个、第 5 页一个、第 7~9 页一个。"
        >
          <input
            type="text"
            value={c.splitExpr}
            onChange={(e) => c.setSplitExpr(e.target.value)}
            placeholder="1-3,5,7-9"
            className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
          />
        </Field>
      )}

      <Field
        label="拆后的文件名"
        hint={
          c.mode === 'split_per_page'
            ? '可保留默认。{stem} 自动换成源文件名、{n} 自动换成页号。例：源文件叫 报告.pdf，模板 {stem}_p{n}.pdf 拆出来就是 报告_p1.pdf、报告_p2.pdf…'
            : '可保留默认。{stem}=源文件名、{start} {end}=该段起止页号。例：报告.pdf 拆 1-3 → 报告_1-3.pdf。'
        }
      >
        <input
          type="text"
          value={c.splitTemplate}
          onChange={(e) => c.setSplitTemplate(e.target.value)}
          placeholder={c.defaultTemplate}
          className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
        />
      </Field>

      <div className="text-vscode-text-faint pt-2 text-[11px]">
        填完后回到工具页点顶部「开始拆分」按钮。
      </div>
    </div>
  );
}
