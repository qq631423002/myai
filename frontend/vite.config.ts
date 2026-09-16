import { spawn } from 'node:child_process'
import { fileURLToPath, URL } from 'node:url'

import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

/**
 * 开发服务器起来之后，自动用 **Edge** 打开页面。
 *
 * 为什么要自己写一小段：Vite 自带的 `server.open: true` 只会打开
 * 「系统默认浏览器」，而这台机器默认是 Chrome（注册表里 http 是 ChromeHTML）。
 * 要指定 Edge，就得自己调命令 —— Edge 已注册在 Windows 的 App Paths 里，
 * 所以 `start msedge <url>` 可以直接用。
 *
 * 不想要自动打开：启动时带上环境变量 `NO_OPEN=1`（比如 `NO_OPEN=1 pnpm dev`）。
 */
function openInEdge(): Plugin {
  return {
    name: 'open-in-edge',
    apply: 'serve', // 只在 dev 时生效，build 不管
    configureServer(server) {
      server.httpServer?.once('listening', () => {
        // 等一小会儿：Vite 是在 listening 之后才算好 resolvedUrls 的
        setTimeout(() => {
          if (process.env.NO_OPEN) return

          // 正常能拿到 Vite 算好的地址（含实际端口）；拿不到就用配置里的端口兜底
          const url =
            server.resolvedUrls?.local?.[0] ?? `http://localhost:${server.config.server.port ?? 8080}/`

          let command: string
          let args: string[]

          if (process.platform === 'win32') {
            // Windows：start 后面第一个带引号的参数会被当作窗口标题，
            // 所以先塞一个空标题，再给浏览器名和网址
            command = 'cmd'
            args = ['/c', 'start', '', 'msedge', url]
          } else if (process.platform === 'darwin') {
            command = 'open'
            args = ['-a', 'Microsoft Edge', url]
          } else {
            command = 'microsoft-edge'
            args = [url]
          }

          try {
            // detached + stdio ignore：不挂在 vite 下面，vite 关了浏览器继续留着
            const child = spawn(command, args, { detached: true, stdio: 'ignore' })
            child.unref()
            server.config.logger.info(`  ➜  已在 Edge 中打开: ${url}`)
          } catch (e) {
            server.config.logger.warn(
              `用 Edge 打开失败（${e instanceof Error ? e.message : e}），手动访问 ${url} 即可`,
            )
          }
        }, 300)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
    openInEdge(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    port: 8080,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        // 后端路由本身就带 /api 前缀（如 /api/demo03），所以这里【不要】rewrite 去掉前缀，
        // 只把以 /api 开头的请求原样转发到 8000 端口。
      },
    },
  },

})
