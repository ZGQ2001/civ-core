/**
 * report_generator 右侧 RightPanel「调参」tab。
 *
 * 三块：
 *   1. Word 模板路径（必填）
 *   2. 输出目录（可选，留空 = 自动在输入 Excel 同级建子目录）
 *   3. 项目元信息表单（24 个字段，按 7 个 group 折叠卡片）
 */
import { useCallback, useState } from 'react';
import { open as openDialog } from '@tauri-apps/plugin-dialog';

import { Field, Picker, ResetBtn } from '../_shared/forms';
import { useReportGenerator } from './controller';
import { USER_INPUT_GROUPS, type UserInputGroup } from './types';

export function ReportGeneratorSettingsForm() {
  const c = useReportGenerator();

  const pickTemplate = useCallback(async () => {
    const sel = await openDialog({
      title: '选择 Word 报告模板',
      multiple: false,
      filters: [{ name: 'Word', extensions: ['docx'] }],
    });
    if (typeof sel === 'string') c.setWordTemplatePath(sel);
  }, [c]);

  const pickOutputDir = useCallback(async () => {
    const sel = await openDialog({
      directory: true,
      multiple: false,
      title: '选择 Word 报告输出目录',
    });
    if (typeof sel === 'string') c.setOutputDir(sel);
  }, [c]);

  return (
    <div className="flex h-full flex-col space-y-4 overflow-auto p-4 text-xs">
      <Field
        label="Word 模板"
        hint="带 {{占位符}} 的 .docx；要按锚杆克隆的部分用 [[每根锚杆]] / [[/每根锚杆]] 包住"
      >
        <Picker
          value={c.wordTemplatePath}
          onPick={pickTemplate}
          placeholder="（必选）"
          muted={!c.wordTemplatePath}
          extra={
            c.wordTemplatePath ? (
              <ResetBtn onClick={() => c.setWordTemplatePath('')} />
            ) : undefined
          }
        />
      </Field>

      <Field label="输出目录" hint="留空 = 在输入 Excel 同级建「_Word报告」子目录">
        <Picker
          value={c.outputDir}
          onPick={pickOutputDir}
          placeholder="（自动）"
          muted={!c.outputDir}
          extra={
            c.outputDir ? (
              <ResetBtn onClick={() => c.setOutputDir('')} />
            ) : undefined
          }
        />
      </Field>

      <div className="flex items-center justify-between border-t border-vscode-border pt-3">
        <div className="text-vscode-text text-[12px] font-medium">
          项目元信息（{USER_INPUT_GROUPS.reduce((s, g) => s + g.fields.length, 0)} 项）
        </div>
        <button
          type="button"
          onClick={c.resetUserInputs}
          className="text-vscode-text-dim hover:text-vscode-focus text-[11px] hover:underline"
        >
          全部清空
        </button>
      </div>

      <div className="space-y-2">
        {USER_INPUT_GROUPS.map((g, idx) => (
          <GroupCard key={g.id} group={g} defaultExpanded={idx === 0} />
        ))}
      </div>

      <div className="text-vscode-text-faint pt-2 text-[11px]">
        改完到工具页中间点「生成 Word 报告」即可；输出路径会显示在那。
      </div>
    </div>
  );
}

function GroupCard({
  group,
  defaultExpanded,
}: {
  group: UserInputGroup;
  defaultExpanded: boolean;
}) {
  const c = useReportGenerator();
  const [expanded, setExpanded] = useState(defaultExpanded);

  const filledCount = group.fields.filter(
    (f) => !!c.userInputs[f.key]?.trim(),
  ).length;

  return (
    <div className="border-vscode-border rounded-[3px] border bg-[#252525]">
      <div
        className="hover:bg-vscode-hover flex cursor-pointer items-center px-2 py-1.5 select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <i
          className={`codicon codicon-chevron-${expanded ? 'down' : 'right'} text-vscode-text-dim mr-1 !text-[12px]`}
        />
        <i className={`codicon codicon-${group.icon} text-vscode-text-dim mr-1.5 !text-[12px]`} />
        <span className="text-vscode-text text-[12px] font-medium">
          {group.label}
        </span>
        <span className="text-vscode-text-faint ml-auto text-[10px]">
          {filledCount} / {group.fields.length}
        </span>
      </div>

      {expanded && (
        <div className="border-vscode-border space-y-2 border-t px-3 py-2">
          {group.fields.map((f) => (
            <div key={f.key}>
              <div className="text-vscode-text-dim mb-0.5 text-[11px]">
                {f.label}
              </div>
              <input
                type="text"
                value={c.userInputs[f.key]}
                placeholder={f.placeholder}
                onChange={(e) => c.setUserInput(f.key, e.target.value)}
                className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus w-full rounded-[2px] border px-2 py-1 text-xs focus:outline-none"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
