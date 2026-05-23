/**
 * plot_curves 调参表单（在右侧 RightPanel 显示）。
 *
 * 4 tab：基础 / X 轴 / Y 轴 / 曲线样式
 * 每个 tab 一个独立文件（tabs/*.tsx），本文件只负责 tab 切换 + 渲染。
 *
 * 共用控件（Row/SliderInput/NumberCell）抽到 tabs/_shared.tsx。
 */
import { useState } from 'react';

import { cn } from '../../lib/cn';
import { usePlotCurves } from './controller';
import { AxisTab } from './tabs/AxisTab';
import { BasicTab } from './tabs/BasicTab';
import { CurvesTab } from './tabs/CurvesTab';

type TabId = 'basic' | 'xaxis' | 'yaxis' | 'curve';

export function PlotCurvesSettingsForm() {
  const c = usePlotCurves();
  const [tab, setTab] = useState<TabId>('basic');
  const preset = c.effectivePreset;

  if (!preset) {
    return (
      <div className="text-vscode-text-faint p-6 text-xs italic">
        （未加载曲线；请确认后端预设库可用。）
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col text-xs">
      <div className="border-vscode-border flex shrink-0 items-center gap-1 border-b px-2">
        <TabBtn
          label="基础"
          icon="symbol-misc"
          active={tab === 'basic'}
          onClick={() => setTab('basic')}
        />
        <TabBtn
          label="X 轴"
          icon="arrow-right"
          active={tab === 'xaxis'}
          onClick={() => setTab('xaxis')}
        />
        <TabBtn
          label="Y 轴"
          icon="arrow-up"
          active={tab === 'yaxis'}
          onClick={() => setTab('yaxis')}
        />
        <TabBtn
          label="曲线"
          icon="symbol-color"
          active={tab === 'curve'}
          onClick={() => setTab('curve')}
        />
        {c.edited && (
          <button
            type="button"
            onClick={c.resetPreset}
            title="撤销所有改动，回到曲线原版"
            className="text-vscode-focus ml-auto flex h-7 items-center gap-1 px-2 text-xs hover:underline"
          >
            <i className="codicon codicon-discard !text-[12px]" />
            还原
          </button>
        )}
      </div>

      <div className="flex-1 space-y-3 overflow-auto p-3">
        {tab === 'basic' && <BasicTab />}
        {tab === 'xaxis' && (
          <AxisTab
            axisName="X 轴"
            spec={preset.x_axis}
            onChange={(spec) => c.patchPreset((p) => ({ ...p, x_axis: spec }))}
          />
        )}
        {tab === 'yaxis' && (
          <AxisTab
            axisName="Y 轴"
            spec={preset.y_axis}
            onChange={(spec) => c.patchPreset((p) => ({ ...p, y_axis: spec }))}
          />
        )}
        {tab === 'curve' && <CurvesTab />}
      </div>
    </div>
  );
}

function TabBtn({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        '-mb-px flex h-7 items-center gap-1.5 border-b-2 px-3 text-xs transition-colors',
        active
          ? 'border-vscode-focus text-white'
          : 'text-vscode-text-dim border-transparent hover:text-white',
      )}
    >
      <i className={cn('codicon', `codicon-${icon}`, '!text-[12px]')} />
      {label}
    </button>
  );
}
