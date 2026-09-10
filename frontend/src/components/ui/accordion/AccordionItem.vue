<script setup>
import { reactiveOmit } from "@vueuse/core";
import { AccordionItem, useForwardProps } from "reka-ui";
import { cn } from "@/lib/utils";

const props = defineProps({
  disabled: { type: Boolean, required: false },
  value: { type: String, required: true },
  unmountOnHide: { type: Boolean, required: false },
  asChild: { type: Boolean, required: false },
  as: { type: null, required: false },
  class: {
    type: [Boolean, null, String, Object, Array],
    required: false,
    skipCheck: true,
  },
});

const delegatedProps = reactiveOmit(props, "class");

const forwardedProps = useForwardProps(delegatedProps);
</script>

<template>
  <AccordionItem v-bind="forwardedProps" :class="cn('system-accordion-card', props.class)">
    <slot />
  </AccordionItem>
</template>

<style scoped>
.system-accordion-card {
  overflow: hidden;
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-block);
  background: var(--theme-surface);
  box-shadow: 0 1px 2px color-mix(in oklch, var(--theme-text) 5%, transparent);
}
</style>
