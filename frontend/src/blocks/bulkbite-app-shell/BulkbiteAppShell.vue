<script setup>
import { ref } from "vue"
import { SystemBadge, SystemLink, SystemOperationalButton } from "@/desyium"

defineProps({
  sections: { type: Array, required: true },
  setupLinks: { type: Array, default: () => [
    { label: "Items", shortLabel: "IT", doctype: "BulkBite Item", href: "/bulkbite/setup/BulkBite%20Item" },
    { label: "Recipes", shortLabel: "RC", doctype: "BulkBite Recipe", href: "/bulkbite/setup/BulkBite%20Recipe" },
    { label: "Suppliers", shortLabel: "SP", doctype: "BulkBite Supplier", href: "/bulkbite/setup/BulkBite%20Supplier" },
    { label: "Locations", shortLabel: "LC", doctype: "BulkBite Location", href: "/bulkbite/setup/BulkBite%20Location" },
    { label: "Meal plans", shortLabel: "PL", doctype: "BulkBite Production Plan", href: "/bulkbite/setup/BulkBite%20Production%20Plan" },
  ] },
  activeSection: { type: String, required: true },
  user: { type: String, default: "" },
  busy: { type: Boolean, default: false },
})

defineEmits(["navigate", "refresh"])
const sidebarCollapsed = ref(window.localStorage.getItem("bulkbite-sidebar") === "collapsed")
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  window.localStorage.setItem("bulkbite-sidebar", sidebarCollapsed.value ? "collapsed" : "expanded")
}
</script>

<template>
  <section data-block="bulkbite-app-shell" class="app-shell" :class="{ 'app-shell--collapsed': sidebarCollapsed }">
    <aside class="app-shell__sidebar" aria-label="BulkBite setup and tools">
      <div class="app-shell__brand">
        <div>
          <p class="app-shell__kicker">BulkBite Stock</p>
          <p class="app-shell__descriptor">Kitchen operations</p>
        </div>
        <SystemOperationalButton class="app-shell__collapse" variant="ghost" :aria-label="sidebarCollapsed ? 'Expand setup sidebar' : 'Collapse setup sidebar'" :aria-expanded="!sidebarCollapsed" @click="toggleSidebar"><span aria-hidden="true">{{ sidebarCollapsed ? '›' : '‹' }}</span></SystemOperationalButton>
      </div>

      <nav class="app-shell__utility-nav" aria-label="Setup">
        <p class="app-shell__nav-label">Setup</p>
        <SystemLink v-for="link in setupLinks" :key="link.href" :href="link.href" class="app-shell__utility-link" :title="sidebarCollapsed ? link.label : undefined" @click.prevent="$emit('navigate', { mode: 'list', doctype: link.doctype })">
          <span class="app-shell__utility-icon" aria-hidden="true">{{ link.shortLabel || link.label.slice(0, 2).toUpperCase() }}</span><span class="app-shell__utility-label">{{ link.label }}</span><span class="app-shell__utility-arrow" aria-hidden="true">›</span>
        </SystemLink>
      </nav>

      <div class="app-shell__sidebar-bottom">
        <SystemOperationalButton class="app-shell__export-button" :class="{ 'is-active': activeSection === 'export' }" variant="ghost" @click="$emit('navigate', 'export')"><span aria-hidden="true">EX</span><span class="app-shell__utility-label">Accountant export</span></SystemOperationalButton>
        <div class="app-shell__session-copy"><SystemBadge class="status-badge">Live</SystemBadge><p>{{ user }}</p></div>
      </div>
    </aside>

    <div class="app-shell__main">
      <header class="app-shell__header">
        <div><p class="app-shell__header-label">Kitchen stock</p><p class="app-shell__header-note">Receipts, meal use, and physical counts</p></div>
        <SystemOperationalButton class="app-shell__refresh" variant="subtle" size="md" :loading="busy" loading-text="Refreshing" @click="$emit('refresh')">Refresh stock</SystemOperationalButton>
      </header>

      <nav class="app-shell__nav" aria-label="Main stock flow">
        <div class="app-shell__nav-inner">
        <SystemOperationalButton
          v-for="section in sections.filter(section => section.id !== 'export')"
          :key="section.id"
          class="app-shell__nav-button"
          :class="{ 'is-active': activeSection === section.id }"
          :aria-current="activeSection === section.id ? 'page' : undefined"
          variant="subtle"
          size="lg"
          @click="$emit('navigate', section.id)"
        >
          <span class="app-shell__nav-number">{{ section.number }}</span>
          <span>{{ section.label }}</span>
        </SystemOperationalButton>
        </div>
      </nav>

      <main class="app-shell__work" tabindex="-1"><slot /></main>
    </div>
  </section>
</template>

