<script setup>
import { VisualSurface, surface } from "@/desyium"

// Neutral construction proof only. Replace through the project brand primitive plan.
const recipe = surface({
  id: "starter-surface",
  on: "[data-page='starter']",
  layers: [
  "solid-field",
  "surface-frame",
  "grain"
],
})
import { useDesyiumPageExperiences } from "@/desyium/use-desyium-page-experiences.js"
import { mountEntranceHierarchy } from "@/experiences/entrance-hierarchy.js"

useDesyiumPageExperiences([{ root: "[data-experience-root]", mount: mountEntranceHierarchy }])
</script>

<template>
  <main data-page="starter" data-experience-root class="starter">
    <VisualSurface :recipe="recipe" />
    <section class="starter__content" data-experience-item>
      <p class="starter__eyebrow" data-experience-item>Desyium · Website preset</p>
      <h1 data-experience-item>The system is installed.</h1>
      <p data-experience-item>Build through the generated public route, selected components, and code-owned visual recipes.</p>
    </section>
  </main>
</template>

<style scoped>
.starter{position:relative;isolation:isolate;display:grid;min-height:100vh;place-items:center;padding:var(--spacing-l);overflow:hidden}.starter__content{position:relative;z-index:1;width:min(44rem,100%)}.starter__eyebrow{color:var(--theme-primary);font-size:var(--font-size--1);letter-spacing:.12em;text-transform:uppercase}h1{font:var(--font-weight-bold) var(--font-size-4)/var(--font-line-height-1) var(--font-family-a);margin:var(--spacing-xs) 0}p{font-size:var(--font-size-0);line-height:var(--font-line-height-5)}
</style>
