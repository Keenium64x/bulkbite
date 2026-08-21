import { createApp } from "vue"
import { createRouter, createWebHistory } from "vue-router"
import { Button } from "frappe-ui"
import App from "./App.vue"
import "@/styles/desyium/index.css"
import "@/styles/app.css"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/bulkbite/setup", name: "BulkBiteSetup", component: App, meta: { auxiliaryCatalogue: true } },
    { path: "/bulkbite/setup/:doctype", name: "BulkBiteSetupList", component: App, meta: { auxiliaryList: true } },
    { path: "/bulkbite/setup/:doctype/new", name: "AuxiliaryRecordCreate", component: App, meta: { auxiliaryRecord: true } },
    { path: "/bulkbite/setup/:doctype/:name", name: "AuxiliaryRecordEdit", component: App, meta: { auxiliaryRecord: true } },
    { path: "/:pathMatch(.*)*", component: App },
  ],
})

window.csrf_token = window.csrf_token || window.boot?.csrf_token
createApp(App).use(router).component("Button", Button).mount("#app")
