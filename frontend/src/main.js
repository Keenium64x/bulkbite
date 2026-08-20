import { createApp } from "vue"
import { createRouter, createWebHistory } from "vue-router"
import App from "./App.vue"
import "@/styles/desyium/index.css"
import "@/styles/app.css"

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: "/:pathMatch(.*)*", component: App }],
})

window.csrf_token = window.csrf_token || window.boot?.csrf_token
createApp(App).use(router).mount("#app")
