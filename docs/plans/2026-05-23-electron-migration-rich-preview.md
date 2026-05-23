# 计划：迁移 Tauri → Electron + 富格式文档预览

## Context

**为什么换 Electron：**
- Rust 门槛高，AI 写主进程易出错，CI 审查成本高
- Node.js 主进程对 AI 和人类都更易维护调试
- 不依赖 WebView2，对旧机器和未来跨平台友好
- C# + Python sidecar 通信协议不变，迁移只涉及主进程层

**设计原则（参考 VS Code）：**
- **物理隔离**：主进程 / 渲染进程 / 各 sidecar 各占独立 OS 进程，互不共享内存
- **并发异步**：多请求同时在途，按 ID 匹配响应，不强制串行
- **彻底解耦**：Router 独立类，路由配置与 main.ts 分离；前端 IPC 集中在 `ipc.ts` 一处
- **规范协议**：JSON-RPC 2.0 over newline-delimited stdin/stdout，前端→主进程走结构化 contextBridge 命名空间

---

## 第一阶段：Electron 架构

### 目录结构

```
frontend/
├── electron/
│   ├── protocol.ts     # 协议类型定义（RpcRequest / RpcResponse / IpcApi）
│   ├── sidecar.ts      # JsonRpcSidecar：物理进程管理 + 并发异步 transport
│   ├── router.ts       # RpcRouter：可注册路由，解耦 main.ts
│   ├── main.ts         # 装配入口：创建 sidecar + 注册路由 + 挂 ipcMain
│   └── preload.ts      # 命名空间 contextBridge（不暴露 Node/Electron 原生）
└── src/
    ├── lib/
    │   ├── ipc.ts      # 前端唯一 IPC 出口（所有 electronAPI 调用汇聚于此）
    │   ├── rpc.ts      # 薄包装：export rpc = ipc.rpc（工具页不改 import）
    │   └── shell.ts    # 替换 opener
    └── electron.d.ts   # window.electronAPI 类型声明
```

---

### `electron/protocol.ts`

协议层类型，与具体实现无关：

```typescript
// JSON-RPC 2.0 消息类型
export interface RpcRequest {
  jsonrpc: '2.0';
  id: number;
  method: string;
  params: unknown;
}

export interface RpcResponse {
  jsonrpc: '2.0';
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

// contextBridge 暴露的命名空间 API 契约
// 这个接口在 preload.ts 实现，在 electron.d.ts 声明到 Window
export interface IpcApi {
  rpc: {
    call(method: string, params: unknown): Promise<unknown>;
  };
  dialog: {
    open(opts: Electron.OpenDialogOptions): Promise<string[]>;
    save(opts: Electron.SaveDialogOptions): Promise<string | null>;
  };
  shell: {
    openPath(path: string): Promise<void>;
  };
  fs: {
    readBytes(path: string): Promise<Uint8Array>;  // PDF 渲染用
  };
  window: {
    minimize(): void;
    maximize(): void;
    close(): void;
  };
}
```

---

### `electron/sidecar.ts`

物理进程隔离 + 并发异步 transport（多请求同时在途，按 ID 匹配）：

```typescript
import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';

const DEFAULT_TIMEOUT_MS = 30_000;

interface PendingRequest {
  resolve(v: unknown): void;
  reject(e: Error): void;
  timer: NodeJS.Timeout;
}

export class JsonRpcSidecar extends EventEmitter {
  private proc!: ChildProcess;
  private pending = new Map<number, PendingRequest>();
  private nextId = 0;
  private buf = '';
  readonly name: string;

  constructor(
    name: string,
    private readonly command: string,
    private readonly args: string[],
    private readonly cwd?: string,
  ) {
    super();
    this.name = name;
    this.start();
  }

  private start() {
    this.proc = spawn(this.command, this.args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: this.cwd,
    });

    this.proc.stdout!.setEncoding('utf8');
    this.proc.stdout!.on('data', (chunk: string) => {
      this.buf += chunk;
      const lines = this.buf.split('\n');
      this.buf = lines.pop()!;
      for (const line of lines) {
        if (!line.trim()) continue;
        try { this.dispatch(JSON.parse(line)); }
        catch { process.stderr.write(`[${this.name}] bad JSON: ${line}\n`); }
      }
    });

    // stderr 原样转发，不污染协议流
    this.proc.stderr!.on('data', (d: Buffer) =>
      process.stderr.write(`[${this.name}] ${d}`)
    );

    this.proc.on('exit', (code) => {
      // 进程退出：reject 所有在途请求
      for (const [, p] of this.pending) {
        clearTimeout(p.timer);
        p.reject(new Error(`Sidecar '${this.name}' exited (code ${code})`));
      }
      this.pending.clear();
      this.emit('exit', code);
    });
  }

  call(method: string, params: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC timeout (${timeoutMs}ms): ${this.name}/${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });

      const req: RpcRequest = { jsonrpc: '2.0', id, method, params };
      this.proc.stdin!.write(JSON.stringify(req) + '\n');
    });
  }

  private dispatch(msg: RpcResponse) {
    const p = this.pending.get(msg.id);
    if (!p) return;
    clearTimeout(p.timer);
    this.pending.delete(msg.id);
    msg.error
      ? p.reject(new Error(msg.error.message))
      : p.resolve(msg.result);
  }

  kill() { this.proc.kill(); }
}
```

