import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 为 Tauri 准备：dev server 用固定端口，与 src-tauri/tauri.conf.json 对齐
  server: {
    port: 1420,
    strictPort: true,
    // Rust 源码由 Tauri 监听；Vite 扫描 target 会在 Windows 上遇到占用中的 exe。
    watch: { ignored: ['**/src-tauri/**'] },
  },
  // Tauri 期望相对路径资源
  base: './',
  // 在 Tauri 调试时清理掉 dist
  clearScreen: false,
});
