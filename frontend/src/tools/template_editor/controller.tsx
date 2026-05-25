/**
 * template_editor 状态控制中心 —— 占位符驱动后大瘦身。
 *
 * 当前能力：拉一份字段清单（默认 anchor），让用户照着写 {key} 占位符进 Word 模板。
 * 没有模板 CRUD，没有 bindings，没有 Word 解析 —— Word 文件就是用户自己的。
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
import type { FieldDef } from './types';

const DEFAULT_PROJECT_TYPE = 'anchor';

interface State {
  projectType: string;
  fields: FieldDef[];
  loading: boolean;
  error: string | null;
}

interface Actions {
  setProjectType: (t: string) => void;
  reload: () => Promise<void>;
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
  const [projectType, setProjectType] = useState<string>(DEFAULT_PROJECT_TYPE);
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await rpc<{ fields: FieldDef[] }>('template.fields', {
        project_type: projectType,
      });
      setFields(r.fields);
    } catch (e) {
      setError(String(e));
      setFields([]);
    } finally {
      setLoading(false);
    }
  }, [projectType]);

  useEffect(() => {
    // 启动期 + projectType 变化时拉字段
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  const ctx: Ctx = useMemo(
    () => ({ projectType, fields, loading, error, setProjectType, reload }),
    [projectType, fields, loading, error, reload],
  );

  return (
    <TemplateEditorContext.Provider value={ctx}>
      {children}
    </TemplateEditorContext.Provider>
  );
}
