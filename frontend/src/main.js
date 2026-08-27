import { createApp, h } from "vue"
import { createRouter, createWebHashHistory, createWebHistory, RouterView } from "vue-router"
import { Button } from "frappe-ui"
import App from "./App.vue"
import PriceHistoryPage from "./pages/PriceHistoryPage.vue"
import "@/styles/desyium/index.css"
import "@/styles/app.css"
import { runtimeConfig, requireNativeConfiguration } from "@/config/runtime"
import { initialiseNativeLifecycle } from "@/native/lifecycle"

const router = createRouter({
  history: runtimeConfig.isNative ? createWebHashHistory() : createWebHistory(),
  routes: [
    { path: "/bulkbite/prices", name: "BulkBitePriceHistory", component: PriceHistoryPage },
    { path: "/bulkbite/setup", name: "BulkBiteSetup", component: App, meta: { auxiliaryCatalogue: true } },
    { path: "/bulkbite/setup/:doctype", name: "BulkBiteSetupList", component: App, meta: { auxiliaryList: true } },
    { path: "/bulkbite/setup/:doctype/new", name: "AuxiliaryRecordCreate", component: App, meta: { auxiliaryRecord: true } },
    { path: "/bulkbite/setup/:doctype/:name", name: "AuxiliaryRecordEdit", component: App, meta: { auxiliaryRecord: true } },
    { path: "/:pathMatch(.*)*", component: App },
  ],
})

window.csrf_token = window.csrf_token || window.boot?.csrf_token
requireNativeConfiguration()
createApp({ render: () => h(RouterView) }).use(router).component("Button", Button).mount("#app")
initialiseNativeLifecycle(router)
