/**
 * word2pdf 右侧 RightPanel「调参」tab：输出目录。
 * 当前参数极简（就一项）；未来想加「是否覆盖同名」「页面方向」之类的就在这里堆。
 */
import { useCallback } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { Field, Picker } from '../_shared/forms';
import { useWord2Pdf } from './controller';

export function Word2PdfSettingsForm() {
  const c = useWord2Pdf();

  const pickOutDir = useCallback(async () => {
    const sel = await openDialog({ title: '选择输出目录', directory: true });
    if (typeof sel === 'string') c.setOutDir(sel);
  }, [c]);

  return (
    <div className="flex h-full flex-col space-y-4 overflow-auto p-4 text-xs">
      <Field label="输出目录" hint="每个 docx 在此生成同名 .pdf">
        <Picker value={c.outDir} onPick={pickOutDir} placeholder="尚未选择" />
      </Field>

      <div className="text-vscode-text-faint pt-2 text-[11px]">
        添加 Word 文件 + 选好输出目录后点工具页顶部「开始转换」即可。
        <br />
        COM 单进程串行跑（开 1 个 Word 进程跑完所有文件），不要在跑的时候手动开
        Word。
      </div>
    </div>
  );
}