---

### `electron/router.ts`

可注册路由，与 main.ts 解耦：

```typescript
import { JsonRpcSidecar } from './sidecar';

export interface RouteConfig {
  sidecar: JsonRpcSidecar;
  prefixes?: string[];       // 匹配前缀，e.g. 'plot_curves.'
  exact?: string[];          // 精确匹配，e.g. 'ping'
}

export class RpcRouter {
  private routes: RouteConfig[] = [];

  constructor(private readonly defaultSidecar: JsonRpcSidecar) {}

  register(config: RouteConfig) {
    this.routes.push(config);
    return this;
  }

  route(method: string): JsonRpcSidecar {
    for (const r of this.routes) {
      if (r.exact?.includes(method)) return r.sidecar;
      if (r.prefixes?.some(p => method.startsWith(p))) return r.sidecar;
    }
    return this.defaultSidecar;
  }

  call(method: string, params: unknown): Promise<unknown> {
    return this.route(method).call(method, params);
  }
}
```

---

### `electron/main.ts`

装配入口，只负责组装——不含路由逻辑：

```typescript
import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron';
import path from 'path';
import fs from 'fs/promises';
import { JsonRpcSidecar } from './sidecar';
import { RpcRouter } from './router';

let mainWindow: BrowserWindow;
let router: RpcRouter;

app.whenReady().then(() => {
  const root = path.resolve(__dirname, '../..');

  const csharp = new JsonRpcSidecar('csharp', 'dotnet', [
    'exec',
    path.join(root, 'dotnet/civ-doc/bin/Debug/net9.0/civ-doc.dll'),
    '--root', root,
  ], root);

  const python = new JsonRpcSidecar('python', 'uv', [
    'run', 'python', '-m', 'civ_core.api', '--root', root,
  ], root);

  // C# 是默认 sidecar，Python 注册白名单（同 lib.rs is_python_method）
  router = new RpcRouter(csharp).register({
    sidecar: python,
    prefixes: ['workspace.', 'files.', 'plot_curves.', 'pdf_tools.', 'word2pdf.'],
    exact: ['ping', 'version'],
  });

  mainWindow = new BrowserWindow({
    width: 1280, height: 800,
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,    // 渲染进程与主进程物理隔离
      nodeIntegration: false,    // 渲染进程禁止访问 Node.js
      sandbox: false,            // preload 需要 require，暂不启用 sandbox
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  devUrl
    ? mainWindow.loadURL(devUrl)
    : mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
});

// IPC handlers 按命名空间注册（与 preload 命名空间一一对应）
ipcMain.handle('rpc:call', (_e, method: string, params: unknown) =>
  router.call(method, params)
);

ipcMain.handle('dialog:open', (_e, opts: Electron.OpenDialogOptions) =>
  dialog.showOpenDialog(mainWindow, opts).then(r => r.filePaths)
);
ipcMain.handle('dialog:save', (_e, opts: Electron.SaveDialogOptions) =>
  dialog.showSaveDialog(mainWindow, opts).then(r => r.filePath ?? null)
);
ipcMain.handle('shell:open-path', (_e, p: string) => shell.openPath(p));
ipcMain.handle('fs:read-bytes', (_e, p: string) => fs.readFile(p));

ipcMain.on('window:minimize', () => mainWindow.minimize());
ipcMain.on('window:maximize', () =>
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize()
);
ipcMain.on('window:close', () => mainWindow.close());

app.on('window-all-closed', () => {
  router?.route('ping').kill();  // python
  // csharp 引用在 router 内，通过 defaultSidecar 访问—实际用 app.on 统一 kill
  app.quit();
});
```

---

