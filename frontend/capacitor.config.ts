import type { CapacitorConfig } from "@capacitor/cli"

const config: CapacitorConfig = {
  appId: "za.co.bulkbite.admin",
  appName: "BulkBite Admin",
  webDir: "dist-mobile",
  appendUserAgent: " BulkBiteNative/1",
  backgroundColor: "#F5F0E6",
  server: {
    hostname: "localhost",
    androidScheme: "https",
    cleartext: false,
    allowNavigation: ["admin.bulkbite.co.za"],
  },
  plugins: {
    CapacitorHttp: { enabled: true },
    App: { disableBackButtonHandler: true },
    Keyboard: { resize: "native", resizeOnFullScreen: true },
    StatusBar: { style: "DARK" },
  },
}

export default config
