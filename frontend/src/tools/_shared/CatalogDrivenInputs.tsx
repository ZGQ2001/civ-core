/**
 * 通用「按 catalog 渲染 user_input 输入区」公共组件。
 *
 * 解耦原则：
 *   - **catalog 是 single source of truth**：字段定义住在后端 ~/.civ-core/catalogs/<id>.json，
 *     用户在「模板助手」里改字段，这里立刻同步——避免「报告填充硬编码 32 字段、模板助手
 *     已经加了新字段、两端漂移」的状态错位。
 *   - **本组件不 own 数据**：values + onChange 全由调用方控制，方便接入预设保存/历史值下拉
 *     等扩展（P4）。
 *   - **只渲染 user_input source**：Parameter / RawInput / Calculated 都是程序算出来的，
 *     用户不能填；level=batch / level=component 的字段在调用方各自的「按批次」/「按构件」
 *     区域渲染（P4 接入），本组件只管 level=report + level=detection_item。
 *
 * 用法：
 *   <CatalogDrivenInputs
 *     catalogId="anchor"
 *     values={c.userInputs}
 *     onChange={c.setUserInput}
 *     onReset={c.resetUserInputs}
 *   />
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import { rpc } from '../../lib/rpc';
import { logLine, useShell } from '../../lib/shell';
import type {
  CatalogField,
  FieldCatalog,
  FieldLevel,
} from '../template_helper/types';
import { LEVEL_LABEL } from '../template_helper/types';

interface Props {
  catalogId: string;
  /** 字段值 map（key = catalog.field.key）。空字段也建议建 key 防受控警告。 */
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  /** 「全部清空」按钮回调；不传则不渲染该按钮。 */
  onReset?: () => void;
  /** 只渲染哪些 level（默认 report + detection_item，batch/component 留给调用方）。 */
  includeLevels?: ReadonlyArray<FieldLevel>;
  /**
   * 历史值 map：{ [fieldKey]: [historyValue1, historyValue2, ...] }。
   * 不为空 + 用户主动开启对应字段下拉时显示。聚合规则由调用方决定（如从 report_preset 拉）。
   */
  historyByKey?: Record<string, string[]>;
}

const DEFAULT_INCLUDE_LEVELS: ReadonlyArray<FieldLevel> = [
  'report',
  'detection_item',
];

export function CatalogDrivenInputs({
  catalogId,
  values,
  onChange,
  onReset,
  includeLevels = DEFAULT_INCLUDE_LEVELS,
  historyByKey,
}: Props) {
  const shell = useShell();
  const [catalog, setCatalog] = useState<FieldCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await rpc<{ catalog: FieldCatalog }>('catalog.get', {
        id: catalogId,
      });
      setCatalog(res.catalog);
    } catch (e) {
      const msg = String(e);
      setError(msg);
      shell.appendOutput(logLine(`[报告] 加载字段目录失败: ${msg}`));
    } finally {
      setLoading(false);
    }
  }, [catalogId, shell]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCatalog();
  }, [loadCatalog]);

  /// 按 level → group 两级分组，level 顺序固定（报告级 → 检测项目级 → ...）以保证
  /// 渲染顺序「项目级 → 构件级」（用户偏好），group 内字段按 catalog 原顺序。
  const grouped = useMemo(() => {
    if (!catalog) return [] as Array<LevelGroup>;
    const allowedLevels = new Set(includeLevels);
    const byLevel = new Map<FieldLevel, Map<string, CatalogField[]>>();
    for (const f of catalog.fields) {
      if (f.source !== 'user_input') continue;
      if (!allowedLevels.has(f.level as FieldLevel)) continue;
      const lvl = f.level as FieldLevel;
      let groupMap = byLevel.get(lvl);
      if (!groupMap) {
        groupMap = new Map();
        byLevel.set(lvl, groupMap);
      }
      const g = f.group || '其他';
      const arr = groupMap.get(g);
      if (arr) arr.push(f);
      else groupMap.set(g, [f]);
    }
    return includeLevels
      .filter((lvl) => byLevel.has(lvl))
      .map((lvl) => ({
        level: lvl,
        label: LEVEL_LABEL[lvl],
        groups: Array.from(byLevel.get(lvl)!.entries()).map(
          ([group, fields]) => ({ group, fields }),
        ),
      }));
  }, [catalog, includeLevels]);

  const totalFields = useMemo(
    () =>
      grouped.reduce(
        (s, lvl) => s + lvl.groups.reduce((g, gr) => g + gr.fields.length, 0),
        0,
      ),
    [grouped],
  );

  if (loading) {
    return (
      <div className="text-vscode-text-dim p-3 text-[11px]">
        <i className="codicon codicon-loading codicon-modifier-spin mr-1 !text-[12px]" />
        加载字段目录…
      </div>
    );
  }
  if (error) {
    return (
      <div className="border-l-2 border-l-red-400 bg-[#2d2d2d] p-2 text-[11px] whitespace-pre-wrap text-red-400">
        加载字段目录失败：{error}
        <button
          type="button"
          onClick={loadCatalog}
          className="text-vscode-focus ml-2 underline"
        >
          重试
        </button>
      </div>
    );
  }
  if (!catalog || totalFields === 0) {
    return (
      <div className="text-vscode-text-faint p-3 text-[11px] italic">
        字段目录「{catalogId}」内无可填字段（先在模板助手新建/添加字段）
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="border-vscode-border flex items-center justify-between border-t pt-3">
        <div className="text-vscode-text text-[12px] font-medium">
          项目元信息（{totalFields} 项 · 跟随模板助手字段目录）
        </div>
        {onReset && (
          <button
            type="button"
            onClick={onReset}
            className="text-vscode-text-dim hover:text-vscode-focus text-[11px] hover:underline"
            title="清空所有输入框；不会影响已保存的预设"
          >
            全部清空
          </button>
        )}
      </div>

      {grouped.map((lvl) => (
        <LevelSection
          key={lvl.level}
          level={lvl.level}
          label={lvl.label}
          groups={lvl.groups}
          values={values}
          onChange={onChange}
          historyByKey={historyByKey}
        />
      ))}
    </div>
  );
}

