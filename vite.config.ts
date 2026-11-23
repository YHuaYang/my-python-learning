import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// 为什么不用 dev server：
// Django 负责渲染页面，如果开 Vite dev server 就要配代理、跨域、
// 静态路径映射，收益低于成本。用 build --watch 输出到
// blog/static/js/，Django 直接 serve 静态文件即可。
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./assets/js', import.meta.url)),
    },
  },

  build: {
    // 输出到 Django 的静态目录，产物不进 git（见 .gitignore）
    outDir: 'blog/static/js',
    emptyOutDir: false, // 别删掉同目录下其他文件
    // 不用哈希文件名：Django 模板里要写固定路径。
    // 缓存靠 URL 查询参数或部署时统一失效，个人博客流量小，够用
    rollupOptions: {
      // 两个入口，分别输出两个文件：
      //
      // bundle.js        —— 前台 React 孤岛（主题切换、导航、留言板）
      // admin-editor.js  —— 后台 Markdown 编辑器（Toast UI，约 940KB）
      //
      // 为什么不合成一个：Toast UI 体积接近 1MB，
      // 而前台访客完全用不到。分开后只有后台文章编辑页会加载它。
      input: {
        bundle: fileURLToPath(new URL('./assets/js/main.tsx', import.meta.url)),
        'admin-editor': fileURLToPath(
          new URL('./assets/js/admin-editor.ts', import.meta.url),
        ),
      },
      output: {
        // [name] 从 input 的键取值，得到 bundle.js 与 admin-editor.js
        entryFileNames: '[name].js',
        chunkFileNames: 'chunk-[name].js',
        assetFileNames: 'asset-[name][extname]',
        // 打成单个文件：孤岛组件总量小，多文件请求反而更慢
        manualChunks: undefined,
      },
    },
    // 保留可读性，便于排查。体积约 150KB 未压缩，gzip 后 45KB
    // Vite 8 用 Rolldown + Oxc，不再依赖 esbuild，
    // minify 写 'esbuild' 会报 ERR_MODULE_NOT_FOUND
    minify: 'oxc',
    sourcemap: false,
    target: 'es2020',
  },
})
