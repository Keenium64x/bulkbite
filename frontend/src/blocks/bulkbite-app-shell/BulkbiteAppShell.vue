<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  BadgeDollarSign,
  ClipboardCheck,
  ChevronRight,
  CookingPot,
  FileText,
  LogIn,
  LogOut,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Truck,
  UsersRound,
  UserRound,
} from "lucide-vue-next"
import {
  SystemCard,
  SystemLink,
  SystemOperationalButton,
} from "@/desyium"
import { mountFlipLayoutTransition } from "@/experiences/bulkbite-nav-expand"

// =============================================================================
// region SHELL CONTRACT
// =============================================================================

const props = defineProps({
  sections: { type: Array, required: true },
  theoreticalContextSections: { type: Array, default: () => ["prices"] },
  sidebarGroups: { type: Array, default: () => [
    { label: "Daily tools", links: [
      { label: "Employees", icon: UsersRound, href: "/bulkbite?work=employees", target: { mode: "workflow", id: "employees" } },
      { label: "Worker sheets", icon: FileText, href: "/bulkbite?work=documents", target: { mode: "workflow", id: "documents" } },
      { label: "Price catalogue", icon: BadgeDollarSign, href: "/bulkbite/prices", target: { mode: "route", href: "/bulkbite/prices" } },
      { label: "Stock count", icon: ClipboardCheck, href: "/bulkbite?work=stock", target: { mode: "workflow", id: "stock" } },
    ] },
    { label: "Manage", links: [
      { label: "Items", icon: Package, href: "/bulkbite/setup/BulkBite%20Item", target: { mode: "list", doctype: "BulkBite Item" } },
      { label: "Recipes", icon: CookingPot, href: "/bulkbite/setup/BulkBite%20Recipe", target: { mode: "list", doctype: "BulkBite Recipe" } },
      { label: "Suppliers", icon: Truck, href: "/bulkbite/setup/BulkBite%20Supplier", target: { mode: "list", doctype: "BulkBite Supplier" } },
      { label: "Teams", icon: UsersRound, href: "/bulkbite/setup/BulkBite%20Team%20Template", target: { mode: "list", doctype: "BulkBite Team Template" } },
    ] },
  ] },
  activeSection: { type: String, required: true },
  user: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  sessionBusy: { type: Boolean, default: false },
})

const emit = defineEmits(["navigate", "refresh", "logout"])

// endregion SHELL CONTRACT

// =============================================================================
// region SIDEBAR STATE
// =============================================================================

const sidebarCollapsed = ref(window.localStorage.getItem("bulkbite-sidebar") === "collapsed")
const navGroupsRoot = ref(null)
const theoreticalExpanded = ref(false)
let flipExperience = null
const primarySections = computed(() => props.sections.filter(section => section.group !== "theoretical"))
const theoreticalSections = computed(() => props.sections.filter(section => section.group === "theoretical"))
const theoreticalActive = computed(() => theoreticalSections.value.some(section => section.id === props.activeSection) || props.theoreticalContextSections.includes(props.activeSection))
const theoreticalLinksVisible = computed(() => theoreticalExpanded.value)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  window.localStorage.setItem("bulkbite-sidebar", sidebarCollapsed.value ? "collapsed" : "expanded")
}

async function toggleTheoretical() {
  const mutate = async () => {
    theoreticalExpanded.value = !theoreticalLinksVisible.value
    await nextTick()
  }

  if (flipExperience?.transition) {
    await flipExperience.transition(mutate)
    return
  }

  await mutate()
}

function navigateSidebar(target) {
  emit("navigate", target)
}

function sidebarLinkIsActive(link) {
  if (link.target.mode === "workflow") return props.activeSection === link.target.id
  if (link.target.mode === "route") return window.location.pathname === link.target.href
  return false
}

watch(theoreticalActive, (isActive) => {
  if (isActive) theoreticalExpanded.value = true
}, { immediate: true })

onMounted(() => {
  if (!navGroupsRoot.value) return
  flipExperience = mountFlipLayoutTransition(navGroupsRoot.value, {
    items: "[data-flip-id]",
    duration: 0.32,
    ease: "power2.out",
    absolute: false,
  })
})

