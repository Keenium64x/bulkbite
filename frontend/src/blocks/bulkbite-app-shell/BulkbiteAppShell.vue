<script setup>
import { ref } from "vue"
import {
  CalendarDays,
  ChevronRight,
  CookingPot,
  LogIn,
  LogOut,
  MapPin,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  ReceiptText,
  Tags,
  Settings,
  Truck,
  UserRound,
} from "lucide-vue-next"
import { SystemLink, SystemOperationalButton } from "@/desyium"

// =============================================================================
// region SHELL CONTRACT
// =============================================================================

defineProps({
  sections: { type: Array, required: true },
  setupLinks: { type: Array, default: () => [
    { label: "Items", icon: Package, doctype: "BulkBite Item", href: "/bulkbite/setup/BulkBite%20Item" },
    { label: "Food categories", icon: Tags, doctype: "BulkBite Item Category", href: "/bulkbite/setup/BulkBite%20Item%20Category" },
    { label: "Recipes", icon: CookingPot, doctype: "BulkBite Recipe", href: "/bulkbite/setup/BulkBite%20Recipe" },
    { label: "Suppliers", icon: Truck, doctype: "BulkBite Supplier", href: "/bulkbite/setup/BulkBite%20Supplier" },
    { label: "Supplier offers", icon: ReceiptText, doctype: "BulkBite Supplier Offer", href: "/bulkbite/setup/BulkBite%20Supplier%20Offer" },
    { label: "Locations", icon: MapPin, doctype: "BulkBite Location", href: "/bulkbite/setup/BulkBite%20Location" },
    { label: "Meal plans", icon: CalendarDays, doctype: "BulkBite Production Plan", href: "/bulkbite/setup/BulkBite%20Production%20Plan" },
    { label: "Customer plans", icon: UserRound, doctype: "BulkBite Customer Plan Type", href: "/bulkbite/setup/BulkBite%20Customer%20Plan%20Type" },
  ] },
  activeSection: { type: String, required: true },
  user: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  sessionBusy: { type: Boolean, default: false },
})

defineEmits(["navigate", "refresh", "logout"])

// endregion SHELL CONTRACT

// =============================================================================
// region SIDEBAR STATE
// =============================================================================

const sidebarCollapsed = ref(window.localStorage.getItem("bulkbite-sidebar") === "collapsed")

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  window.localStorage.setItem("bulkbite-sidebar", sidebarCollapsed.value ? "collapsed" : "expanded")
}

// endregion SIDEBAR STATE
</script>

