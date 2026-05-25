/**
 * template_editor 状态控制中心 —— Phase 2 骨架。
 *
 * 当前能力：
 *  - 启动期拉已保存模板列表 + anchor 字段清单
 *  - 选 docx → 调 template.parse → 拿 ParsedTable + signature
 *  - 文件树双击 .docx 联动当前工具
 *
 * 暂未做（留给下一轮）：bindings 编辑、save/load/delete、TableView 渲染。
 * 解耦：actions 不掺 UI；UI 文件不写 RPC。
 */
/* eslint-disable react-refresh/only-export-components -- hook 与 Provider 同文件共存，是工具页范式（见 frontend/CLAUDE.md） */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { rpc } from '../../lib/rpc';
import { logLine, useShell } from '../../lib/shell';
import type { FieldDef, ParsedTable, TemplateMeta } from './types';

const TOOL_ID = 'template_editor';
const ACCEPTED_EXTS = new Set(['.docx']);
const DEFAULT_PROJECT_TYPE = 'anchor';

interface State {
  // 已保存模板列表
  templates: TemplateMeta[];
  templatesLoading: boolean;
  templatesError: string | null;

  // 当前 project 字段清单（anchor 是默认；未来加下拉选）
  projectType: string;
  fields: FieldDef[];
  fieldsLoading: boolean;
  fieldsError: string | null;

  // 当前正在编辑的源 docx
  sourceDocxPath: string;
  parsed: ParsedTable | null;
  parseLoading: boolean;
  parseError: string | null;
}

interface Actions {
  setSourceDocxPath: (p: string) => void;
  setProjectType: (t: string) => void;
  reloadTemplates: () => Promise<void>;
  reloadFields: () => Promise<void>;
}

type Ctx = State & Actions;

const TemplateEditorContext = createContext<Ctx | null>(null);

export function useTemplateEditor(): Ctx {
  const v = useContext(TemplateEditorContext);
  if (!v)
    throw new Error(
      'useTemplateEditor must be used within <TemplateEditorProvider>',
    );
  return v;
}

export function TemplateEditorProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const shell = useShell();

  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  const [projectType, setProjectType] = useState<string>(DEFAULT_PROJECT_TYPE);
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [fieldsLoading, setFieldsLoading] = useState(false);
  const [fieldsError, setFieldsError] = useState<string | null>(null);

  const [sourceDocxPath, setSourceDocxPath] = useState<string>('');
  const [parsed, setParsed] = useState<ParsedTable | null>(null);
  const [parseLoading, setParseLoading] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  // ── 已保存模板列表 ─────────────────────────────────────
  const reloadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    setTemplatesError(null);
    try {
      const r = await rpc<{ templates: TemplateMeta[] }>('template.list');
      setTemplates(r.templates);
    } catch (e) {
      setTemplatesError(String(e));
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  // ── 字段清单 ──────────────────────────────────────────
  const reloadFields = useCallback(async () => {
    setFieldsLoading(true);
    setFieldsError(null);
    try {
      const r = await rpc<{ fields: FieldDef[] }>('template.fields', {
        project_type: projectType,
      });
      setFields(r.fields);
    } catch (e) {
      setFieldsError(String(e));
      setFields([]);
    } finally {
      setFieldsLoading(false);
    }
  }, [projectType]);

  // 启动期拉两份
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reloadTemplates();
  }, [reloadTemplates]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reloadFields();
  }, [reloadFields]);

  // ── 解析 docx：sourceDocxPath 变 → 调 template.parse ──
  useEffect(() => {
    if (!sourceDocxPath) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setParsed(null);
      setParseError(null);
      setParseLoading(false);
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }
    let cancelled = false;
    setParseLoading(true);
    setParseError(null);
    rpc<ParsedTable>('template.parse', { docx_path: sourceDocxPath })
      .then((r) => {
        if (cancelled) return;
        setParsed(r);
      })
      .catch((e) => {
        if (cancelled) return;
        setParseError(String(e));
        setParsed(null);
      })
      .finally(() => {
        if (!cancelled) setParseLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceDocxPath]);

  // ── 文件树双击 .docx 联动 ─────────────────────────────
  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (!ACCEPTED_EXTS.has(ext)) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSourceDocxPath(f.path);
    shell.appendOutput(logLine(`[模板编辑] 已接收文件: ${f.path}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  const ctx: Ctx = useMemo(
    () => ({
      templates,
      templatesLoading,
      templatesError,
      projectType,
      fields,
      fieldsLoading,
      fieldsError,
      sourceDocxPath,
      parsed,
      parseLoading,
      parseError,
      setSourceDocxPath,
      setProjectType,
      reloadTemplates,
      reloadFields,
    }),
    [
      templates,
      templatesLoading,
      templatesError,
      projectType,
      fields,
      fieldsLoading,
      fieldsError,
      sourceDocxPath,
      parsed,
      parseLoading,
      parseError,
      reloadTemplates,
      reloadFields,
    ],
  );

  return (
    <TemplateEditorContext.Provider value={ctx}>
      {children}
    </TemplateEditorContext.Provider>
  );
}