onBeforeUnmount(() => {
  flipExperience?.destroy()
  flipExperience = null
})

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

      <div class="app-shell__sidebar-navigation">
        <nav v-for="group in sidebarGroups" :key="group.label" class="app-shell__utility-nav" :aria-label="group.label">
          <p class="app-shell__nav-label">{{ group.label }}</p>
          <SystemLink v-for="link in group.links" :key="link.href" :href="link.href" class="app-shell__utility-link" :class="{ 'is-active': sidebarLinkIsActive(link) }" :title="sidebarCollapsed ? link.label : undefined" :aria-label="sidebarCollapsed ? link.label : undefined" @click.prevent="navigateSidebar(link.target)">
            <span class="app-shell__sidebar-icon" aria-hidden="true"><component :is="link.icon || Settings" /></span>
            <span class="app-shell__utility-label">{{ link.label }}</span>
            <ChevronRight class="app-shell__utility-arrow" aria-hidden="true" />
          </SystemLink>
        </nav>
        <nav class="app-shell__utility-nav app-shell__utility-nav--all" aria-label="All setup records">
          <SystemLink href="/bulkbite/setup" class="app-shell__utility-link" :title="sidebarCollapsed ? 'All setup' : undefined" :aria-label="sidebarCollapsed ? 'All setup' : undefined" @click.prevent="navigateSidebar({ mode: 'catalogue' })">
            <span class="app-shell__sidebar-icon" aria-hidden="true"><Settings /></span>
            <span class="app-shell__utility-label">All setup</span>
            <ChevronRight class="app-shell__utility-arrow" aria-hidden="true" />
          </SystemLink>
        </nav>
      </div>

      <footer class="app-shell__sidebar-footer">
        <section class="app-shell__account" aria-label="Account">
          <div class="app-shell__account-user" :title="sidebarCollapsed ? (user || 'Guest') : undefined">
            <span class="app-shell__account-avatar" aria-hidden="true"><UserRound /></span>
            <div class="app-shell__account-copy">
              <p>{{ user && user !== 'Guest' ? user : 'Guest' }}</p>
            </div>
          </div>

          <SystemOperationalButton v-if="user && user !== 'Guest'" class="app-shell__sidebar-action app-shell__session-action" variant="ghost" :loading="sessionBusy && !sidebarCollapsed" loading-text="Signing out" label="Log out" :tooltip="sidebarCollapsed ? 'Log out' : undefined" :aria-label="sidebarCollapsed ? 'Log out' : undefined" @click="$emit('logout')">
            <span v-if="sessionBusy && sidebarCollapsed" class="app-shell__session-loader" aria-hidden="true" />
            <LogOut v-else aria-hidden="true" />
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
          <SystemOperationalButton class="app-shell__refresh" variant="subtle" size="md" :disabled="busy" :aria-busy="busy" :label="busy ? 'Refreshing BulkBite data' : 'Refresh BulkBite data'" @click="$emit('refresh')">
            <span v-if="busy" class="app-shell__refresh-loader" aria-hidden="true" />
            <span>{{ busy ? 'Refreshing' : 'Refresh' }}</span>
          </SystemOperationalButton>
        </header>

        <nav class="app-shell__nav" aria-label="Main stock flow">
          <div ref="navGroupsRoot" class="app-shell__nav-inner app-shell__nav-groups" data-nav-groups>
            <section class="app-shell__nav-category app-shell__nav-category--actual" aria-labelledby="actual-nav-label" data-flip-id="actual-category">
              <p id="actual-nav-label" class="app-shell__category-label">Actual</p>
              <SystemCard class="app-shell__category-card">
                <div class="app-shell__category-controls">
                  <SystemOperationalButton v-for="section in primarySections" :key="section.id" :data-flip-id="`actual-${section.id}`" class="app-shell__nav-button" :class="{ 'is-active': activeSection === section.id }" :aria-current="activeSection === section.id ? 'page' : undefined" variant="subtle" size="lg" @click="$emit('navigate', section.id)">
                    <span>{{ section.label }}</span>
                  </SystemOperationalButton>
                </div>
              </SystemCard>
            </section>

            <section v-if="theoreticalSections.length" class="app-shell__nav-category app-shell__nav-category--theoretical" aria-labelledby="theoretical-nav-label" data-flip-id="theoretical-category">
              <p id="theoretical-nav-label" class="app-shell__category-label">Theoretical</p>
              <SystemCard class="app-shell__category-card">
                <div class="app-shell__category-controls">
                  <SystemOperationalButton class="app-shell__nav-button app-shell__expand-button" :class="{ 'is-active': theoreticalActive }" :aria-expanded="theoreticalLinksVisible" aria-controls="theoretical-workflows" variant="subtle" size="lg" data-flip-id="theoretical-toggle" @click="toggleTheoretical">
                    <span>{{ theoreticalLinksVisible ? 'Collapse' : 'Expand' }}</span>
                  </SystemOperationalButton>
                  <div v-if="theoreticalLinksVisible" id="theoretical-workflows" class="app-shell__theoretical-controls" aria-label="Theoretical workflows">
                    <SystemOperationalButton v-for="section in theoreticalSections" :key="section.id" :data-flip-id="`theoretical-${section.id}`" class="app-shell__nav-button" :class="{ 'is-active': activeSection === section.id }" :aria-current="activeSection === section.id ? 'page' : undefined" variant="subtle" size="lg" @click="$emit('navigate', section.id)">
                      <span>{{ section.label }}</span>
                    </SystemOperationalButton>
                  </div>
                </div>
              </SystemCard>
            </section>
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
@media(max-width:44rem){.app-shell__sidebar-footer{grid-template-columns:1fr}.app-shell__account{grid-template-columns:minmax(0,1fr) auto}.app-shell__export-button{width:100%}.app-shell__header-note{display:none}.app-shell__refresh{flex-basis:7.75rem!important;width:7.75rem!important;min-width:7.75rem!important;max-width:7.75rem!important}.app-shell__nav-inner{gap:var(--spacing-3xs);width:100%;min-width:0;padding-inline:var(--spacing-xs)}.app-shell__nav :deep(.app-shell__nav-button){min-width:max-content;padding-inline:var(--spacing-3xs)!important;font-size:var(--font-size--2)!important}}
.app-shell__refresh :deep(svg){display:inline-block!important;flex:0 0 .875rem!important;width:.875rem!important;height:.875rem!important;min-width:.875rem!important;min-height:.875rem!important;max-width:.875rem!important;max-height:.875rem!important;scale:1!important;transform-origin:center!important}
.app-shell__refresh-loader{display:block;flex:0 0 .75rem;width:.75rem;height:.75rem;border:1.5px solid currentColor;border-right-color:transparent;border-radius:999px;animation:app-shell-spin .7s linear infinite}@keyframes app-shell-spin{to{transform:rotate(360deg)}}
:deep(.app-shell__collapse){border:var(--border-width-1) solid var(--theme-navigation-sidebar-border)!important;background:var(--theme-navigation-sidebar-control)!important;color:var(--theme-navigation-sidebar-text)!important}:deep(.app-shell__collapse svg){width:1rem!important;height:1rem!important;stroke:currentColor!important}:deep(.app-shell__sidebar-action){color:var(--theme-navigation-sidebar-muted)!important}:deep(.app-shell__sidebar-action > span.truncate){display:flex!important;align-items:center!important;gap:var(--spacing-xs)!important;width:100%;height:auto!important;overflow:visible!important}:deep(.app-shell__sidebar-action > span.truncate svg),:deep(.app-shell__session-link svg){flex:0 0 1.05rem!important;width:1.05rem!important;height:1.05rem!important;stroke:currentColor!important}:deep(.app-shell__export-button:hover),:deep(.app-shell__export-button.is-active),:deep(.app-shell__session-action:hover){background:var(--theme-navigation-sidebar-hover)!important;color:var(--theme-navigation-sidebar-text)!important}:deep(.app-shell__refresh){flex:0 0 8.75rem!important;width:8.75rem!important;min-width:8.75rem!important;max-width:8.75rem!important;height:2.75rem!important;min-height:2.75rem!important;max-height:2.75rem!important;border-color:var(--theme-navigation-header-border)!important;background:var(--theme-navigation-header-control)!important;color:var(--theme-navigation-header-text)!important}.app-shell__refresh :deep(> span.truncate){display:flex;align-items:center;justify-content:center;gap:var(--spacing-2xs);width:100%;overflow:visible;color:inherit!important}.app-shell__refresh :deep(> span.truncate > span:last-child){min-width:5.25rem;text-align:left}.app-shell__account-copy{display:block}.app-shell__account-copy p{font-size:var(--font-size--2);font-weight:var(--font-weight-600)}
@media(min-width:64.0625rem){.app-shell__account{grid-template-columns:minmax(0,1fr) 2.25rem;align-items:center;padding:var(--spacing-2xs)}:deep(.app-shell__session-action),:deep(.app-shell__session-link){display:flex!important;align-items:center!important;justify-content:center!important;flex:0 0 2.25rem!important;width:2.25rem!important;min-width:2.25rem!important;height:2.25rem!important;min-height:2.25rem!important;padding:0!important;white-space:nowrap}:deep(.app-shell__session-action > span.truncate){justify-content:center!important;gap:0!important}:deep(.app-shell__session-action > span.truncate svg){flex:0 0 1rem!important;width:1rem!important;height:1rem!important}.app-shell__session-label{display:none!important}}
.app-shell__session-loader{display:block;flex:0 0 .8rem;width:.8rem;height:.8rem;border:1.5px solid currentColor;border-right-color:transparent;border-radius:999px;animation:app-shell-spin .7s linear infinite}
@media(min-width:64.0625rem){.app-shell--collapsed .app-shell__sidebar{padding-inline:var(--spacing-2xs)}.app-shell--collapsed .app-shell__account{display:grid;grid-template-columns:2.5rem;justify-content:center;justify-items:center;gap:var(--spacing-2xs);padding:var(--spacing-2xs)}.app-shell--collapsed .app-shell__account-user{display:grid;grid-template-columns:2.5rem;width:2.5rem;height:2.5rem}.app-shell--collapsed .app-shell__account-avatar{width:2.5rem;height:2.5rem}.app-shell--collapsed :deep(.app-shell__session-action),.app-shell--collapsed .app-shell__session-link{display:flex!important;flex:0 0 2.5rem!important;width:2.5rem!important;min-width:2.5rem!important;max-width:2.5rem!important;height:2.5rem!important;min-height:2.5rem!important;max-height:2.5rem!important;padding:0!important;overflow:hidden!important}}