### `electron/preload.ts`

命名空间隔离，不暴露任何 Node/Electron 原生对象：

```typescript
import { contextBridge, ipcRenderer } from 'electron';
import type { IpcApi } from './protocol';

const api: IpcApi = {
  rpc: {
    call: (method, params) => ipcRenderer.invoke('rpc:call', method, params),
  },
  dialog: {
    open: (opts) => ipcRenderer.invoke('dialog:open', opts),
    save: (opts) => ipcRenderer.invoke('dialog:save', opts),
  },
  shell: {
    openPath: (p) => ipcRenderer.invoke('shell:open-path', p),
  },
  fs: {
    readBytes: (p) => ipcRenderer.invoke('fs:read-bytes', p).then(
      (buf: Buffer) => new Uint8Array(buf)
    ),
  },
  window: {
    minimize: () => ipcRenderer.send('window:minimize'),
    maximize: () => ipcRenderer.send('window:maximize'),
    close: () => ipcRenderer.send('window:close'),
  },
};

contextBridge.exposeInMainWorld('electronAPI', api);
```

---

### `frontend/src/electron.d.ts`

```typescript
import type { IpcApi } from '../../electron/protocol';

declare global {
  interface Window {
    electronAPI: IpcApi;
  }
}
```

---

### `frontend/src/lib/ipc.ts`（新建）

前端唯一 IPC 出口，所有 `window.electronAPI` 调用在此汇聚：

```typescript
// 此文件是前端与主进程的唯一边界。工具页不直接用 window.electronAPI。

export const ipc = {
  rpc: <T>(method: string, params?: unknown): Promise<T> =>
    window.electronAPI.rpc.call(method, params ?? {}) as Promise<T>,

  dialog: {
    open: (opts: Parameters<Window['electronAPI']['dialog']['open']>[0]) =>
      window.electronAPI.dialog.open(opts),
    save: (opts: Parameters<Window['electronAPI']['dialog']['save']>[0]) =>
      window.electronAPI.dialog.save(opts),
  },

  shell: { openPath: (p: string) => window.electronAPI.shell.openPath(p) },

  fs: { readBytes: (p: string) => window.electronAPI.fs.readBytes(p) },

  window: {
    minimize: () => window.electronAPI.window.minimize(),
    maximize: () => window.electronAPI.window.maximize(),
    close: () => window.electronAPI.window.close(),
  },
} as const;
```

### `frontend/src/lib/rpc.ts`

```typescript
import { ipc } from './ipc';
// 工具页 import { rpc } from '../lib/rpc' 不变
export const rpc = ipc.rpc;
```

### 其他前端改动

**`shell.ts`**：`openPath` → `ipc.shell.openPath`

**`TitleBar.tsx`**：
- 拖拽区加 `style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}`，按钮加 `no-drag`
- 按钮调用 `ipc.window.minimize()` 等

**4 个工具 controller 的 dialog**：
```typescript
// open
const paths = await ipc.dialog.open({ properties: ['openFile', 'multiSelections'], filters: [...] });
// save
const p = await ipc.dialog.save({ filters: [...] });
```

### package.json + vite 配置

移除：`@tauri-apps/plugin-dialog`、`@tauri-apps/plugin-opener`、`@tauri-apps/api`、`@tauri-apps/cli`

新增：`electron`、`electron-builder`、`vite-plugin-electron`、`vite-plugin-electron-renderer`

`vite.config.ts` 加插件：
```typescript
import electron from 'vite-plugin-electron';
electron([{ entry: 'electron/main.ts' }, { entry: 'electron/preload.ts', onstart: o => o.reload() }])
```

### 删除

`frontend/src-tauri/` 整目录

### 文档同步

- `CLAUDE.md`：架构图更新（Tauri → Electron，invoke → ipc.rpc）
- `.ai/RULES.md`：目录结构（src-tauri → electron/）、测试命令（删 Rust cargo）、T6打包（Tauri externalBin → electron-builder extraResources）
- `frontend/CLAUDE.md`：构建命令（tauri:dev → npm run dev）

---

## 第二阶段：富格式 Excel 预览

### C# 新增：`xlsx.preview_rich`

**文件**：`dotnet/civ-doc/Handlers/XlsxHandlers.cs`

入参：`{ path, sheet?, max_rows? }`（默认 200）

