/* eslint-disable react-refresh/only-export-components -- hook 与 Provider 同文件共存，是工具页范式 */
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
import type {
  CatalogSummary,
  FieldCatalog,
  ValidateResult,
} from './types';

const TOOL_ID = 'template_helper';
const ACCEPTED_EXTS = new Set(['.docx']);

interface State {
  catalogs: CatalogSummary[];
  catalogsLoading: boolean;
  activeCatalogId: string | null;
  activeCatalog: FieldCatalog | null;
  catalogLoading: boolean;

  docxPath: string;
  validateResult: ValidateResult | null;
  validating: boolean;
  validateError: string | null;

  copiedKey: string | null;
}

interface Actions {
  refreshCatalogs: () => Promise<void>;
  selectCatalog: (id: string) => Promise<void>;
  setDocxPath: (p: string) => void;
  validate: () => Promise<ValidateResult | null>;
  copyPlaceholder: (text: string, key: string) => void;
}

type Ctx = State & Actions;

const TemplateHelperContext = createContext<Ctx | null>(null);

export function useTemplateHelper(): Ctx {
  const v = useContext(TemplateHelperContext);
  if (!v)
    throw new Error('useTemplateHelper must be used within <TemplateHelperProvider>');
  return v;
}

export function TemplateHelperProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const shell = useShell();

  const [catalogs, setCatalogs] = useState<CatalogSummary[]>([]);
  const [catalogsLoading, setCatalogsLoading] = useState(false);
  const [activeCatalogId, setActiveCatalogId] = useState<string | null>(null);
  const [activeCatalog, setActiveCatalog] = useState<FieldCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);

  const [docxPath, setDocxPath] = useState('');
  const [validateResult, setValidateResult] = useState<ValidateResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [validateError, setValidateError] = useState<string | null>(null);

  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const refreshCatalogs = useCallback(async () => {
    setCatalogsLoading(true);
    try {
      const res = await rpc<{ catalogs: CatalogSummary[] }>('catalog.list');
      setCatalogs(res.catalogs);
      if (res.catalogs.length > 0 && !activeCatalogId) {
        setActiveCatalogId(res.catalogs[0].id);
      }
    } catch (e) {
      shell.appendOutput(logLine(`[模板助手] 加载字段目录失败: ${String(e)}`));
    } finally {
      setCatalogsLoading(false);
    }
  }, [activeCatalogId, shell]);

  const selectCatalog = useCallback(async (id: string) => {
    setActiveCatalogId(id);
    setCatalogLoading(true);
    setValidateResult(null);
    try {
      const res = await rpc<{ catalog: FieldCatalog }>('catalog.get', { id });
      setActiveCatalog(res.catalog);
    } catch (e) {
      shell.appendOutput(logLine(`[模板助手] 加载字段目录失败: ${String(e)}`));
      setActiveCatalog(null);
    } finally {
      setCatalogLoading(false);
    }
  }, [shell]);

  useEffect(() => {
    refreshCatalogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeCatalogId) {
      selectCatalog(activeCatalogId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCatalogId]);

  useEffect(() => {
    const f = shell.activatedFile;
    if (!f) return;
    if (shell.activeToolId !== TOOL_ID) return;
    const idx = f.path.lastIndexOf('.');
    const ext = idx > 0 ? f.path.slice(idx).toLowerCase() : '';
    if (!ACCEPTED_EXTS.has(ext)) return;
    setDocxPath(f.path);
    setValidateResult(null);
    setValidateError(null);
    shell.appendOutput(logLine(`[模板助手] 已接收模板文件: ${f.path}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.activatedFile?.key, shell.activeToolId]);

  const validate = useCallback(async (): Promise<ValidateResult | null> => {
    if (!docxPath || !activeCatalogId) return null;
    setValidating(true);
    setValidateError(null);
    try {
      const res = await rpc<ValidateResult>('template.validate', {
        docx_path: docxPath,
        catalog_id: activeCatalogId,
      });
      setValidateResult(res);
      const s = res.summary;
      shell.appendOutput(
        logLine(
          `[模板助手] 验证完成: ${s.matched_count} 个匹配, ${s.unrecognized_count} 个未识别, ${s.unused_count} 个未使用`,
        ),
      );
      return res;
    } catch (e) {
      const msg = String(e);
      setValidateError(msg);
      shell.appendOutput(logLine(`[模板助手] 验证失败: ${msg}`));
      return null;
    } finally {
      setValidating(false);
    }
  }, [docxPath, activeCatalogId, shell]);

  const copyPlaceholder = useCallback((text: string, key: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedKey(key);
    setTimeout(() => setCopiedKey((prev) => (prev === key ? null : prev)), 1500);
  }, []);

  const ctx: Ctx = useMemo(
    () => ({
      catalogs,
      catalogsLoading,
      activeCatalogId,
      activeCatalog,
      catalogLoading,
      docxPath,
      validateResult,
      validating,
      validateError,
      copiedKey,
      refreshCatalogs,
      selectCatalog,
      setDocxPath,
      validate,
      copyPlaceholder,
    }),
    [
      catalogs,
      catalogsLoading,
      activeCatalogId,
      activeCatalog,
      catalogLoading,
      docxPath,
      validateResult,
      validating,
      validateError,
      copiedKey,
      refreshCatalogs,
      selectCatalog,
      validate,
      copyPlaceholder,
    ],
  );

  return (
    <TemplateHelperContext.Provider value={ctx}>
      {children}
    </TemplateHelperContext.Provider>
  );
}