.app-shell__sidebar-navigation{min-height:0;overflow-y:auto;padding-bottom:var(--spacing-s)}
.app-shell__sidebar-navigation{scrollbar-width:thin;scrollbar-color:var(--theme-navigation-sidebar-control) transparent}
.app-shell__sidebar-navigation::-webkit-scrollbar{width:.5rem;height:.5rem}
.app-shell__sidebar-navigation::-webkit-scrollbar-track{background:transparent}
.app-shell__sidebar-navigation::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background:var(--theme-navigation-sidebar-control);background-clip:padding-box}
.app-shell__sidebar-navigation::-webkit-scrollbar-thumb:hover{background:var(--theme-navigation-sidebar-hover);background-clip:padding-box}
.app-shell__sidebar-navigation .app-shell__utility-nav + .app-shell__utility-nav{margin-top:var(--spacing-s);padding-top:var(--spacing-s);border-top:var(--border-width-1) solid var(--theme-navigation-sidebar-border)}
.app-shell__utility-nav--all{margin-top:var(--spacing-xs)!important;padding-top:var(--spacing-xs)!important}
.app-shell__utility-link.is-active{background:var(--theme-navigation-sidebar-hover);color:var(--theme-navigation-sidebar-text)}
.app-shell__nav-groups{align-items:flex-end;gap:var(--spacing-s);width:max-content;min-width:min(100%,90rem)}
.app-shell__nav-category{display:grid;flex:0 0 auto;gap:var(--spacing-3xs);min-width:0}
.app-shell__category-label{margin:0;padding-left:var(--spacing-xs);color:var(--theme-navigation-header-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-600);line-height:1.25}
.app-shell__category-card{overflow:visible!important;padding:var(--spacing-2xs)!important;border:var(--border-width-1) solid var(--theme-navigation-header-border)!important;border-radius:var(--component-radius-card)!important;box-shadow:none!important}
.app-shell__nav-category--actual{--app-shell-category-accent:var(--theme-success);--app-shell-category-surface:color-mix(in oklch,var(--theme-success) 18%,var(--theme-surface-raised));--app-shell-category-border:color-mix(in oklch,var(--theme-success) 52%,var(--theme-border));--app-shell-category-control:color-mix(in oklch,var(--theme-success) 7%,var(--theme-surface-raised));--app-shell-category-control-hover:color-mix(in oklch,var(--theme-success) 15%,var(--theme-surface-raised));--app-shell-category-label:var(--theme-navigation-header-text)}
.app-shell__nav-category--theoretical{--app-shell-category-accent:var(--theme-info);--app-shell-category-surface:color-mix(in oklch,var(--theme-info) 17%,var(--theme-surface-raised));--app-shell-category-border:color-mix(in oklch,var(--theme-info) 48%,var(--theme-border));--app-shell-category-control:color-mix(in oklch,var(--theme-info) 6%,var(--theme-surface-raised));--app-shell-category-control-hover:color-mix(in oklch,var(--theme-info) 14%,var(--theme-surface-raised));--app-shell-category-label:var(--theme-navigation-header-text)}
.app-shell__nav-category .app-shell__category-label{color:var(--app-shell-category-label)}
.app-shell__nav-category .app-shell__category-card{border-color:var(--app-shell-category-border)!important;background:var(--app-shell-category-surface)!important}
.app-shell__category-controls,.app-shell__theoretical-controls{display:flex;align-items:center;gap:var(--spacing-3xs);min-width:0}
.app-shell__theoretical-controls{transform-origin:left center}
.app-shell__nav :deep(.app-shell__nav-category .app-shell__nav-button){padding-inline:var(--spacing-2xs)!important;border-color:color-mix(in oklch,var(--app-shell-category-accent) 24%,var(--theme-border))!important;background:var(--app-shell-category-control)!important;color:var(--theme-text)!important;font-size:var(--font-size--1)!important}
.app-shell__nav :deep(.app-shell__nav-category .app-shell__nav-button:hover){border-color:color-mix(in oklch,var(--app-shell-category-accent) 44%,var(--theme-navigation-header-border))!important;background:var(--app-shell-category-control-hover)!important}
.app-shell__nav :deep(.app-shell__nav-category .app-shell__nav-button.is-active){border-color:color-mix(in oklch,var(--app-shell-category-accent) 48%,var(--theme-navigation-active-border))!important;background:var(--theme-navigation-active)!important;color:var(--theme-navigation-active-text)!important}
.app-shell__expand-button{min-width:5.25rem!important}
@media(max-width:64rem){.app-shell__sidebar-navigation{display:flex;overflow-x:auto;overflow-y:hidden;gap:var(--spacing-xs);padding-bottom:var(--spacing-2xs)}.app-shell__sidebar-navigation .app-shell__utility-nav,.app-shell__sidebar-navigation .app-shell__utility-nav + .app-shell__utility-nav{flex:0 0 auto;margin:0;padding-top:var(--spacing-xs);border-top:0}.app-shell__utility-nav--all{padding-top:var(--spacing-xs)!important}.app-shell__nav-groups{width:max-content;min-width:100%}}
@media(max-width:44rem){.app-shell__nav{overflow-x:hidden}.app-shell__nav-groups{display:grid;width:100%;min-width:0}.app-shell__nav-category{width:100%}.app-shell__category-controls,.app-shell__theoretical-controls{flex-wrap:wrap}.app-shell__theoretical-controls{display:contents}.app-shell__nav :deep(.app-shell__nav-button){flex:1 1 auto;min-width:5.5rem!important;padding-inline:var(--spacing-xs)!important}.app-shell__category-card{width:100%}}
</style>