interface LevelGroup {
  level: FieldLevel;
  label: string;
  groups: Array<{ group: string; fields: CatalogField[] }>;
}

function LevelSection({
  level,
  label,
  groups,
  values,
  onChange,
  historyByKey,
}: {
  level: FieldLevel;
  label: string;
  groups: Array<{ group: string; fields: CatalogField[] }>;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  historyByKey?: Record<string, string[]>;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className={`text-[11px] font-medium ${levelTextColor(level)}`}>
          {label}
        </span>
        <span className="text-vscode-text-faint text-[10px]">
          ({groups.reduce((s, g) => s + g.fields.length, 0)} 字段)
        </span>
      </div>
      {groups.map((g, idx) => (
        <GroupCard
          key={`${level}-${g.group}`}
          group={g.group}
          fields={g.fields}
          values={values}
          onChange={onChange}
          historyByKey={historyByKey}
          defaultExpanded={idx === 0}
        />
      ))}
    </div>
  );
}

function GroupCard({
  group,
  fields,
  values,
  onChange,
  historyByKey,
  defaultExpanded,
}: {
  group: string;
  fields: CatalogField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  historyByKey?: Record<string, string[]>;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const filledCount = fields.filter((f) => !!values[f.key]?.trim()).length;

  return (
    <div className="border-vscode-border rounded-[3px] border bg-[#252525]">
      <div
        className="hover:bg-vscode-hover flex cursor-pointer items-center px-2 py-1.5 select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <i
          className={`codicon codicon-chevron-${expanded ? 'down' : 'right'} text-vscode-text-dim mr-1 !text-[12px]`}
        />
        <span className="text-vscode-text text-[12px] font-medium">
          {group}
        </span>
        <span className="text-vscode-text-faint ml-auto text-[10px]">
          {filledCount} / {fields.length}
        </span>
      </div>
      {expanded && (
        <div className="border-vscode-border space-y-2 border-t px-3 py-2">
          {fields.map((f) => (
            <FieldRow
              key={f.key}
              field={f}
              value={values[f.key] ?? ''}
              onChange={onChange}
              history={historyByKey?.[f.key]}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * 单字段一行：左侧标签 + 输入框 + 右侧（可选）历史值下拉按钮。
 * 历史值下拉默认折叠（用户主动开启对应字段才显示菜单），符合用户约束
 * 「不会自动清空填写内容」延伸而来的「不主动覆盖用户输入」原则。
 */
function FieldRow({
  field,
  value,
  onChange,
  history,
}: {
  field: CatalogField;
  value: string;
  onChange: (key: string, value: string) => void;
  history?: string[];
}) {
  const [open, setOpen] = useState(false);
  const hasHistory = (history?.length ?? 0) > 0;

  return (
    <div>
      <div
        className="text-vscode-text-dim mb-0.5 text-[11px]"
        title={`Key: ${field.key}${field.aliases.length ? `\n别名: ${field.aliases.join(', ')}` : ''}`}
      >
        {field.name}
      </div>
      <div className="relative flex items-stretch gap-1">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          className="bg-vscode-input border-vscode-border text-vscode-text focus:border-vscode-focus min-w-0 flex-1 rounded-[2px] border px-2 py-1 text-xs focus:outline-none"
        />
        {hasHistory && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="border-vscode-border text-vscode-text-dim hover:bg-vscode-hover shrink-0 rounded-[2px] border bg-[#2a2a2a] px-1.5 text-[10px]"
            title={`从历史预设里选（${history!.length} 个候选）`}
          >
            <i
              className={`codicon codicon-chevron-${open ? 'up' : 'down'} !text-[11px]`}
            />
          </button>
        )}
        {open && hasHistory && (
          <div className="border-vscode-border absolute top-full right-0 z-50 mt-1 max-h-48 w-full overflow-y-auto rounded border bg-[#252526] shadow-lg">
            <div className="border-vscode-border flex items-center justify-between border-b px-2 py-1 text-[10px]">
              <span className="text-vscode-text-dim">
                历史值（来自报告预设）
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-vscode-text-dim hover:text-vscode-text"
              >
                <i className="codicon codicon-close !text-[11px]" />
              </button>
            </div>
            {history!.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => {
                  onChange(field.key, v);
                  setOpen(false);
                }}
                className="hover:bg-vscode-list-hover text-vscode-text block w-full truncate px-2 py-1 text-left text-[11px]"
                title={v}
              >
                {v}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function levelTextColor(level: FieldLevel): string {
  return (
    {
      report: 'text-blue-300',
      detection_item: 'text-cyan-300',
      batch: 'text-yellow-300',
      component: 'text-green-300',
    }[level] ?? 'text-vscode-text-dim'
  );
}
