<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  ChevronLeft,
  ChevronRight,
  CookingPot,
  Ellipsis,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  ReceiptText,
  Settings,
  Truck,
  UsersRound,
  UserRound,
  WalletCards,
  Warehouse,
  X,
} from "lucide-vue-next"
import {
  SystemCard,
  SystemDrawer,
  SystemDrawerClose,
  SystemDrawerContent,
  SystemDrawerDescription,
  SystemDrawerHeader,
  SystemDrawerTitle,
  SystemDrawerTrigger,
  SystemLink,
  SystemLogo,
  SystemOperationalButton,
} from "@/desyium"
import bulkbiteIcon from "@/assets/bulkbite-icon.svg"
import bulkbiteWordmark from "@/assets/bulkbite-logo-wordmark.svg"
import { mountFlipLayoutTransition } from "@/experiences/bulkbite-nav-expand"

// =============================================================================
// region SHELL CONTRACT
// =============================================================================

const props = defineProps({
  sections: { type: Array, required: true },
  theoreticalContextSections: { type: Array, default: () => ["prices"] },
  sidebarGroups: { type: Array, default: () => [
    { label: "Daily operations", links: [
      { label: "Dashboard", icon: LayoutDashboard, href: "/bulkbite?work=overview", target: { mode: "workflow", id: "overview" } },
      { label: "Receipt", icon: ReceiptText, href: "/bulkbite?work=receipts", target: { mode: "workflow", id: "receipts" } },
      { label: "Production", icon: CookingPot, href: "/bulkbite?work=production", target: { mode: "workflow", id: "production" } },
      { label: "Stock", icon: Warehouse, href: "/bulkbite?work=stock", target: { mode: "workflow", id: "stock" } },
      { label: "Finances", icon: WalletCards, href: "/bulkbite?work=finance", target: { mode: "workflow", id: "finance" } },
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
const sidebarMoreExpanded = ref(false)
const navGroupsRoot = ref(null)
const theoreticalExpanded = ref(false)
let flipExperience = null
let mobileShellQuery = null
const primarySections = computed(() => props.sections.filter(section => section.group !== "theoretical"))
const theoreticalSections = computed(() => props.sections.filter(section => section.group === "theoretical"))
const theoreticalActive = computed(() => theoreticalSections.value.some(section => section.id === props.activeSection) || props.theoreticalContextSections.includes(props.activeSection))
const theoreticalLinksVisible = computed(() => theoreticalExpanded.value)
const primarySidebarGroup = computed(() => props.sidebarGroups[0] || null)
const secondarySidebarGroups = computed(() => props.sidebarGroups.slice(1))
const mobileDrawerOpen = ref(false)
const mobileCloseButton = ref(null)
const mobilePrimaryIds = ["overview", "receipts", "production"]
const mobileSectionIcons = { overview: LayoutDashboard, receipts: ReceiptText, production: CookingPot }
const mobilePrimarySections = computed(() => mobilePrimaryIds
  .map(id => props.sections.find(section => section.id === id))
  .filter(Boolean)
  .map(section => ({ ...section, icon: mobileSectionIcons[section.id] })))
const mobileSecondarySections = computed(() => props.sections.filter(section => !mobilePrimaryIds.includes(section.id)))

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  window.localStorage.setItem("bulkbite-sidebar", sidebarCollapsed.value ? "collapsed" : "expanded")
}

function toggleSidebarMore() {
  sidebarMoreExpanded.value = !sidebarMoreExpanded.value
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

function navigateMobile(target) {
  mobileDrawerOpen.value = false
  emit("navigate", target)
}

function focusMobileDrawer(event) {
  event?.preventDefault?.()
  const target = document.querySelector(".app-shell__mobile-close") || mobileCloseButton.value?.$el || mobileCloseButton.value
  target?.focus?.()
}

function resolveMobileShellMode(event) {
  if (!event.matches) mobileDrawerOpen.value = false
}

function sidebarLinkIsActive(link) {
  if (link.target.mode === "workflow") return props.activeSection === link.target.id
  if (link.target.mode === "route") return window.location.pathname === link.target.href
  return false
}

watch(theoreticalActive, (isActive) => {
  if (isActive) theoreticalExpanded.value = true
}, { immediate: true })

watch(mobileDrawerOpen, async (isOpen) => {
  if (!isOpen) return
  await nextTick()
  window.requestAnimationFrame(() => {
    const target = document.querySelector(".app-shell__mobile-close") || mobileCloseButton.value?.$el || mobileCloseButton.value
    target?.focus?.()
  })
})

onMounted(() => {
  mobileShellQuery = window.matchMedia("(max-width: 64rem)")
  mobileShellQuery.addEventListener("change", resolveMobileShellMode)
  if (!navGroupsRoot.value) return
  flipExperience = mountFlipLayoutTransition(navGroupsRoot.value, {
    items: "[data-flip-id]",
    duration: 0.32,
    ease: "power2.out",
    absolute: false,
  })
})

onBeforeUnmount(() => {
  mobileShellQuery?.removeEventListener("change", resolveMobileShellMode)
  mobileShellQuery = null
  flipExperience?.destroy()
  flipExperience = null
})

// endregion SIDEBAR STATE
</script>

<template>
  <section data-block="bulkbite-app-shell" class="app-shell" :class="{ 'app-shell--collapsed': sidebarCollapsed }">
    <aside class="app-shell__sidebar" aria-label="BulkBite setup and tools">
      <header class="app-shell__brand">
        <div class="app-shell__brand-identity">
          <SystemLogo class="app-shell__logo" name="BulkBite" :src="sidebarCollapsed ? bulkbiteIcon : bulkbiteWordmark" href="/bulkbite" compact variant="inverse" @click.prevent="$emit('navigate', 'overview')" />
          <p class="app-shell__descriptor">Kitchen operations</p>
        </div>
        <SystemOperationalButton class="app-shell__collapse" variant="ghost" :label="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :tooltip="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" :aria-expanded="!sidebarCollapsed" @click="toggleSidebar">
          <PanelLeftOpen v-if="sidebarCollapsed" aria-hidden="true" />
          <PanelLeftClose v-else aria-hidden="true" />
        </SystemOperationalButton>
      </header>

      <div class="app-shell__sidebar-navigation">
        <nav v-if="primarySidebarGroup" class="app-shell__utility-nav" :aria-label="primarySidebarGroup.label">
          <p class="app-shell__nav-label">{{ primarySidebarGroup.label }}</p>
          <SystemLink v-for="link in primarySidebarGroup.links" :key="link.href" :href="link.href" class="app-shell__utility-link" :class="{ 'is-active': sidebarLinkIsActive(link) }" :title="sidebarCollapsed ? link.label : undefined" :aria-label="sidebarCollapsed ? link.label : undefined" @click.prevent="navigateSidebar(link.target)">
            <span class="app-shell__sidebar-icon" aria-hidden="true"><component :is="link.icon || Settings" /></span>
            <span class="app-shell__utility-label">{{ link.label }}</span>
            <ChevronRight class="app-shell__utility-arrow" aria-hidden="true" />
          </SystemLink>
        </nav>

        <SystemOperationalButton v-if="secondarySidebarGroups.length" class="app-shell__sidebar-action app-shell__more-toggle" variant="ghost" :label="sidebarMoreExpanded ? 'Collapse more navigation' : 'More navigation'" :tooltip="sidebarCollapsed ? (sidebarMoreExpanded ? 'Collapse' : 'More') : undefined" :aria-expanded="sidebarMoreExpanded" aria-controls="sidebar-more-navigation" @click="toggleSidebarMore">
          <Ellipsis aria-hidden="true" />
          <span class="app-shell__utility-label">{{ sidebarMoreExpanded ? 'Collapse' : 'More' }}</span>
          <ChevronRight class="app-shell__more-arrow" aria-hidden="true" />
        </SystemOperationalButton>

        <div v-if="sidebarMoreExpanded" id="sidebar-more-navigation" class="app-shell__more-navigation">
          <nav v-for="group in secondarySidebarGroups" :key="group.label" class="app-shell__utility-nav" :aria-label="group.label">
            <p class="app-shell__nav-label">{{ group.label }}</p>
            <SystemLink v-for="link in group.links" :key="link.href" :href="link.href" class="app-shell__utility-link" :class="{ 'is-active': sidebarLinkIsActive(link) }" :title="sidebarCollapsed ? link.label : undefined" :aria-label="sidebarCollapsed ? link.label : undefined" @click.prevent="navigateSidebar(link.target)">
              <span class="app-shell__sidebar-icon" aria-hidden="true"><component :is="link.icon || Settings" /></span>
              <span class="app-shell__utility-label">{{ link.label }}</span>
              <ChevronRight class="app-shell__utility-arrow" aria-hidden="true" />
            </SystemLink>
          </nav>
        </div>
      </div>

      <footer class="app-shell__sidebar-footer">
        <nav class="app-shell__fixed-setup" aria-label="All setup records">
          <SystemLink href="/bulkbite/setup" class="app-shell__utility-link" :title="sidebarCollapsed ? 'All setup' : undefined" :aria-label="sidebarCollapsed ? 'All setup' : undefined" @click.prevent="navigateSidebar({ mode: 'catalogue' })">
            <span class="app-shell__sidebar-icon" aria-hidden="true"><Settings /></span>
            <span class="app-shell__utility-label">All setup</span>
            <ChevronRight class="app-shell__utility-arrow" aria-hidden="true" />
          </SystemLink>
        </nav>
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
                    <ChevronLeft v-if="theoreticalLinksVisible" class="app-shell__expand-icon" aria-hidden="true" />
                    <ChevronRight v-else class="app-shell__expand-icon" aria-hidden="true" />
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

    <SystemDrawer v-model:open="mobileDrawerOpen" direction="bottom">
      <nav class="app-shell__mobile-nav" aria-label="Primary mobile navigation">
        <SystemOperationalButton
          v-for="section in mobilePrimarySections"
          :key="section.id"
          class="app-shell__mobile-nav-action"
          :class="{ 'is-active': activeSection === section.id }"
          :aria-current="activeSection === section.id ? 'page' : undefined"
          variant="ghost"
          @click="navigateMobile(section.id)"
        >
          <component :is="section.icon" aria-hidden="true" />
          <span>{{ section.label }}</span>
        </SystemOperationalButton>

        <SystemDrawerTrigger as-child>
          <SystemOperationalButton class="app-shell__mobile-nav-action" :class="{ 'is-active': mobileDrawerOpen }" variant="ghost" aria-label="Open all navigation">
            <Menu aria-hidden="true" />
            <span>Menu</span>
          </SystemOperationalButton>
        </SystemDrawerTrigger>
      </nav>

      <SystemDrawerContent class="app-shell__mobile-drawer" @open-auto-focus="focusMobileDrawer">
        <SystemDrawerHeader class="app-shell__mobile-drawer-header">
          <div class="app-shell__mobile-drawer-heading">
            <SystemLogo class="app-shell__mobile-logo" name="BulkBite" :src="bulkbiteWordmark" href="/bulkbite" compact @click.prevent="navigateMobile('overview')" />
            <SystemDrawerClose as-child>
              <SystemOperationalButton ref="mobileCloseButton" class="app-shell__mobile-close" variant="ghost"><X aria-hidden="true" /><span class="app-shell__visually-hidden">Close navigation</span></SystemOperationalButton>
            </SystemDrawerClose>
          </div>
          <SystemDrawerTitle>All operations</SystemDrawerTitle>
          <SystemDrawerDescription>Open planning, stock, finance, setup, or account actions.</SystemDrawerDescription>
        </SystemDrawerHeader>

        <div class="app-shell__mobile-drawer-scroll">
          <nav class="app-shell__mobile-drawer-group" aria-label="Planning and control">
            <p class="app-shell__mobile-group-label">Planning and control</p>
            <SystemDrawerClose v-for="section in mobileSecondarySections" :key="section.id" as-child>
              <SystemLink :href="`/bulkbite?work=${section.id}`" class="app-shell__mobile-drawer-link" :class="{ 'is-active': activeSection === section.id }" :aria-current="activeSection === section.id ? 'page' : undefined" @click.prevent="navigateMobile(section.id)">
                <span>{{ section.label }}</span><ChevronRight aria-hidden="true" />
              </SystemLink>
            </SystemDrawerClose>
          </nav>

          <nav v-for="group in secondarySidebarGroups" :key="group.label" class="app-shell__mobile-drawer-group" :aria-label="group.label">
            <p class="app-shell__mobile-group-label">{{ group.label }}</p>
            <SystemDrawerClose v-for="link in group.links" :key="link.href" as-child>
              <SystemLink :href="link.href" class="app-shell__mobile-drawer-link" @click.prevent="navigateMobile(link.target)">
                <span class="app-shell__mobile-link-label"><component :is="link.icon || Settings" aria-hidden="true" /><span>{{ link.label }}</span></span>
                <ChevronRight aria-hidden="true" />
              </SystemLink>
            </SystemDrawerClose>
          </nav>

          <nav class="app-shell__mobile-drawer-group" aria-label="Setup">
            <p class="app-shell__mobile-group-label">Setup</p>
            <SystemDrawerClose as-child>
              <SystemLink href="/bulkbite/setup" class="app-shell__mobile-drawer-link" @click.prevent="navigateMobile({ mode: 'catalogue' })">
                <span class="app-shell__mobile-link-label"><Settings aria-hidden="true" /><span>All setup</span></span><ChevronRight aria-hidden="true" />
              </SystemLink>
            </SystemDrawerClose>
          </nav>
        </div>

        <footer class="app-shell__mobile-drawer-footer">
          <div class="app-shell__mobile-account"><span class="app-shell__account-avatar" aria-hidden="true"><UserRound /></span><span>{{ user && user !== 'Guest' ? user : 'Guest' }}</span></div>
          <div class="app-shell__mobile-footer-actions">
            <SystemOperationalButton variant="subtle" :disabled="busy" :aria-busy="busy" @click="$emit('refresh')"><span v-if="busy" class="app-shell__refresh-loader" aria-hidden="true" /><span>{{ busy ? 'Refreshing' : 'Refresh' }}</span></SystemOperationalButton>
            <SystemOperationalButton v-if="user && user !== 'Guest'" variant="subtle" :disabled="sessionBusy" @click="$emit('logout')"><LogOut aria-hidden="true" /><span>Log out</span></SystemOperationalButton>
            <SystemLink v-else href="/login?redirect-to=%2Fbulkbite" class="app-shell__mobile-login"><LogIn aria-hidden="true" /><span>Log in</span></SystemLink>
          </div>
        </footer>
      </SystemDrawerContent>
    </SystemDrawer>
  </section>
</template>

<style scoped>
.app-shell{display:grid;grid-template-columns:16rem minmax(0,1fr);min-height:100vh;background:var(--theme-canvas);color:var(--theme-text);transition:grid-template-columns .18s ease}.app-shell--collapsed{grid-template-columns:5.25rem minmax(0,1fr)}.app-shell__sidebar{position:sticky;top:0;z-index:20;display:flex;flex-direction:column;width:100%;min-width:0;max-width:100%;height:100vh;overflow:hidden;padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-navigation-sidebar-border);background:var(--theme-navigation-sidebar);color:var(--theme-navigation-sidebar-text)}.app-shell__brand{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-xs);min-height:4rem;padding:var(--spacing-xs) var(--spacing-2xs) var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-navigation-sidebar-border)}.app-shell__brand-copy,.app-shell__header-copy,.app-shell__account-copy{min-width:0}.app-shell__kicker,.app-shell__descriptor,.app-shell__sidebar p,.app-shell__header p{margin:0}.app-shell__kicker{color:var(--theme-navigation-sidebar-text);font-size:var(--font-size-0);font-weight:var(--font-weight-700)}.app-shell__descriptor{margin-top:var(--spacing-3xs)!important;color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--2)}.app-shell__collapse{flex:0 0 2.5rem!important;width:2.5rem!important;height:2.5rem!important;min-height:2.5rem!important;padding:0!important;border:var(--border-width-1) solid var(--theme-navigation-sidebar-border)!important;background:var(--theme-navigation-sidebar-control)!important;color:var(--theme-navigation-sidebar-text)!important;box-shadow:none!important}.app-shell__collapse:hover{background:var(--theme-navigation-sidebar-hover)!important}.app-shell__collapse :deep(svg){width:1rem!important;height:1rem!important}.app-shell__utility-nav{display:grid;gap:var(--spacing-3xs);padding-top:var(--spacing-s)}.app-shell__nav-label{padding:0 var(--spacing-xs) var(--spacing-2xs);color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.app-shell__utility-link{display:grid;grid-template-columns:2.25rem minmax(0,1fr) 1rem;align-items:center;gap:var(--spacing-2xs);min-height:2.75rem;padding:0 var(--spacing-2xs);border-radius:var(--component-radius-button);color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--1);line-height:1;text-decoration:none;text-decoration-color:transparent}.app-shell__utility-link:hover{background:var(--theme-navigation-sidebar-hover);color:var(--theme-navigation-sidebar-text);text-decoration:none}.app-shell__utility-link:focus-visible,.app-shell__session-link:focus-visible{outline:2px solid var(--theme-navigation-sidebar-text);outline-offset:2px}.app-shell__sidebar-icon,.app-shell__account-avatar{display:grid;place-items:center;width:2.25rem;height:2.25rem;border-radius:var(--component-radius-button);background:var(--theme-navigation-sidebar-control);color:var(--theme-navigation-sidebar-text)}.app-shell__sidebar-icon svg,.app-shell__account-avatar svg{width:1.05rem;height:1.05rem;stroke-width:1.8}.app-shell__utility-arrow{width:.9rem;height:.9rem}.app-shell__sidebar-footer{display:grid;gap:var(--spacing-xs);margin-top:auto}.app-shell__sidebar-action{display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:var(--spacing-xs)!important;width:100%;height:2.75rem!important;min-height:2.75rem!important;padding:0 var(--spacing-xs)!important;border:0!important;border-radius:var(--component-radius-button)!important;background:transparent!important;color:var(--theme-navigation-sidebar-muted)!important;font-size:var(--font-size--1)!important;line-height:1!important;box-shadow:none!important}.app-shell__sidebar-action:hover,.app-shell__export-button.is-active{background:var(--theme-navigation-sidebar-hover)!important;color:var(--theme-navigation-sidebar-text)!important}.app-shell__sidebar-action :is(svg){flex:0 0 1.05rem!important;width:1.05rem!important;height:1.05rem!important;max-width:1.05rem!important;max-height:1.05rem!important}.app-shell__account{display:grid;gap:var(--spacing-2xs);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-navigation-sidebar-border);border-radius:var(--component-radius-card);background:var(--theme-navigation-sidebar-panel)}.app-shell__account-user{display:grid;grid-template-columns:2.25rem minmax(0,1fr);align-items:center;gap:var(--spacing-xs);min-width:0}.app-shell__account-copy{display:grid;gap:var(--spacing-3xs);color:var(--theme-navigation-sidebar-muted);font-size:var(--font-size--2)}.app-shell__account-copy p{overflow:hidden;color:var(--theme-navigation-sidebar-text);text-overflow:ellipsis;white-space:nowrap}.app-shell__account-status{width:max-content;background:var(--theme-navigation-sidebar-control)!important;color:var(--theme-navigation-sidebar-muted)!important}.app-shell__session-link{text-decoration:none}.app-shell--collapsed :is(.app-shell__brand-copy,.app-shell__nav-label,.app-shell__utility-label,.app-shell__utility-arrow,.app-shell__account-copy){display:none}.app-shell--collapsed .app-shell__brand{justify-content:center;padding-inline:0}.app-shell--collapsed .app-shell__utility-link{grid-template-columns:1fr;justify-items:center;padding:0}.app-shell--collapsed .app-shell__sidebar-action{justify-content:center!important;padding-inline:0!important}.app-shell--collapsed .app-shell__account{justify-items:center;padding:var(--spacing-2xs)}.app-shell--collapsed .app-shell__account-user{grid-template-columns:1fr}.app-shell__main{min-width:0}.app-shell__top-area{position:sticky;top:0;z-index:10;background:var(--theme-navigation-header)}.app-shell__header{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-m);height:4.25rem;padding:0 var(--spacing-m);border-bottom:var(--border-width-1) solid var(--theme-navigation-header-border);background:var(--theme-navigation-header);color:var(--theme-navigation-header-text)}.app-shell__header-label{color:var(--theme-navigation-header-text);font-weight:var(--font-weight-700)}.app-shell__header-note{margin-top:var(--spacing-3xs)!important;color:var(--theme-navigation-header-muted);font-size:var(--font-size--2)}.app-shell__refresh{flex:0 0 8.75rem!important;width:8.75rem!important;min-width:8.75rem!important;max-width:8.75rem!important;height:2.75rem!important;min-height:2.75rem!important;max-height:2.75rem!important;overflow:hidden!important;padding:0 var(--spacing-xs)!important;border:var(--border-width-1) solid var(--theme-navigation-header-border)!important;border-radius:var(--component-radius-button)!important;background:var(--theme-navigation-header-control)!important;color:var(--theme-navigation-header-text)!important;line-height:1!important;white-space:nowrap!important;box-shadow:none!important}.app-shell__refresh:hover{background:var(--theme-navigation-header-hover)!important}.app-shell__refresh :deep(svg){display:block!important;flex:0 0 1rem!important;width:1rem!important;height:1rem!important;min-width:1rem!important;min-height:1rem!important;max-width:1rem!important;max-height:1rem!important;scale:1!important}.app-shell__nav{overflow-x:auto;border-bottom:var(--border-width-1) solid var(--theme-navigation-header-border);background:var(--theme-navigation-tabs)}.app-shell__nav-inner{display:flex;gap:var(--spacing-2xs);width:min(100%,90rem);margin-inline:auto;padding:var(--spacing-xs) var(--spacing-m)}.app-shell__nav :deep(.app-shell__nav-button){position:relative;flex:0 0 auto;gap:var(--spacing-2xs)!important;height:2.75rem!important;min-height:2.75rem!important;padding-inline:var(--spacing-s)!important;border:var(--border-width-1) solid transparent!important;border-radius:var(--component-radius-button)!important;background:var(--theme-navigation-tab)!important;color:var(--theme-navigation-header-muted)!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button:hover){border-color:var(--theme-navigation-header-border)!important;background:var(--theme-navigation-tab-hover)!important;color:var(--theme-navigation-header-text)!important}.app-shell__nav :deep(.app-shell__nav-button:focus-visible){outline:2px solid var(--theme-navigation-header-text)!important;outline-offset:2px!important;box-shadow:none!important}.app-shell__nav :deep(.app-shell__nav-button.is-active){border-color:var(--theme-navigation-active-border)!important;background:var(--theme-navigation-active)!important;color:var(--theme-navigation-active-text)!important}.app-shell__nav :deep(.app-shell__nav-button.is-active)::after{position:absolute;right:var(--spacing-s);bottom:-.45rem;left:var(--spacing-s);height:2px;border-radius:999px;background:var(--theme-navigation-active-accent);content:""}.app-shell__nav-number{font-size:var(--font-size--2);font-variant-numeric:tabular-nums;opacity:.74}.app-shell__work{min-width:0;min-height:calc(100vh - 7.75rem);background:var(--theme-canvas)}
@media(max-width:64rem){.app-shell,.app-shell--collapsed{grid-template-columns:1fr;width:100%;max-width:100vw;overflow-x:clip}.app-shell__sidebar{position:static;width:100%;min-width:0;max-width:100vw;height:auto;padding:var(--spacing-xs) var(--spacing-s);border-right:0;border-bottom:var(--border-width-1) solid var(--theme-navigation-sidebar-border)}.app-shell__brand{align-items:center;min-height:3.25rem;padding:0}.app-shell__brand-copy,.app-shell--collapsed .app-shell__brand-copy{display:block}.app-shell__utility-nav{display:flex;overflow-x:auto;gap:var(--spacing-3xs);padding-top:var(--spacing-xs)}.app-shell__nav-label{display:none}.app-shell__utility-link,.app-shell--collapsed .app-shell__utility-link{flex:0 0 auto;grid-template-columns:2.25rem auto;padding-inline:var(--spacing-2xs)}.app-shell__utility-arrow{display:none}.app-shell__sidebar-footer{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--spacing-xs);margin-top:var(--spacing-xs)}.app-shell__account{grid-template-columns:minmax(0,1fr) auto;align-items:center;padding:var(--spacing-2xs)}.app-shell__account-user,.app-shell--collapsed .app-shell__account-user{grid-template-columns:2.25rem minmax(0,1fr)}.app-shell--collapsed .app-shell__account-copy{display:grid}.app-shell--collapsed .app-shell__sidebar-action{justify-content:flex-start!important;padding-inline:var(--spacing-xs)!important}.app-shell--collapsed .app-shell__utility-label{display:inline}.app-shell__session-action,.app-shell__session-link{width:auto}.app-shell__top-area{position:static}.app-shell__header{height:4rem;padding-inline:var(--spacing-s)}.app-shell__nav-inner{width:max-content;min-width:100%;padding-inline:var(--spacing-s)}}
@media(max-width:44rem){.app-shell__sidebar-footer{grid-template-columns:1fr!important}.app-shell__account{grid-template-columns:minmax(0,1fr) auto}.app-shell__export-button{width:100%}.app-shell__header-note{display:none}.app-shell__refresh{flex-basis:7.75rem!important;width:7.75rem!important;min-width:7.75rem!important;max-width:7.75rem!important}.app-shell__nav-inner{gap:var(--spacing-3xs);width:100%;min-width:0;padding-inline:var(--spacing-xs)}.app-shell__nav :deep(.app-shell__nav-button){min-width:max-content;padding-inline:var(--spacing-3xs)!important;font-size:var(--font-size--2)!important}}
.app-shell__refresh :deep(svg){display:inline-block!important;flex:0 0 .875rem!important;width:.875rem!important;height:.875rem!important;min-width:.875rem!important;min-height:.875rem!important;max-width:.875rem!important;max-height:.875rem!important;scale:1!important;transform-origin:center!important}
.app-shell__refresh-loader{display:block;align-self:center;box-sizing:border-box;flex:0 0 .75rem;width:.75rem;height:.75rem;margin:0;border:1.5px solid currentColor;border-right-color:transparent;border-radius:999px;animation:app-shell-spin .7s linear infinite}@keyframes app-shell-spin{to{transform:rotate(360deg)}}
:deep(.app-shell__collapse){border:var(--border-width-1) solid var(--theme-navigation-sidebar-border)!important;background:var(--theme-navigation-sidebar-control)!important;color:var(--theme-navigation-sidebar-text)!important}:deep(.app-shell__collapse svg){width:1rem!important;height:1rem!important;stroke:currentColor!important}:deep(.app-shell__sidebar-action){color:var(--theme-navigation-sidebar-muted)!important}:deep(.app-shell__sidebar-action > span.truncate){display:flex!important;align-items:center!important;gap:var(--spacing-xs)!important;width:100%;height:auto!important;overflow:visible!important}:deep(.app-shell__sidebar-action > span.truncate svg),:deep(.app-shell__session-link svg){flex:0 0 1.05rem!important;width:1.05rem!important;height:1.05rem!important;stroke:currentColor!important}:deep(.app-shell__export-button:hover),:deep(.app-shell__export-button.is-active),:deep(.app-shell__session-action:hover){background:var(--theme-navigation-sidebar-hover)!important;color:var(--theme-navigation-sidebar-text)!important}:deep(.app-shell__refresh){flex:0 0 8.75rem!important;width:8.75rem!important;min-width:8.75rem!important;max-width:8.75rem!important;height:2.75rem!important;min-height:2.75rem!important;max-height:2.75rem!important;border-color:var(--theme-navigation-header-border)!important;background:var(--theme-navigation-header-control)!important;color:var(--theme-navigation-header-text)!important}:deep(.app-shell__refresh > span.truncate){display:flex!important;align-items:center!important;justify-content:center!important;gap:var(--spacing-2xs)!important;width:100%!important;height:100%!important;overflow:visible!important;color:inherit!important;line-height:1!important}:deep(.app-shell__refresh > span.truncate > span:last-child){display:flex!important;align-items:center!important;justify-content:center!important;min-width:5.25rem;height:100%;text-align:center}.app-shell__account-copy{display:block}.app-shell__account-copy p{font-size:var(--font-size--2);font-weight:var(--font-weight-600)}
@media(min-width:64.0625rem){.app-shell__account{grid-template-columns:minmax(0,1fr) 2.25rem;align-items:center;padding:var(--spacing-2xs)}:deep(.app-shell__session-action),:deep(.app-shell__session-link){display:flex!important;align-items:center!important;justify-content:center!important;flex:0 0 2.25rem!important;width:2.25rem!important;min-width:2.25rem!important;height:2.25rem!important;min-height:2.25rem!important;padding:0!important;white-space:nowrap}:deep(.app-shell__session-action > span.truncate){justify-content:center!important;gap:0!important}:deep(.app-shell__session-action > span.truncate svg){flex:0 0 1rem!important;width:1rem!important;height:1rem!important}.app-shell__session-label{display:none!important}}
.app-shell__session-loader{display:block;flex:0 0 .8rem;width:.8rem;height:.8rem;border:1.5px solid currentColor;border-right-color:transparent;border-radius:999px;animation:app-shell-spin .7s linear infinite}
.app-shell__brand-identity{min-width:0}.app-shell__logo{width:8.5rem;min-height:0}.app-shell__logo :deep(.system-logo__mark){width:100%;height:auto}.app-shell--collapsed .app-shell__brand{flex-direction:column;min-height:6.75rem}.app-shell--collapsed .app-shell__descriptor{display:none}.app-shell--collapsed .app-shell__logo{width:2.4rem}
@media(max-width:64rem){.app-shell__brand,.app-shell--collapsed .app-shell__brand{justify-content:space-between}.app-shell__logo,.app-shell--collapsed .app-shell__logo{width:7.5rem}.app-shell--collapsed .app-shell__descriptor{display:block}}
@media(min-width:64.0625rem){.app-shell--collapsed .app-shell__sidebar{padding-inline:var(--spacing-2xs)}.app-shell--collapsed .app-shell__account{display:grid;grid-template-columns:2.5rem;justify-content:center;justify-items:center;gap:var(--spacing-2xs);padding:var(--spacing-2xs)}.app-shell--collapsed .app-shell__account-user{display:grid;grid-template-columns:2.5rem;width:2.5rem;height:2.5rem}.app-shell--collapsed .app-shell__account-avatar{width:2.5rem;height:2.5rem}.app-shell--collapsed :deep(.app-shell__session-action),.app-shell--collapsed .app-shell__session-link{display:flex!important;flex:0 0 2.5rem!important;width:2.5rem!important;min-width:2.5rem!important;max-width:2.5rem!important;height:2.5rem!important;min-height:2.5rem!important;max-height:2.5rem!important;padding:0!important;overflow:hidden!important}}