<template>
  <section data-block="bulkbite-app-shell" class="app-shell" :class="{ 'app-shell--collapsed': sidebarCollapsed }">
    <aside class="app-shell__sidebar" aria-label="BulkBite setup and tools">
      <header class="app-shell__brand">
        <div class="app-shell__brand-copy">
          <p class="app-shell__kicker">BulkBite Stock</p>
          <p class="app-shell__descriptor">Kitchen operations</p>
        </div>
        <SystemOperationalButton class="app-shell__collapse" variant="ghost" :label="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :tooltip="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :aria-expanded="!sidebarCollapsed" @click="toggleSidebar">
          <PanelLeftOpen v-if="sidebarCollapsed" aria-hidden="true" />
          <PanelLeftClose v-else aria-hidden="true" />
        </SystemOperationalButton>
      </header>

      <nav class="app-shell__utility-nav" aria-label="Setup records">
        <p class="app-shell__nav-label">Setup</p>
        <SystemLink v-for="link in setupLinks" :key="link.href" :href="link.href" class="app-shell__utility-link" :title="sidebarCollapsed ? link.label : undefined" :aria-label="sidebarCollapsed ? link.label : undefined" @click.prevent="$emit('navigate', { mode: 'list', doctype: link.doctype })">
          <span class="app-shell__sidebar-icon" aria-hidden="true"><component :is="link.icon || Settings" /></span>
          <span class="app-shell__utility-label">{{ link.label }}</span>
          <ChevronRight class="app-shell__utility-arrow" aria-hidden="true" />
        </SystemLink>
      </nav>

      <footer class="app-shell__sidebar-footer">
        <section class="app-shell__account" aria-label="Account">
          <div class="app-shell__account-user" :title="sidebarCollapsed ? (user || 'Guest') : undefined">
            <span class="app-shell__account-avatar" aria-hidden="true"><UserRound /></span>
            <div class="app-shell__account-copy">
              <p>{{ user && user !== 'Guest' ? user : 'Guest' }}</p>
            </div>
          </div>

          <SystemOperationalButton v-if="user && user !== 'Guest'" class="app-shell__sidebar-action app-shell__session-action" variant="ghost" :loading="sessionBusy" loading-text="Signing out" label="Log out" :tooltip="sidebarCollapsed ? 'Log out' : undefined" @click="$emit('logout')">
            <LogOut aria-hidden="true" />
            <span class="app-shell__utility-label app-shell__session-label">Log out</span>
          </SystemOperationalButton>

          <SystemLink v-else href="/login?redirect-to=%2Fbulkbite" class="app-shell__sidebar-action app-shell__session-link" aria-label="Log in" :title="sidebarCollapsed ? 'Log in' : undefined">
            <LogIn aria-hidden="true" />
            <span class="app-shell__utility-label app-shell__session-label">Log in</span>
          </SystemLink>
        </section>
      </footer>
    </aside>

    <div class="app-shell__main">
      <div class="app-shell__top-area">
        <header class="app-shell__header">
          <div class="app-shell__header-copy">
            <p class="app-shell__header-label">Kitchen operations</p>
            <p class="app-shell__header-note">Plan, buy, receive, cook, and reconcile</p>
          </div>
          <SystemOperationalButton class="app-shell__refresh" variant="subtle" size="md" :disabled="busy" :aria-busy="busy" :label="busy ? 'Refreshing stock' : 'Refresh stock'" @click="$emit('refresh')">
            <span v-if="busy" class="app-shell__refresh-loader" aria-hidden="true" />
            <span>{{ busy ? 'Refreshing' : 'Refresh stock' }}</span>
          </SystemOperationalButton>
        </header>

        <nav class="app-shell__nav" aria-label="Main stock flow">
          <div class="app-shell__nav-inner">
            <SystemOperationalButton v-for="section in sections" :key="section.id" class="app-shell__nav-button" :class="{ 'is-active': activeSection === section.id }" :aria-current="activeSection === section.id ? 'page' : undefined" variant="subtle" size="lg" @click="$emit('navigate', section.id)">
              <span>{{ section.label }}</span>
            </SystemOperationalButton>
          </div>
        </nav>
      </div>

      <main class="app-shell__work" tabindex="-1"><slot /></main>
    </div>
  </section>
</template>

