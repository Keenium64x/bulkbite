<script setup>
import { reactiveOmit } from "@vueuse/core";
import { AccordionContent } from "reka-ui";
import { cn } from "@/lib/utils";

const props = defineProps({
  forceMount: { type: Boolean, required: false },
  asChild: { type: Boolean, required: false },
  as: { type: null, required: false },
  class: {
    type: [Boolean, null, String, Object, Array],
    required: false,
    skipCheck: true,
  },
});

const delegatedProps = reactiveOmit(props, "class");
</script>

<template>
  <AccordionContent
    v-bind="delegatedProps"
    class="overflow-hidden text-sm data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down"
  >
    <div :class="cn('system-accordion-content', props.class)">
      <slot />
    </div>
  </AccordionContent>
</template>

<style scoped>
.system-accordion-content {
  padding: 0 var(--spacing-m) var(--spacing-m);
}
</style>
