<script setup>
import { computed } from "vue"
const props = defineProps({ href: { type: String, required: true }, external: { type: Boolean, default: false }, current: { type: Boolean, default: false }, download: { type: [Boolean, String], default: false } })
const target = computed(() => props.external ? "_blank" : undefined)
const rel = computed(() => props.external ? "noopener noreferrer" : undefined)
</script>
<template><a class="system-link" :href="href" :target="target" :rel="rel" :aria-current="current ? 'page' : undefined" :download="download || undefined"><slot /><span v-if="external" class="system-link__external" aria-hidden="true">↗</span></a></template>
<style scoped>.system-link{display:inline-flex;align-items:baseline;gap:.3em;color:var(--theme-primary);font:inherit;text-decoration-color:color-mix(in oklch,var(--theme-primary) 45%,transparent);text-decoration-thickness:var(--border-width-1);text-underline-offset:.18em}.system-link:hover{text-decoration-color:currentColor}.system-link:focus-visible{outline:var(--outline-width-2) solid var(--theme-primary);outline-offset:var(--outline-offset-2);border-radius:var(--radius-1)}.system-link[aria-current=page]{font-weight:var(--font-weight-700)}.system-link__external{font-size:.8em}</style>
