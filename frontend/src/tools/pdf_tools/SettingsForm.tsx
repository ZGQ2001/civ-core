/**
 * pdf_tools 右侧 RightPanel「调参」tab：只放高级参数。
 *   - merge: 无（输出 PDF 路径已搬到中间区顶部）
 *   - split_by_ranges: 要拆哪几页
 *
 * 输出位置（合并/拆分）现在在 Page.tsx 顶部条直接选，不进右栏。
 * 拆后文件名固定为「源文件名_起始页-结束页.pdf」，不暴露模板给用户（非程序员看不懂占位符）。
 */
import { Field } from '../_shared/forms';
import { usePdfTools } from './controller';

export function PdfToolsSettingsForm() {
  const c = usePdfTools();

  if (c.mode === 'merge') {
    return (
      <div className="text-vscode-text-faint p-3 text-xs leading-relaxed">
        合并 PDF 没有高级参数。
        <br />
        在工具页顶部选好「输出到」和要合并的 PDF，再点「开始合并」即可。
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col space-y-3 overflow-auto p-3 text-xs">
      <Field
        label="要拆哪几页"
        hint="按页号分段写，逗号分隔。例如填 1-3,5,7-9 会拆成 3 个 PDF：第 1~3 页一个、第 5 页一个、第 7~9 页一个。要按页全拆，写 1,2,3,4… 即可。"
      >
        <input
          type="text"
          value={c.splitExpr}
          onChange={(e) => c.setSplitExpr(e.target.value)}
          placeholder="1-3,5,7-9"
          className="bg-vscode-input border-vscode-border text-vscode-text w-full rounded-[2px] border px-2 py-1 text-xs"
        />
      </Field>

      <div className="text-vscode-text-faint border-l-2 border-[#3a3a3a] pl-3 text-[11px] leading-relaxed">
        拆出的文件名自动生成：
        <span className="text-vscode-text-dim">报告.pdf</span> 拆 1-3 →{' '}
        <span className="text-vscode-text-dim">报告_1-3.pdf</span>
      </div>

      <div className="text-vscode-text-faint text-[11px]">
        填完后回到工具页点顶部「开始拆分」按钮。
      </div>
    </div>
  );
}
