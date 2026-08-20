import path from "node:path"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"
import frappeui from "frappe-ui/vite"

const frappeSiteName = process.env.FRAPPE_SITE_NAME || "bulkbite.localhost"
const frappeWebServerPort = Number(process.env.FRAPPE_WEB_SERVER_PORT || 8000)

export default defineConfig(({ command }) => ({
  base: command === "serve" ? "/" : "/assets/bulkbite/frontend/",
  optimizeDeps: { exclude: ["frappe-ui"], include: ["debug", "feather-icons"] },
  plugins: [
    frappeui({
      frappeProxy: false,
      jinjaBootData: true,
      lucideIcons: true,
      buildConfig: {
        outDir: "../bulkbite/public/frontend",
        indexHtmlPath: "../bulkbite/www/bulkbite.html",
        emptyOutDir: true,
        sourcemap: true,
      },
    }),
    vue(),
  ],
  build: {
    outDir: "../bulkbite/public/frontend",
    emptyOutDir: true,
    sourcemap: true,
    target: "es2018",
  },
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    allowedHosts: true,
    host: "0.0.0.0",
    port: 8080,
    strictPort: true,
    proxy: {
      "^/(app|login|api|assets|files|private)": {
        target: `http://127.0.0.1:${frappeWebServerPort}`,
        changeOrigin: false,
        configure(proxy) {
          proxy.on("proxyReq", (request) => {
            request.setHeader("Host", frappeSiteName)
            request.setHeader("X-Frappe-Site-Name", frappeSiteName)
          })
        },
      },
    },
  },
}))
