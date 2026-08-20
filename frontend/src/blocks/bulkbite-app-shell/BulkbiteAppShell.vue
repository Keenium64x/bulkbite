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
    <header class="app-shell__header">
      <div class="app-shell__brand">
        <div>
          <p class="app-shell__kicker">BulkBite Stock</p>
          <p class="app-shell__descriptor">Kitchen operations</p>
        </div>
      </div>

      <div class="app-shell__session">
        <div class="app-shell__session-copy">
          <SystemBadge class="status-badge">Live stock</SystemBadge>
          <p>{{ user }}</p>
        </div>
        <SystemOperationalButton variant="outline" :loading="busy" @click="$emit('refresh')">
          Refresh
        </SystemOperationalButton>
      </div>
    </header>

    <nav class="app-shell__nav" aria-label="BulkBite workflows">
      <div class="app-shell__nav-inner">
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
          <span class="app-shell__nav-number">{{ section.number }}</span>
          <span>{{ section.label }}</span>
        </SystemOperationalButton>
      </div>
    </nav>

    <main class="app-shell__work" tabindex="-1">
      <slot />
    </main>
  </section>
</template>

<style scoped>
.app-shell{min-height:100vh;background:var(--theme-canvas);color:var(--theme-text)}.app-shell__header{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-m);min-height:4.5rem;padding:var(--spacing-xs) max(var(--spacing-m),calc((100vw - 90rem)/2 + var(--spacing-m)));border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.app-shell__brand{display:flex;align-items:center;min-width:max-content}.app-shell__kicker,.app-shell__descriptor,.app-shell__session p{margin:0}.app-shell__kicker{font-size:var(--font-size-0);font-weight:var(--font-weight-700)}.app-shell__descriptor{margin-top:var(--spacing-3xs);color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__session,.app-shell__session-copy{display:flex;align-items:center;gap:var(--spacing-xs)}.app-shell__session{color:var(--theme-text-muted);font-size:var(--font-size--2)}.app-shell__session-copy{min-width:0}.app-shell__session p{max-width:18rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-shell__nav{position:sticky;top:0;z-index:10;overflow-x:auto;border-bottom:var(--border-width-1) solid var(--theme-border);background:color-mix(in oklch,var(--theme-surface-raised) 94%,transparent);backdrop-filter:blur(10px)}.app-shell__nav-inner{display:flex;gap:var(--spacing-3xs);width:min(100%,90rem);margin-inline:auto;padding:var(--spacing-2xs) var(--spacing-m)}.app-shell__nav :deep(.app-shell__nav-button){flex:0 0 auto;gap:var(--spacing-2xs)!important;min-height:2.75rem!important;border:var(--border-width-1) solid transparent!important;border-radius:var(--component-radius-button)!important;background:transparent!important;color:var(--theme-text-muted)!important}.app-shell__nav :deep(.app-shell__nav-button:hover){background:var(--theme-secondary)!important;color:var(--theme-text)!important}.app-shell__nav :deep(.app-shell__nav-button.is-active){border-color:var(--theme-border)!important;background:var(--theme-surface-raised)!important;color:var(--theme-text)!important;box-shadow:var(--shadow-1)}.app-shell__nav-number{color:var(--theme-text-muted);font-size:var(--font-size--2);font-variant-numeric:tabular-nums}.app-shell__work{min-width:0;min-height:calc(100vh - 8rem);background:var(--theme-canvas)}.status-badge{width:max-content}
@media(max-width:44rem){.app-shell__header{min-height:4rem;padding:var(--spacing-xs) var(--spacing-s)}.app-shell__descriptor,.app-shell__session-copy{display:none}.app-shell__session{gap:0}.app-shell__nav-inner{width:max-content;min-width:100%;padding-inline:var(--spacing-s)}.app-shell__nav :deep(.app-shell__nav-button){min-width:max-content}}
</style>
