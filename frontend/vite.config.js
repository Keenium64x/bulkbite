import path from "node:path"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"
import frappeui from "frappe-ui/vite"

export default defineConfig({
  
  optimizeDeps: { exclude: ["frappe-ui"], include: ["feather-icons"] },
  plugins: [frappeui({ frappeProxy: false, jinjaBootData: false, buildConfig: false }), vue()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
})
