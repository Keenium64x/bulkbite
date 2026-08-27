import type { CapacitorConfig } from "@capacitor/cli"

const config: CapacitorConfig = {
  appId: "za.co.bulkbite.admin",
  appName: "BulkBite Admin",
  webDir: "dist-mobile",
  appendUserAgent: " BulkBiteNative/1",
  backgroundColor: "#f3efe9",
  server: { hostname: "localhost", androidScheme: "https" },
  plugins: {
    CapacitorHttp: { enabled: true },
    App: { disableBackButtonHandler: true },
    Keyboard: { resize: "native", resizeOnFullScreen: true },
    StatusBar: { style: "DARK" },
  },
}

export default config
