<script setup>
import { SystemBadge, SystemOperationalButton } from "@/desyium"

defineProps({
  sections: { type: Array, required: true },
  activeSection: { type: String, required: true },
  user: { type: String, default: "" },
  busy: { type: Boolean, default: false },
})

defineEmits(["navigate", "refresh"])
</script>

<template>
  <section data-block="bulkbite-app-shell" class="app-shell">
    <aside class="app-shell__rail" aria-label="BulkBite workflows">
      <div class="app-shell__brand">
        <span class="app-shell__bite" aria-hidden="true">B</span>
        <div>
          <p class="app-shell__kicker">BulkBite</p>
          <p class="app-shell__descriptor">Stock operations</p>
        </div>
      </div>

      <nav class="app-shell__nav">
        <SystemOperationalButton
          v-for="section in sections"
          :key="section.id"
          class="app-shell__nav-button"
          :class="{ 'is-active': activeSection === section.id }"
          :aria-current="activeSection === section.id ? 'page' : undefined"
          variant="ghost"
          size="lg"
          @click="$emit('navigate', section.id)"
        >
          <span>{{ section.label }}</span>
        </SystemOperationalButton>
      </nav>

      <div class="app-shell__session">
        <SystemBadge class="status-badge">SIGNED IN</SystemBadge>
        <p>{{ user }}</p>
        <SystemOperationalButton variant="outline" :loading="busy" @click="$emit('refresh')">
          Refresh stock
        </SystemOperationalButton>
      </div>
    </aside>

    <main class="app-shell__work" tabindex="-1">
      <slot />
    </main>
  </section>
</template>

<style scoped>
.app-shell{display:grid;grid-template-columns:14rem minmax(0,1fr);min-height:100vh;background:var(--theme-canvas);color:var(--theme-text)}.app-shell__rail{position:sticky;top:0;z-index:10;display:flex;flex-direction:column;gap:var(--spacing-m);height:100vh;padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.app-shell__brand{display:flex;align-items:center;gap:var(--spacing-xs);padding-bottom:var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border)}.app-shell__bite{display:grid;place-items:center;width:2.25rem;height:2.25rem;border-radius:var(--component-radius-button);background:var(--theme-primary);color:var(--theme-primary-foreground);font-weight:var(--font-weight-700)}.app-shell__kicker,.app-shell__descriptor,.app-shell__session p{margin:0}.app-shell__kicker{font-weight:var(--font-weight-700)}.app-shell__descriptor{margin-top:var(--spacing-3xs);color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__nav{display:grid;gap:var(--spacing-3xs);align-content:start}.app-shell__nav :deep(.app-shell__nav-button){justify-content:flex-start!important;width:100%;border-left:var(--border-width-3) solid transparent!important;background:transparent!important;color:var(--theme-text)!important}.app-shell__nav :deep(.app-shell__nav-button:hover){background:var(--theme-canvas)!important}.app-shell__nav :deep(.app-shell__nav-button.is-active){border-left-color:var(--theme-primary)!important;background:color-mix(in oklch,var(--theme-primary) 12%,var(--theme-surface-raised))!important;color:var(--theme-text)!important}.app-shell__session{display:grid;gap:var(--spacing-xs);margin-top:auto;color:var(--theme-text-muted);font-size:var(--font-size--2);overflow-wrap:anywhere}.app-shell__work{min-width:0;min-height:100vh;background:var(--theme-canvas)}.status-badge{width:max-content}
@media(max-width:64rem){.app-shell{grid-template-columns:1fr}.app-shell__rail{position:sticky;height:auto;padding:var(--spacing-xs-s);border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border);gap:var(--spacing-xs)}.app-shell__brand{padding-bottom:var(--spacing-xs)}.app-shell__nav{display:flex;overflow-x:auto;gap:var(--spacing-3xs);padding-bottom:var(--spacing-3xs)}.app-shell__nav :deep(.app-shell__nav-button){width:auto;min-width:max-content}.app-shell__session{display:none}}
</style>
