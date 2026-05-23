# 前端域规则

> **角色**：仅在 AI 操作 `frontend/src/` 目录时加载。放前端专属编码规范。
> **主宪法**：`../CLAUDE.md`（架构/路由/不可变规则）

---

## 技术栈

Vite + React 19 + TypeScript + Tailwind v4 + @vscode/codicons + react-resizable-panels

## 工具页范式

4 个工具页统一结构：

```
tools/<tool>/
├── index.ts           export { Provider, Page, SettingsForm }
├── types.ts           State / Actions / Ctx 类型
├── controller.tsx     createContext + Provider + 状态管理
├── Page.tsx           主界面（中间预览区）
└── SettingsForm.tsx   右侧参数区（在 RightPanel 内渲染）
```

### Controller 模板

```tsx
// controller.tsx
interface State { running: boolean; runError: string | null; previewLoading: boolean; ... }
interface Actions { run(): Promise<RunRes | null>; ... }
interface RunRes { summary: string; ... }

const Ctx = createContext<(State & Actions) | null>(null);

export function Provider({ children }: { children: ReactNode }) {
    const [state, setState] = useState<State>({ ... });
    const reqIdRef = useRef(0);

    const actions: Actions = useMemo(() => ({
        async run() {
            setState(s => ({ ...s, running: true, runError: null }));
            try {
                const data = await rpc<RunRes>("tool.run", { ... });
                setState(s => ({ ...s, running: false }));
                return data;  // ← 必须 return！Page.tsx 依赖这个返回值
            } catch (e) {
                setState(s => ({ ...s, running: false, runError: String(e) }));
                return null;
            }
        },
        // ...
    }), [/* deps */]);

    return <Ctx.Provider value={{ ...state, ...actions }}>{children}</Ctx.Provider>;
}

export function useXxxCtrl() {
    const v = useContext(Ctx);
    if (!v) throw new Error("useXxxCtrl must be inside Provider");
    return v;
}
```

### Page 模板

```tsx
// Page.tsx
export function Page({ appendOutput }: { appendOutput?: (line: string) => void }) {
    const c = useXxxCtrl();

    // ✅ 正确：run() 返回结果
    const handleRun = useCallback(async () => {
        const res = await c.run();
        if (res) {
            appendOutput?.(`完成：${res.summary}`);
        } else if (c.runError) {
            appendOutput?.(`错误：${c.runError}`);
        }
    }, [c, appendOutput]);

    // ❌ 禁止：await c.run() 后读 c.result（陈旧闭包）

    return (/* JSX */);
}
```

### SettingsForm 模板

```tsx
// SettingsForm.tsx
export function SettingsForm() {
  const c = useXxxCtrl();
  return <div className="space-y-4 p-3">{/* 参数表单 */}</div>;
}
```

## RPC 调用

```tsx
// lib/rpc.ts
export async function rpc<T>(
  method: string,
  params?: Record<string, unknown>,
): Promise<T> {
  return await invoke<T>('rpc_call', { method, params: params ?? {} });
}
```

**注意**：`as T` 无运行时校验。后端返回字段缺失时渲染才报错。未来可加 zod 校验。

## 布局约束

```
TitleBar (30px)
[ActivityBar(48) | SideBar(全高) | (Editor + 底部 Panel) | RightPanel(全高)]
StatusBar (22px)
```

- SideBar：全高，不被底部 Panel 截断
- 底部 Panel：专用「输出/日志」Tab；Ctrl+J toggle
- RightPanel：全高，tab 化（当前工具调参 + AI 助手占位）；Ctrl+Alt+B toggle
- 工具页：中间上部预览区 + 右侧参数区（RightPanel）

## 样式

- Tailwind v4，暗色主题（`bg-[#1e1e1e]` 基底）
- 图标：@vscode/codicons，只用真实存在的名字（见 `../.ai/RULES.md` 完整列表）
- 禁 emoji（UI/commit/AI 文档）
- 原生控件深色：`index.css` 已设 `html { color-scheme: dark }`

## 公共组件

`tools/_shared/forms.tsx`：`Field` / `Picker` / `ResetBtn` / `RunBtn`（4 个工具共用的 form 控件）

## 快捷键

| 快捷键     | 功能              |
| ---------- | ----------------- |
| Ctrl+B     | toggle SideBar    |
| Ctrl+J     | toggle 底部 Panel |
| Ctrl+Alt+B | toggle RightPanel |

## 构建

```bash
cd frontend
npm install                     # 装依赖
npx tsc -b --noEmit             # TS 类型检查
npm run build                   # 生产构建
npm run tauri:dev               # 开发模式（Tauri + Vite + Python/C# sidecar）
```