<style scoped>
.app-shell{display:grid;grid-template-columns:15rem minmax(0,1fr);min-height:100vh;background:var(--theme-canvas);color:var(--theme-text);transition:grid-template-columns .18s ease}.app-shell--collapsed{grid-template-columns:4.5rem minmax(0,1fr)}.app-shell__sidebar{position:sticky;top:0;z-index:20;display:flex;flex-direction:column;height:100vh;padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border);background:var(--theme-secondary)}.app-shell__brand{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-xs);min-height:4rem;padding:var(--spacing-xs) var(--spacing-2xs) var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border)}.app-shell__kicker,.app-shell__descriptor,.app-shell__sidebar p,.app-shell__header p{margin:0}.app-shell__kicker{font-size:var(--font-size-0);font-weight:var(--font-weight-700)}.app-shell__descriptor{margin-top:var(--spacing-3xs);color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__collapse{flex:0 0 2.25rem!important;width:2.25rem!important;height:2.25rem!important;min-height:2.25rem!important;padding:0!important;border:0!important;background:var(--theme-surface)!important;color:var(--theme-text)!important}.app-shell__utility-nav{display:grid;gap:var(--spacing-3xs);padding-top:var(--spacing-s)}.app-shell__nav-label{padding:0 var(--spacing-2xs) var(--spacing-2xs);color:var(--theme-text-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.app-shell__utility-link{display:grid;grid-template-columns:2rem minmax(0,1fr) auto;align-items:center;gap:var(--spacing-2xs);min-height:2.75rem;padding:0 var(--spacing-2xs);border-radius:var(--component-radius-button);color:var(--theme-text-muted);font-size:var(--font-size--1);text-decoration:none}.app-shell__utility-link:hover{background:var(--theme-surface);color:var(--theme-text)}.app-shell__utility-icon{display:grid;place-items:center;width:2rem;height:2rem;border-radius:8px;background:var(--theme-surface);color:var(--theme-text);font-size:.68rem;font-weight:var(--font-weight-700);letter-spacing:.04em}.app-shell__sidebar-bottom{display:grid;gap:var(--spacing-s);margin-top:auto}.app-shell__export-button{justify-content:flex-start!important;width:100%;gap:var(--spacing-xs)!important}.app-shell__session-copy{display:grid;gap:var(--spacing-2xs);min-width:0;padding:var(--spacing-s) var(--spacing-2xs) 0;border-top:var(--border-width-1) solid var(--theme-border);color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__session-copy p{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-shell--collapsed :is(.app-shell__brand>div,.app-shell__nav-label,.app-shell__utility-label,.app-shell__utility-arrow,.app-shell__session-copy p){display:none}.app-shell--collapsed .app-shell__brand{justify-content:center;padding-inline:0}.app-shell--collapsed .app-shell__utility-link{grid-template-columns:1fr;justify-items:center;padding:0}.app-shell--collapsed .app-shell__export-button{justify-content:center!important;padding-inline:0!important}.app-shell__main{min-width:0}.app-shell__header{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-m);min-height:4.5rem;padding:var(--spacing-xs) var(--spacing-m);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface)}.app-shell__header-label{font-weight:var(--font-weight-650)}.app-shell__header-note{margin-top:var(--spacing-3xs)!important;color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__refresh{width:auto!important;min-width:7.5rem!important;max-width:9rem!important;min-height:2.5rem!important;white-space:nowrap}.app-shell__refresh :deep(svg),.app-shell__refresh :deep([data-slot="loading"]){flex:0 0 1rem!important;width:1rem!important;height:1rem!important;max-width:1rem!important;max-height:1rem!important}.app-shell__nav{position:sticky;top:0;z-index:10;overflow-x:auto;border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface)}.app-shell__nav-inner{display:flex;gap:var(--spacing-2xs);width:min(100%,90rem);margin-inline:auto;padding:var(--spacing-xs) var(--spacing-m)}.app-shell__nav :deep(.app-shell__nav-button){position:relative;flex:0 0 auto;gap:var(--spacing-2xs)!important;min-height:2.75rem!important;padding-inline:var(--spacing-s)!important;border:var(--border-width-1) solid transparent!important;border-radius:var(--component-radius-button)!important;background:var(--theme-secondary)!important;color:var(--theme-text-muted)!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button:hover){border-color:var(--theme-border)!important;background:var(--theme-surface-raised)!important;color:var(--theme-text)!important}.app-shell__nav :deep(.app-shell__nav-button:focus-visible){outline:2px solid var(--theme-text)!important;outline-offset:2px!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button.is-active){border-color:var(--theme-border)!important;background:var(--theme-surface-raised)!important;color:var(--theme-text)!important;box-shadow:0 1px 2px color-mix(in oklch,var(--theme-text) 10%,transparent)!important}.app-shell__nav :deep(.app-shell__nav-button.is-active)::after{position:absolute;right:var(--spacing-s);bottom:-.42rem;left:var(--spacing-s);height:2px;border-radius:999px;background:var(--theme-primary);content:""}.app-shell__nav-number{color:var(--theme-text-muted);font-size:var(--font-size--2);font-variant-numeric:tabular-nums}.app-shell__work{min-width:0;min-height:calc(100vh - 8rem);background:var(--theme-canvas)}.status-badge{width:max-content}.app-shell__export-button.is-active{background:var(--theme-surface)!important;color:var(--theme-text)!important}
@media(max-width:64rem){.app-shell,.app-shell--collapsed{grid-template-columns:1fr;width:100%;max-width:100vw;overflow-x:clip}.app-shell__sidebar{position:static;width:100%;height:auto;padding:var(--spacing-xs) var(--spacing-s);border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.app-shell__brand{min-height:3rem;padding:0}.app-shell__brand>div,.app-shell--collapsed .app-shell__brand>div{display:block}.app-shell__utility-nav{display:flex;overflow-x:auto;gap:var(--spacing-3xs);padding-top:var(--spacing-xs)}.app-shell__nav-label{display:none}.app-shell__utility-link,.app-shell--collapsed .app-shell__utility-link{flex:0 0 auto;grid-template-columns:2rem auto;padding-inline:var(--spacing-2xs)}.app-shell__utility-arrow{display:none}.app-shell__sidebar-bottom{display:none}}
@media(max-width:44rem){.app-shell__header{min-height:4rem;padding:var(--spacing-xs) var(--spacing-s)}.app-shell__header-note{display:none}.app-shell__nav-inner{width:max-content;min-width:100%;padding-inline:var(--spacing-s)}.app-shell__nav :deep(.app-shell__nav-button){min-width:max-content}}
</style>