.app-shell__sidebar-navigation{min-height:0;overflow-y:auto;padding-bottom:var(--spacing-s)}
.app-shell__sidebar-navigation{scrollbar-width:thin;scrollbar-color:var(--theme-navigation-sidebar-control) transparent}
.app-shell__sidebar-navigation::-webkit-scrollbar{width:.5rem;height:.5rem}
.app-shell__sidebar-navigation::-webkit-scrollbar-track{background:transparent}
.app-shell__sidebar-navigation::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background:var(--theme-navigation-sidebar-control);background-clip:padding-box}
.app-shell__sidebar-navigation::-webkit-scrollbar-thumb:hover{background:var(--theme-navigation-sidebar-hover);background-clip:padding-box}
.app-shell__sidebar-navigation .app-shell__utility-nav + .app-shell__utility-nav{margin-top:var(--spacing-s);padding-top:var(--spacing-s);border-top:var(--border-width-1) solid var(--theme-navigation-sidebar-border)}
.app-shell__sidebar-navigation :deep(.app-shell__more-toggle){display:flex!important;align-items:center!important;justify-content:flex-start!important;width:100%!important;max-width:100%!important;gap:0!important;margin-top:var(--spacing-s);padding:0 var(--spacing-2xs)!important;border:0!important;border-radius:var(--component-radius-button)!important;background:transparent!important;color:var(--theme-navigation-sidebar-muted)!important}
.app-shell__sidebar-navigation :deep(.app-shell__more-toggle:hover){background:var(--theme-navigation-sidebar-hover)!important;color:var(--theme-navigation-sidebar-text)!important}
.app-shell__sidebar-navigation :deep(.app-shell__more-toggle:focus-visible){outline:2px solid var(--theme-navigation-sidebar-text)!important;outline-offset:2px!important;box-shadow:none!important}
.app-shell__more-toggle :deep(> span.truncate){display:grid!important;grid-template-columns:2.25rem minmax(0,1fr) 1rem;align-items:center;gap:var(--spacing-2xs);width:100%;overflow:visible;text-align:left}
.app-shell__more-arrow{width:.9rem!important;height:.9rem!important;transition:transform .18s ease}
.app-shell__more-toggle[aria-expanded="true"] .app-shell__more-arrow{transform:rotate(90deg)}
.app-shell__more-navigation{display:grid}
.app-shell__fixed-setup{padding:var(--spacing-2xs);border:var(--border-width-1) solid var(--theme-navigation-sidebar-border);border-radius:var(--component-radius-card);background:var(--theme-navigation-sidebar-panel)}
.app-shell__fixed-setup .app-shell__sidebar-icon{color:var(--theme-navigation-sidebar-text)}
.app-shell__fixed-setup .app-shell__sidebar-icon svg{color:var(--theme-navigation-sidebar-text);stroke:var(--theme-navigation-sidebar-text)}
.app-shell__utility-link.is-active{background:var(--theme-navigation-sidebar-hover);color:var(--theme-navigation-sidebar-text)}
.app-shell__nav-groups{align-items:flex-end;gap:var(--spacing-s);width:max-content;min-width:min(100%,90rem)}
.app-shell__nav-category{display:grid;flex:0 0 auto;gap:var(--spacing-3xs);min-width:0}
.app-shell__category-label{margin:0;padding-left:var(--spacing-xs);color:var(--theme-navigation-header-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-600);line-height:1.25}
.app-shell__category-card{overflow:visible!important;padding:var(--spacing-2xs)!important;border:var(--border-width-1) solid var(--theme-navigation-header-border)!important;border-radius:var(--component-radius-card)!important;background:transparent!important;box-shadow:none!important}
.app-shell__category-controls,.app-shell__theoretical-controls{display:flex;align-items:center;gap:var(--spacing-3xs);min-width:0}
.app-shell__theoretical-controls{transform-origin:left center}
.app-shell__nav :deep(.app-shell__nav-category .app-shell__nav-button){padding-inline:var(--spacing-2xs)!important;font-size:var(--font-size--1)!important;line-height:1.25!important}
.app-shell__nav :deep(.app-shell__nav-category .app-shell__nav-button > span.truncate){display:flex!important;align-items:center!important;height:100%!important;padding-block:1px!important;overflow:visible!important;line-height:1.25!important}
.app-shell__nav :deep(.app-shell__expand-button),.app-shell__nav :deep(.app-shell__expand-button.is-active){min-width:6.5rem!important;border-color:var(--theme-navigation-header-border)!important;background:var(--theme-navigation-header-control)!important;color:var(--theme-navigation-header-text)!important}
.app-shell__expand-icon{flex:0 0 .95rem!important;width:.95rem!important;height:.95rem!important;stroke:currentColor!important;stroke-width:2.2!important}
@media(max-width:64rem){.app-shell__sidebar-navigation{display:flex;align-items:flex-end;overflow-x:auto;overflow-y:hidden;gap:var(--spacing-xs);padding-bottom:var(--spacing-2xs)}.app-shell__sidebar-navigation .app-shell__utility-nav,.app-shell__sidebar-navigation .app-shell__utility-nav + .app-shell__utility-nav{flex:0 0 auto;margin:0;padding-top:var(--spacing-xs);border-top:0}.app-shell__more-toggle{flex:0 0 auto!important;width:auto!important;margin:0!important;border-top:0!important}.app-shell__more-navigation{display:flex;gap:var(--spacing-xs)}.app-shell__sidebar-footer{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.app-shell__fixed-setup{align-self:stretch}.app-shell__nav-groups{width:max-content;min-width:100%}}
@media(min-width:64.0625rem){.app-shell--collapsed :deep(.app-shell__more-toggle){justify-content:center!important;padding-inline:0!important}.app-shell--collapsed :deep(.app-shell__more-toggle > span.truncate){display:flex!important;justify-content:center!important;width:100%!important;gap:0!important}.app-shell--collapsed :deep(.app-shell__more-toggle > span.truncate > :not(:first-child)){display:none!important;width:0!important;height:0!important;min-width:0!important;min-height:0!important;margin:0!important;padding:0!important}.app-shell--collapsed .app-shell__more-toggle .app-shell__more-arrow{display:none!important}.app-shell--collapsed .app-shell__fixed-setup,.app-shell--collapsed .app-shell__account{box-sizing:border-box;width:100%}.app-shell--collapsed .app-shell__fixed-setup{padding:var(--spacing-2xs)}.app-shell--collapsed .app-shell__fixed-setup .app-shell__utility-link{width:100%}}
@media(max-width:44rem){.app-shell__nav{overflow-x:hidden}.app-shell__nav-groups{display:grid;width:100%;min-width:0}.app-shell__nav-category{width:100%}.app-shell__category-controls,.app-shell__theoretical-controls{flex-wrap:wrap}.app-shell__theoretical-controls{display:contents}.app-shell__nav :deep(.app-shell__nav-button){flex:1 1 auto;min-width:5.5rem!important;padding-inline:var(--spacing-xs)!important}.app-shell__category-card{width:100%}}
.app-shell__mobile-nav,.app-shell__mobile-drawer{display:none}
.app-shell__visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;margin:-1px;padding:0;border:0;clip:rect(0 0 0 0);white-space:nowrap}
@media(max-width:64rem){
  .app-shell,.app-shell--collapsed{display:block;min-height:100dvh;overflow-x:clip}
  .app-shell__sidebar,.app-shell__top-area{display:none}
  .app-shell__main{min-height:100dvh}
  .app-shell__work{min-height:100dvh;padding-bottom:calc(5.25rem + env(safe-area-inset-bottom,0px))}
  .app-shell__mobile-nav{position:fixed;right:0;bottom:0;left:0;z-index:40;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-3xs);min-height:4.75rem;padding:var(--spacing-2xs) max(var(--spacing-xs),env(safe-area-inset-right,0px)) calc(var(--spacing-2xs) + env(safe-area-inset-bottom,0px)) max(var(--spacing-xs),env(safe-area-inset-left,0px));border-top:var(--border-width-1) solid var(--theme-navigation-header-border);background:var(--theme-navigation-header);box-shadow:0 -.5rem 1.5rem rgb(37 37 34/.12)}
  .app-shell__mobile-nav :deep(.app-shell__mobile-nav-action){position:relative;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:.3rem!important;width:100%!important;min-width:0!important;height:3.75rem!important;min-height:3.75rem!important;padding:.35rem .2rem!important;border:0!important;border-radius:var(--component-radius-button)!important;background:transparent!important;color:var(--theme-navigation-header-muted)!important;font-size:var(--font-size--2)!important;font-weight:var(--font-weight-600)!important;line-height:1!important;box-shadow:none!important}
  .app-shell__mobile-nav :deep(.app-shell__mobile-nav-action>span.truncate){display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:.3rem!important;width:100%!important;height:100%!important;min-width:0!important;overflow:visible!important;line-height:1!important;text-align:center!important}
  .app-shell__mobile-nav :deep(.app-shell__mobile-nav-action>span.truncate>span){display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .app-shell__mobile-nav :deep(.app-shell__mobile-nav-action:hover),.app-shell__mobile-nav :deep(.app-shell__mobile-nav-action.is-active){background:var(--theme-navigation-header-hover)!important;color:var(--theme-navigation-header-text)!important}
  .app-shell__mobile-nav :deep(.app-shell__mobile-nav-action.is-active)::after{position:absolute;top:.2rem;left:50%;width:1.4rem;height:.18rem;border-radius:999px;background:var(--theme-navigation-active-accent);content:"";transform:translateX(-50%)}
  .app-shell__mobile-nav :deep(.app-shell__mobile-nav-action svg){display:block!important;flex:0 0 1.25rem!important;width:1.25rem!important;height:1.25rem!important;min-width:1.25rem!important;min-height:1.25rem!important;max-width:1.25rem!important;max-height:1.25rem!important;margin:0 auto!important}
  :global(.app-shell__mobile-drawer){display:flex!important;max-height:min(88dvh,48rem)!important;overflow:hidden!important;padding-bottom:env(safe-area-inset-bottom,0px);border-color:var(--theme-border)!important;border-radius:var(--component-radius-card) var(--component-radius-card) 0 0!important;background:var(--theme-surface-raised)!important;color:var(--theme-text)!important;box-shadow:0 -1rem 3rem rgb(37 37 34/.2)}
  :global(.app-shell__mobile-drawer-header){padding:var(--spacing-m) var(--spacing-m) var(--spacing-s)!important;text-align:left!important}
  .app-shell__mobile-drawer-heading{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);margin-bottom:var(--spacing-xs)}
  .app-shell__mobile-logo{max-width:9rem}
  :global(.app-shell__mobile-close){width:2.75rem!important;min-width:2.75rem!important;height:2.75rem!important;min-height:2.75rem!important;padding:0!important;border:var(--border-width-1) solid var(--theme-border)!important;background:var(--theme-surface)!important;color:var(--theme-text)!important}
  :global(.app-shell__mobile-close svg){width:1.1rem!important;height:1.1rem!important}
  .app-shell__mobile-drawer-scroll{display:grid;gap:var(--spacing-m);overflow-y:auto;padding:0 var(--spacing-m) var(--spacing-m);overscroll-behavior:contain;scrollbar-color:var(--theme-border) transparent;scrollbar-width:thin}
  .app-shell__mobile-drawer-group{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-2xs)}
  .app-shell__mobile-group-label{grid-column:1/-1;margin:0 0 var(--spacing-3xs);color:var(--theme-text-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-700);letter-spacing:.04em;text-transform:uppercase}
  .app-shell__mobile-drawer-link{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-xs);min-height:3.25rem;padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-button);background:var(--theme-surface);color:var(--theme-text);font-size:var(--font-size--1);font-weight:var(--font-weight-600);text-decoration:none}
  .app-shell__mobile-drawer-link:hover,.app-shell__mobile-drawer-link.is-active{border-color:var(--theme-navigation-active-border);background:var(--theme-accent-soft);text-decoration:none}
  .app-shell__mobile-drawer-link>svg{flex:0 0 .9rem;width:.9rem;height:.9rem;color:var(--theme-text-muted)}
  .app-shell__mobile-link-label{display:flex;align-items:center;gap:var(--spacing-2xs);min-width:0}
  .app-shell__mobile-link-label svg{flex:0 0 1.05rem;width:1.05rem;height:1.05rem;color:var(--theme-primary)}
  .app-shell__mobile-drawer-footer{display:grid;gap:var(--spacing-xs);padding:var(--spacing-s) var(--spacing-m);border-top:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface)}
  .app-shell__mobile-account{display:flex;align-items:center;gap:var(--spacing-xs);min-width:0;font-size:var(--font-size--1);font-weight:var(--font-weight-600)}
  .app-shell__mobile-footer-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-xs)}
  .app-shell__mobile-footer-actions :deep(button),.app-shell__mobile-login{display:flex;align-items:center;justify-content:center;gap:var(--spacing-2xs);min-height:2.75rem;padding:0 var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-button);background:var(--theme-surface-raised);color:var(--theme-text);font-size:var(--font-size--1);text-decoration:none}
  :global(.app-shell__mobile-drawer .system-component--operational-button>span.truncate){display:flex!important;align-items:center!important;justify-content:center!important;gap:var(--spacing-2xs)!important;min-width:0!important;height:100%!important;overflow:visible!important;line-height:1!important}
  :global(.app-shell__mobile-drawer .system-component--operational-button :is(svg,[data-slot="loading"],.app-shell__refresh-loader)){display:block!important;align-self:center!important;flex:0 0 1rem!important;width:1rem!important;height:1rem!important;min-width:1rem!important;min-height:1rem!important;max-width:1rem!important;max-height:1rem!important;margin:0!important;transform-origin:center!important}
  .app-shell__mobile-footer-actions :deep(svg),.app-shell__mobile-login svg{width:1rem!important;height:1rem!important}
}
@media(max-width:30rem){.app-shell__mobile-drawer-group{grid-template-columns:1fr}.app-shell__mobile-nav{padding-inline:var(--spacing-2xs)}.app-shell__mobile-nav :deep(.app-shell__mobile-nav-action){font-size:.68rem!important}}
@media(prefers-reduced-motion:reduce){.app-shell,.app-shell__mobile-nav :deep(button){transition:none!important}}
</style>
