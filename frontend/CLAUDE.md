# 前端域规则

> **角色**：仅在 AI 操作 `frontend/src/` 目录时加载。放前端专属编码规范。
> **主宪法**：`../CLAUDE.md`（架构/路由/不可变规则）

---

## 技术栈

Vite + React 19 + TypeScript + Tailwind v4 + @vscode/codicons + react-resizable-panels

## 工具页范式

所有工具页统一结构（当前 5 个：data_processing / plot_curves / report_generator / pdf_tools / word2pdf）：

```
tools/<tool>/
├── index.ts           export { Provider, Page, SettingsForm }
├── types.ts           State / Actions / Ctx 类型
├── controller.tsx     createContext + Provider + 状态管理
├── Page.tsx           主界面（中间预览区）
└── SettingsForm.tsx   右侧参数区（在 RightPanel 内渲染）
```

**工具间耦合原则**：工具之间不通过 useXxxCtrl() 隐式继承上游 state（曾经 report_generator 直接 useDataProcessing 是反例）。如果工具 B 想消费工具 A 的输入，提供「一键导入 A」按钮 —— 显式拷贝快照到 B 自己的 state。这样：

- 工具 B 能独立工作（用别人的输入 / 测试隔离）
- 装配线连贯（用户一键就能继承上游已填的）
- 状态变化追溯清晰（不会"上游一变下游莫名重渲染"）

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

| 文件                                    | 内容                                                                                                                                                                               |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tools/_shared/forms.tsx`               | `Field` / `Picker` / `ResetBtn` / `RunBtn`（所有工具共用的 form 控件）                                                                                                             |
| `tools/_shared/anchorParamsForm.tsx`    | 锚杆按批次工程参数 UI（P/Lf/La/A/E 5 字段 × N 批次折叠卡片）。data_processing 和 report_generator 通过 props 传 batchIds / paramsByBatch / setter 复用。                           |
| `tools/_shared/CatalogDrivenInputs.tsx` | 报告填充「项目元信息」公共渲染器：按 `catalog.get` 动态拉字段定义，按 level → group 分组渲染 user_input。模板助手改字段，报告填充立刻同步。接 `historyByKey` prop 显示历史值下拉。 |

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