返回（TypeScript 类型存 `frontend/src/components/viewers/excel-types.ts`）：
```typescript
export interface RichPreviewData {
  sheets: string[];
  sheet: string;
  total_rows: number;
  shown_rows: number;
  col_count: number;
  col_widths: Record<number, number>;   // 1-based → ClosedXML 字符宽
  row_heights: Record<number, number>;  // 1-based → 点高
  merges: Array<{ sr: number; sc: number; er: number; ec: number }>; // 0-based
  cells: Array<{
    r: number; c: number;               // 0-based
    v: string | number | boolean | null;
    d: string;
    bold?: true; italic?: true;
    ha?: 'l' | 'c' | 'r';
    bg?: string; fc?: string;           // "#RRGGBB"
    wrap?: true;
  }>;
  images: Array<{ r: number; c: number; data: string }>;  // base64 data URI
}
```

ClosedXML：`ws.MergedRanges` / `cell.Style.*` / `ws.Pictures`（整块 try-catch，失败返空）

### 前端 ExcelViewer

**`frontend/src/components/viewers/ExcelViewer.tsx`**

Props：`data`, `loading`, `highlightCols`, `highlightRows`, `onColClick(col: number)`, `onRowClick(row: number)`

核心：预计算 `suppressedSet`（合并覆盖格）+ `mergeMap`（主格 → rowSpan/colSpan），渲染时跳过 suppressed，主格加 span 属性。

集成 `data_processing`：`onColClick` → `setBatchIdCol`，`onRowClick` → `setHeaderRow`

---

## 第三阶段：PDF 渲染

### 前端 PdfViewer

**新增依赖**：`pdfjs-dist`

**`frontend/src/components/viewers/PdfViewer.tsx`**

```typescript
// 加载：走 ipc.fs.readBytes（无需 asset 协议配置）
const bytes = await ipc.fs.readBytes(pdfPath);
const task = pdfjsLib.getDocument({ data: bytes });

// Worker（Vite ?url 导入）
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
```

渲染：canvas 逐页 + Intersection Observer 惰性加载。

集成：
- `pdf_tools/Page.tsx`：点击文件行展开折叠式 PdfViewer
- `word2pdf/Page.tsx`：转换完成后展示输出文件预览

---

## 关键文件

| 文件 | 变更 |
|------|------|
| `frontend/electron/protocol.ts` | 新建（协议类型） |
| `frontend/electron/sidecar.ts` | 新建（并发 transport） |
| `frontend/electron/router.ts` | 新建（可注册路由） |
| `frontend/electron/main.ts` | 新建（装配入口） |
| `frontend/electron/preload.ts` | 新建（命名空间 IPC） |
| `frontend/src/electron.d.ts` | 新建（类型声明） |
| `frontend/src/lib/ipc.ts` | 新建（前端唯一 IPC 出口） |
| `frontend/src/lib/rpc.ts` | 改为 `export const rpc = ipc.rpc` |
| `frontend/src/lib/shell.ts` | 改 opener → `ipc.shell.openPath` |
| `frontend/src/components/TitleBar.tsx` | CSS drag + `ipc.window.*` |
| `frontend/src/tools/*/controller.tsx` | `ipc.dialog.*`（4 个文件） |
| `frontend/vite.config.ts` | 加 vite-plugin-electron |
| `frontend/package.json` | 换依赖 + scripts |
| `frontend/src-tauri/` | **整目录删除** |
| `CLAUDE.md` | 架构图更新 |
| `.ai/RULES.md` | 目录/命令/技术债更新 |
| `frontend/CLAUDE.md` | 构建命令更新 |
| `dotnet/civ-doc/Handlers/XlsxHandlers.cs` | 新增 `xlsx.preview_rich` |
| `frontend/src/components/viewers/excel-types.ts` | 新建 |
| `frontend/src/components/viewers/ExcelViewer.tsx` | 新建 |
| `frontend/src/components/viewers/PdfViewer.tsx` | 新建 |
| `frontend/src/tools/data_processing/controller.tsx` | 新增 richPreview |
| `frontend/src/tools/data_processing/Page.tsx` | 替换预览组件 |
| `frontend/src/tools/pdf_tools/Page.tsx` | 加 PdfViewer |

## 验证

1. `cd frontend && npm install && npm run dev` → Electron 窗口正常启动
2. 4 个工具页 RPC / dialog / opener 全功能正常
3. 含合并单元格 xlsx → ExcelViewer 正确渲染 rowspan/colspan，交互回调触发
4. PDF 文件 → PdfViewer 渲染真实页面内容
5. `cd dotnet && dotnet test` 全过
6. `cd frontend && npx tsc -b --noEmit` 无报错（包括 electron/ 目录）
