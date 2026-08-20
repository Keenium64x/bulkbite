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
          <p class="app-shell__kicker">BULKBITE</p>
          <p class="app-shell__descriptor">STOCK TRUTH</p>
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
          <span class="app-shell__nav-number">{{ section.number }}</span>
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
.app-shell{min-height:100vh;background:var(--theme-canvas);color:var(--theme-text);display:grid;grid-template-columns:minmax(15rem,18rem) minmax(0,1fr)}.app-shell__rail{position:sticky;top:0;height:100vh;border-right:var(--border-width-2) solid var(--theme-primary);background:var(--theme-canvas);color:var(--theme-surface);padding:var(--spacing-s);display:flex;flex-direction:column;gap:var(--spacing-l);z-index:10}.app-shell__brand{display:flex;align-items:center;gap:var(--spacing-xs);border-bottom:var(--border-width-2) solid var(--theme-primary);padding-bottom:var(--spacing-s)}.app-shell__bite{display:grid;place-items:center;width:3rem;height:3rem;background:var(--theme-primary);color:var(--theme-primary-foreground);font:var(--font-weight-700) var(--font-size-2)/1 var(--font-family-a)}.app-shell__kicker,.app-shell__descriptor,.app-shell__session p{margin:0}.app-shell__kicker{color:var(--theme-primary);font:var(--font-weight-700) var(--font-size-1)/1 var(--font-family-a);letter-spacing:var(--font-letter-spacing-2)}.app-shell__descriptor{font-size:var(--font-size--2);letter-spacing:var(--font-letter-spacing-3)}.app-shell__nav{display:grid;gap:var(--spacing-3xs);align-content:start}.app-shell__nav-button{justify-content:flex-start!important;width:100%;color:var(--theme-surface)!important;background:transparent!important;border-left:var(--border-width-3) solid transparent!important}.app-shell__nav-button.is-active{background:var(--theme-primary)!important;color:var(--theme-primary-foreground)!important;border-left-color:var(--theme-surface)!important}.app-shell__nav-number{min-width:1.7rem;font-family:var(--font-family-c);font-size:var(--font-size--2)}.app-shell__session{margin-top:auto;display:grid;gap:var(--spacing-xs);font-size:var(--font-size--2);overflow-wrap:anywhere}.app-shell__work{min-width:0;background:var(--theme-surface);min-height:100vh}.status-badge{width:max-content;border-radius:0;background:var(--theme-primary);color:var(--theme-primary-foreground)}
@media(max-width:64rem){.app-shell{grid-template-columns:1fr}.app-shell__rail{position:sticky;height:auto;border-right:0;border-bottom:var(--border-width-2) solid var(--theme-primary);padding:var(--spacing-xs-s);gap:var(--spacing-xs)}.app-shell__brand{padding-bottom:var(--spacing-xs)}.app-shell__nav{display:flex;overflow-x:auto;gap:var(--spacing-3xs);padding-bottom:var(--spacing-3xs)}.app-shell__nav-button{width:auto;min-width:max-content}.app-shell__session{display:none}}
</style>
