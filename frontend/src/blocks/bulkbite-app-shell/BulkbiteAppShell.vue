<script setup>
import { SystemBadge, SystemLink, SystemOperationalButton } from "@/desyium"

defineProps({
  sections: { type: Array, required: true },
  setupLinks: { type: Array, default: () => [
    { label: "Items", href: "/app/bulkbite-item" },
    { label: "Recipes", href: "/app/bulkbite-recipe" },
    { label: "Suppliers", href: "/app/bulkbite-supplier" },
    { label: "Locations", href: "/app/bulkbite-location" },
    { label: "Meal plans", href: "/app/bulkbite-production-plan" },
  ] },
  activeSection: { type: String, required: true },
  user: { type: String, default: "" },
  busy: { type: Boolean, default: false },
})

defineEmits(["navigate", "refresh"])
</script>

<template>
  <section data-block="bulkbite-app-shell" class="app-shell">
    <aside class="app-shell__sidebar" aria-label="BulkBite setup and tools">
      <div class="app-shell__brand">
        <div>
          <p class="app-shell__kicker">BulkBite Stock</p>
          <p class="app-shell__descriptor">Kitchen operations</p>
        </div>
      </div>

      <nav class="app-shell__utility-nav" aria-label="Setup">
        <p class="app-shell__nav-label">Setup</p>
        <SystemLink v-for="link in setupLinks" :key="link.href" :href="link.href" class="app-shell__utility-link">
          <span>{{ link.label }}</span><span aria-hidden="true">›</span>
        </SystemLink>
      </nav>

      <div class="app-shell__sidebar-bottom">
        <SystemOperationalButton class="app-shell__export-button" :class="{ 'is-active': activeSection === 'export' }" variant="ghost" @click="$emit('navigate', 'export')">Accountant export</SystemOperationalButton>
        <div class="app-shell__session-copy"><SystemBadge class="status-badge">Live</SystemBadge><p>{{ user }}</p></div>
      </div>
    </aside>

    <div class="app-shell__main">
      <header class="app-shell__header">
        <div><p class="app-shell__header-label">Kitchen stock</p><p class="app-shell__header-note">Receipts, meal use, and physical counts</p></div>
        <SystemOperationalButton class="app-shell__refresh" variant="outline" size="md" :loading="busy" loading-text="Refreshing" @click="$emit('refresh')">Refresh stock</SystemOperationalButton>
      </header>

      <nav class="app-shell__nav" aria-label="Main stock flow">
        <div class="app-shell__nav-inner">
        <SystemOperationalButton
          v-for="section in sections.filter(section => section.id !== 'export')"
          :key="section.id"
          class="app-shell__nav-button"
          :class="{ 'is-active': activeSection === section.id }"
          :aria-current="activeSection === section.id ? 'page' : undefined"
          variant="outline"
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
.app-shell{display:grid;grid-template-columns:13.5rem minmax(0,1fr);min-height:100vh;background:var(--theme-canvas);color:var(--theme-text)}.app-shell__sidebar{position:sticky;top:0;display:flex;flex-direction:column;height:100vh;padding:var(--spacing-m) var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.app-shell__brand{padding:0 var(--spacing-xs) var(--spacing-m);border-bottom:var(--border-width-1) solid var(--theme-border)}.app-shell__kicker,.app-shell__descriptor,.app-shell__sidebar p,.app-shell__header p{margin:0}.app-shell__kicker{font-size:var(--font-size-0);font-weight:var(--font-weight-700)}.app-shell__descriptor{margin-top:var(--spacing-3xs);color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__utility-nav{display:grid;gap:var(--spacing-3xs);padding-top:var(--spacing-m)}.app-shell__nav-label{padding:0 var(--spacing-xs) var(--spacing-2xs);color:var(--theme-text-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.app-shell__utility-link{display:flex;align-items:center;justify-content:space-between;min-height:2.5rem;padding:0 var(--spacing-xs);border-radius:var(--component-radius-button);color:var(--theme-text-muted);font-size:var(--font-size--1);text-decoration:none}.app-shell__utility-link:hover{background:var(--theme-secondary);color:var(--theme-text)}.app-shell__utility-link:focus-visible{outline-color:var(--theme-text)}.app-shell__sidebar-bottom{display:grid;gap:var(--spacing-s);margin-top:auto}.app-shell__export-button{justify-content:flex-start!important;width:100%}.app-shell__session-copy{display:grid;gap:var(--spacing-2xs);min-width:0;padding:var(--spacing-s) var(--spacing-xs) 0;border-top:var(--border-width-1) solid var(--theme-border);color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__session-copy p{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-shell__main{min-width:0}.app-shell__header{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-m);min-height:4.5rem;padding:var(--spacing-xs) var(--spacing-m);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.app-shell__header-label{font-weight:var(--font-weight-650)}.app-shell__header-note{margin-top:var(--spacing-3xs)!important;color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__refresh{width:auto!important;min-width:7.5rem!important;max-width:9rem!important;white-space:nowrap}.app-shell__refresh :deep(svg){flex:0 0 auto;max-width:1rem;max-height:1rem}.app-shell__nav{position:sticky;top:0;z-index:10;overflow-x:auto;border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.app-shell__nav-inner{display:flex;gap:var(--spacing-xs);width:min(100%,90rem);margin-inline:auto;padding:var(--spacing-xs) var(--spacing-m)}.app-shell__nav :deep(.app-shell__nav-button){position:relative;flex:0 0 auto;gap:var(--spacing-2xs)!important;min-height:2.75rem!important;padding-inline:var(--spacing-s)!important;border-color:var(--theme-border)!important;border-radius:var(--component-radius-button)!important;background:var(--theme-canvas)!important;color:var(--theme-text-muted)!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button:hover){border-color:color-mix(in oklch,var(--theme-text) 20%,var(--theme-border))!important;background:var(--theme-secondary)!important;color:var(--theme-text)!important}.app-shell__nav :deep(.app-shell__nav-button:focus-visible){outline:2px solid var(--theme-text)!important;outline-offset:2px!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button.is-active){border-color:var(--theme-text)!important;background:var(--theme-text)!important;color:var(--theme-surface-raised)!important}.app-shell__nav :deep(.app-shell__nav-button.is-active .app-shell__nav-number){color:color-mix(in oklch,var(--theme-surface-raised) 70%,transparent)}.app-shell__nav-number{color:var(--theme-text-muted);font-size:var(--font-size--2);font-variant-numeric:tabular-nums}.app-shell__work{min-width:0;min-height:calc(100vh - 8rem);background:var(--theme-canvas)}.status-badge{width:max-content}
@media(max-width:64rem){.app-shell{grid-template-columns:1fr;width:100%;max-width:100vw;overflow-x:clip}.app-shell__sidebar{position:static;width:100%;min-width:0;max-width:100vw;height:auto;padding:var(--spacing-xs) var(--spacing-s);overflow:hidden;border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.app-shell__brand{padding:0 0 var(--spacing-xs)}.app-shell__utility-nav{display:flex;width:100%;min-width:0;max-width:100%;overflow-x:auto;gap:var(--spacing-3xs);padding-top:var(--spacing-xs)}.app-shell__nav-label{display:none}.app-shell__utility-link{flex:0 0 auto}.app-shell__sidebar-bottom{display:none}}
@media(max-width:44rem){.app-shell__header{min-height:4rem;padding:var(--spacing-xs) var(--spacing-s)}.app-shell__header-note{display:none}.app-shell__nav-inner{width:max-content;min-width:100%;padding-inline:var(--spacing-s)}.app-shell__nav :deep(.app-shell__nav-button){min-width:max-content}}
.app-shell__header-label{font-weight:var(--font-weight-600)}.app-shell__export-button.is-active{background:var(--theme-secondary)!important;color:var(--theme-text)!important}
</style>