<style scoped>
.app-shell{display:grid;grid-template-columns:16rem minmax(0,1fr);min-height:100vh;background:var(--theme-canvas);color:var(--theme-text);transition:grid-template-columns .18s ease}.app-shell--collapsed{grid-template-columns:4.75rem minmax(0,1fr)}.app-shell__sidebar{position:sticky;top:0;z-index:20;display:flex;flex-direction:column;width:100%;min-width:0;max-width:100%;height:100vh;overflow:hidden;padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-navigation-sidebar-border);background:var(--theme-navigation-sidebar);color:var(--theme-navigation-sidebar-text)}.app-shell__brand{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-xs);min-height:4rem;padding:var(--spacing-xs) var(--spacing-2xs) var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-navigation-sidebar-border)}.app-shell__brand-copy,.app-shell__header-copy,.app-shell__account-copy{min-width:0}.app-shell__kicker,.app-shell__descriptor,.app-shell__sidebar p,.app-shell__header p{margin:0}.app-shell__kicker{color:var(--theme-navigation-sidebar-text);font-size:var(--font-size-0);font-weight:var(--font-weight-700)}.app-shell__descriptor{margin-top:var(--spacing-3xs)!important;color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--2)}.app-shell__collapse{flex:0 0 2.5rem!important;width:2.5rem!important;height:2.5rem!important;min-height:2.5rem!important;padding:0!important;border:var(--border-width-1) solid var(--theme-navigation-sidebar-border)!important;background:var(--theme-navigation-sidebar-control)!important;color:var(--theme-navigation-sidebar-text)!important;box-shadow:none!important}.app-shell__collapse:hover{background:var(--theme-navigation-sidebar-hover)!important}.app-shell__collapse :deep(svg){width:1rem!important;height:1rem!important}.app-shell__utility-nav{display:grid;gap:var(--spacing-3xs);padding-top:var(--spacing-s)}.app-shell__nav-label{padding:0 var(--spacing-xs) var(--spacing-2xs);color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.app-shell__utility-link{display:grid;grid-template-columns:2.25rem minmax(0,1fr) 1rem;align-items:center;gap:var(--spacing-2xs);min-height:2.75rem;padding:0 var(--spacing-2xs);border-radius:var(--component-radius-button);color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--1);line-height:1;text-decoration:none;text-decoration-color:transparent}.app-shell__utility-link:hover{background:var(--theme-navigation-sidebar-hover);color:var(--theme-navigation-sidebar-text);text-decoration:none}.app-shell__utility-link:focus-visible,.app-shell__session-link:focus-visible{outline:2px solid var(--theme-navigation-sidebar-text);outline-offset:2px}.app-shell__sidebar-icon,.app-shell__account-avatar{display:grid;place-items:center;width:2.25rem;height:2.25rem;border-radius:var(--component-radius-button);background:var(--theme-navigation-sidebar-control);color:var(--theme-navigation-sidebar-text)}.app-shell__sidebar-icon svg,.app-shell__account-avatar svg{width:1.05rem;height:1.05rem;stroke-width:1.8}.app-shell__utility-arrow{width:.9rem;height:.9rem}.app-shell__sidebar-footer{display:grid;gap:var(--spacing-xs);margin-top:auto}.app-shell__sidebar-action{display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:var(--spacing-xs)!important;width:100%;height:2.75rem!important;min-height:2.75rem!important;padding:0 var(--spacing-xs)!important;border:0!important;border-radius:var(--component-radius-button)!important;background:transparent!important;color:var(--theme-navigation-sidebar-muted)!important;font-size:var(--font-size--1)!important;line-height:1!important;box-shadow:none!important}.app-shell__sidebar-action:hover,.app-shell__export-button.is-active{background:var(--theme-navigation-sidebar-hover)!important;color:var(--theme-navigation-sidebar-text)!important}.app-shell__sidebar-action :is(svg){flex:0 0 1.05rem!important;width:1.05rem!important;height:1.05rem!important;max-width:1.05rem!important;max-height:1.05rem!important}.app-shell__account{display:grid;gap:var(--spacing-2xs);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-navigation-sidebar-border);border-radius:var(--component-radius-card);background:var(--theme-navigation-sidebar-panel)}.app-shell__account-user{display:grid;grid-template-columns:2.25rem minmax(0,1fr);align-items:center;gap:var(--spacing-xs);min-width:0}.app-shell__account-copy{display:grid;gap:var(--spacing-3xs);color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--2)}.app-shell__account-copy p{overflow:hidden;color:var(--theme-navigation-sidebar-text);text-overflow:ellipsis;white-space:nowrap}.app-shell__account-status{width:max-content;background:var(--theme-navigation-sidebar-control)!important;color:var(--theme-navigation-sidebar-muted)!important}.app-shell__session-link{text-decoration:none}.app-shell--collapsed :is(.app-shell__brand-copy,.app-shell__nav-label,.app-shell__utility-label,.app-shell__utility-arrow,.app-shell__account-copy){display:none}.app-shell--collapsed .app-shell__brand{justify-content:center;padding-inline:0}.app-shell--collapsed .app-shell__utility-link{grid-template-columns:1fr;justify-items:center;padding:0}.app-shell--collapsed .app-shell__sidebar-action{justify-content:center!important;padding-inline:0!important}.app-shell--collapsed .app-shell__account{justify-items:center;padding:var(--spacing-2xs)}.app-shell--collapsed .app-shell__account-user{grid-template-columns:1fr}.app-shell__main{min-width:0}.app-shell__top-area{position:sticky;top:0;z-index:10;background:var(--theme-navigation-header)}.app-shell__header{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-m);height:4.25rem;padding:0 var(--spacing-m);border-bottom:var(--border-width-1) solid var(--theme-navigation-header-border);background:var(--theme-navigation-header);color:var(--theme-navigation-header-text)}.app-shell__header-label{color:var(--theme-navigation-header-text);font-weight:var(--font-weight-700)}.app-shell__header-note{margin-top:var(--spacing-3xs)!important;color:var(--theme-navigation-header-muted);font-size:var(--font-size--2)}.app-shell__refresh{flex:0 0 8.75rem!important;width:8.75rem!important;min-width:8.75rem!important;max-width:8.75rem!important;height:2.75rem!important;min-height:2.75rem!important;max-height:2.75rem!important;overflow:hidden!important;padding:0 var(--spacing-xs)!important;border:var(--border-width-1) solid var(--theme-navigation-header-border)!important;border-radius:var(--component-radius-button)!important;background:var(--theme-navigation-header-control)!important;color:var(--theme-navigation-header-text)!important;line-height:1!important;white-space:nowrap!important;box-shadow:none!important}.app-shell__refresh:hover{background:var(--theme-navigation-header-hover)!important}.app-shell__refresh :deep(svg){display:block!important;flex:0 0 1rem!important;width:1rem!important;height:1rem!important;min-width:1rem!important;min-height:1rem!important;max-width:1rem!important;max-height:1rem!important;scale:1!important}.app-shell__nav{overflow-x:auto;border-bottom:var(--border-width-1) solid var(--theme-navigation-header-border);background:var(--theme-navigation-tabs)}.app-shell__nav-inner{display:flex;gap:var(--spacing-2xs);width:min(100%,90rem);margin-inline:auto;padding:var(--spacing-xs) var(--spacing-m)}.app-shell__nav :deep(.app-shell__nav-button){position:relative;flex:0 0 auto;gap:var(--spacing-2xs)!important;height:2.75rem!important;min-height:2.75rem!important;padding-inline:var(--spacing-s)!important;border:var(--border-width-1) solid transparent!important;border-radius:var(--component-radius-button)!important;background:var(--theme-navigation-tab)!important;color:var(--theme-navigation-header-muted)!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button:hover){border-color:var(--theme-navigation-header-border)!important;background:var(--theme-navigation-tab-hover)!important;color:var(--theme-navigation-header-text)!important}.app-shell__nav :deep(.app-shell__nav-button:focus-visible){outline:2px solid var(--theme-navigation-header-text)!important;outline-offset:2px!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button.is-active){border-color:var(--theme-navigation-active-border)!important;background:var(--theme-navigation-active)!important;color:var(--theme-navigation-active-text)!important}.app-shell__nav :deep(.app-shell__nav-button.is-active)::after{position:absolute;right:var(--spacing-s);bottom:-.45rem;left:var(--spacing-s);height:2px;border-radius:999px;background:var(--theme-navigation-active-accent);content:""}.app-shell__nav-number{font-size:var(--font-size--2);font-variant-numeric:tabular-nums;opacity:.74}.app-shell__work{min-width:0;min-height:calc(100vh - 7.75rem);background:var(--theme-canvas)}
@media(max-width:64rem){.app-shell,.app-shell--collapsed{grid-template-columns:1fr;width:100%;max-width:100vw;overflow-x:clip}.app-shell__sidebar{position:static;width:100%;min-width:0;max-width:100vw;height:auto;padding:var(--spacing-xs) var(--spacing-s);border-right:0;border-bottom:var(--border-width-1) solid var(--theme-navigation-sidebar-border)}.app-shell__brand{align-items:center;min-height:3.25rem;padding:0}.app-shell__brand-copy,.app-shell--collapsed .app-shell__brand-copy{display:block}.app-shell__utility-nav{display:flex;overflow-x:auto;gap:var(--spacing-3xs);padding-top:var(--spacing-xs)}.app-shell__nav-label{display:none}.app-shell__utility-link,.app-shell--collapsed .app-shell__utility-link{flex:0 0 auto;grid-template-columns:2.25rem auto;padding-inline:var(--spacing-2xs)}.app-shell__utility-arrow{display:none}.app-shell__sidebar-footer{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--spacing-xs);margin-top:var(--spacing-xs)}.app-shell__account{grid-template-columns:minmax(0,1fr) auto;align-items:center;padding:var(--spacing-2xs)}.app-shell__account-user,.app-shell--collapsed .app-shell__account-user{grid-template-columns:2.25rem minmax(0,1fr)}.app-shell--collapsed .app-shell__account-copy{display:grid}.app-shell--collapsed .app-shell__sidebar-action{justify-content:flex-start!important;padding-inline:var(--spacing-xs)!important}.app-shell--collapsed .app-shell__utility-label{display:inline}.app-shell__session-action,.app-shell__session-link{width:auto}.app-shell__top-area{position:static}.app-shell__header{height:4rem;padding-inline:var(--spacing-s)}.app-shell__nav-inner{width:max-content;min-width:100%;padding-inline:var(--spacing-s)}}
@media(max-width:44rem){.app-shell__sidebar-footer{grid-template-columns:1fr}.app-shell__account{grid-template-columns:minmax(0,1fr) auto}.app-shell__export-button{width:100%}.app-shell__header-note{display:none}.app-shell__refresh{flex-basis:7.75rem!important;width:7.75rem!important;min-width:7.75rem!important;max-width:7.75rem!important}.app-shell__nav :deep(.app-shell__nav-button){min-width:max-content}}
.app-shell__refresh :deep(svg){display:inline-block!important;flex:0 0 .875rem!important;width:.875rem!important;height:.875rem!important;min-width:.875rem!important;min-height:.875rem!important;max-width:.875rem!important;max-height:.875rem!important;scale:1!important;transform-origin:center!important}
.app-shell__refresh-loader{display:block;flex:0 0 .75rem;width:.75rem;height:.75rem;border:1.5px solid currentColor;border-right-color:transparent;border-radius:999px;animation:app-shell-spin .7s linear infinite}@keyframes app-shell-spin{to{transform:rotate(360deg)}}
:deep(.app-shell__collapse){border:var(--border-width-1) solid var(--theme-navigation-sidebar-border)!important;background:var(--theme-navigation-sidebar-control)!important;color:var(--theme-navigation-sidebar-text)!important}:deep(.app-shell__collapse svg){width:1rem!important;height:1rem!important;stroke:currentColor!important}:deep(.app-shell__sidebar-action){color:var(--theme-navigation-sidebar-muted)!important}:deep(.app-shell__sidebar-action > span.truncate){display:flex!important;align-items:center!important;gap:var(--spacing-xs)!important;width:100%;height:auto!important;overflow:visible!important}:deep(.app-shell__sidebar-action > span.truncate svg),:deep(.app-shell__session-link svg){flex:0 0 1.05rem!important;width:1.05rem!important;height:1.05rem!important;stroke:currentColor!important}:deep(.app-shell__export-button:hover),:deep(.app-shell__export-button.is-active),:deep(.app-shell__session-action:hover){background:var(--theme-navigation-sidebar-hover)!important;color:var(--theme-navigation-sidebar-text)!important}:deep(.app-shell__refresh){flex:0 0 8.75rem!important;width:8.75rem!important;min-width:8.75rem!important;max-width:8.75rem!important;height:2.75rem!important;min-height:2.75rem!important;max-height:2.75rem!important;border-color:var(--theme-navigation-header-border)!important;background:var(--theme-navigation-header-control)!important;color:var(--theme-navigation-header-text)!important}.app-shell__refresh :deep(> span.truncate){display:flex;align-items:center;justify-content:center;gap:var(--spacing-2xs);width:100%;overflow:visible;color:inherit!important}.app-shell__refresh :deep(> span.truncate > span:last-child){min-width:5.25rem;text-align:left}.app-shell__account-copy{display:block}.app-shell__account-copy p{font-size:var(--font-size--2);font-weight:var(--font-weight-600)}
@media(min-width:64.0625rem){.app-shell__account{grid-template-columns:minmax(0,1fr) 2.25rem;align-items:center;padding:var(--spacing-2xs)}:deep(.app-shell__session-action),:deep(.app-shell__session-link){display:flex!important;align-items:center!important;justify-content:center!important;flex:0 0 2.25rem!important;width:2.25rem!important;min-width:2.25rem!important;height:2.25rem!important;min-height:2.25rem!important;padding:0!important;white-space:nowrap}:deep(.app-shell__session-action > span.truncate){justify-content:center!important;gap:0!important}:deep(.app-shell__session-action > span.truncate svg){flex:0 0 1rem!important;width:1rem!important;height:1rem!important}.app-shell__session-label{display:none!important}}
</style>
