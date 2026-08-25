<script setup>
import { computed } from "vue"
import { Check, Minus } from "lucide-vue-next"
import { CheckboxIndicator, CheckboxRoot } from "reka-ui"

// =============================================================================
// region SHADCN CHECKBOX OWNER
// =============================================================================

const props = defineProps({
  modelValue: { type: [Boolean, Number, String], default: false },
  label: { type: String, default: "" },
  disabled: { type: Boolean, default: false },
  indeterminate: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const checked = computed(() => props.indeterminate ? "indeterminate" : Boolean(Number(props.modelValue) || props.modelValue === true))

function updateChecked(value) {
  emit("update:modelValue", value === true)
}

// endregion SHADCN CHECKBOX OWNER
</script>

<template>
  <label class="system-checkbox" :class="{ 'is-disabled': disabled }">
    <CheckboxRoot class="system-checkbox__control" :model-value="checked" :disabled="disabled" @update:model-value="updateChecked">
      <CheckboxIndicator class="system-checkbox__indicator">
        <Minus v-if="indeterminate" aria-hidden="true" />
        <Check v-else aria-hidden="true" />
      </CheckboxIndicator>
    </CheckboxRoot>
    <span v-if="label || $slots.default" class="system-checkbox__label"><slot>{{ label }}</slot></span>
  </label>
</template>

<style scoped>
.system-checkbox{display:inline-flex;align-items:center;gap:var(--spacing-xs);min-width:0;min-height:2.5rem;color:var(--theme-text);font-size:var(--font-size--1);line-height:1.35;cursor:pointer}.system-checkbox__control{display:flex;flex:0 0 1.125rem;align-items:center;justify-content:center;width:1.125rem;height:1.125rem;padding:0;border:var(--border-width-1) solid var(--theme-border);border-radius:.3rem;background:var(--theme-field);color:var(--theme-primary-foreground);box-shadow:inset 0 1px 0 color-mix(in oklch,var(--theme-surface-raised) 65%,transparent);line-height:1}.system-checkbox__control:hover{border-color:var(--theme-text-muted)}.system-checkbox__control:focus-visible{outline:2px solid var(--theme-text);outline-offset:2px}.system-checkbox__control[data-state="checked"],.system-checkbox__control[data-state="indeterminate"]{border-color:var(--theme-primary);background:var(--theme-primary);color:var(--theme-primary-foreground)!important;box-shadow:none}.system-checkbox__indicator{display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:var(--theme-primary-foreground)!important;line-height:0}.system-checkbox__indicator :deep(svg){display:block;width:.8rem;height:.8rem;color:var(--theme-primary-foreground)!important;stroke:var(--theme-primary-foreground)!important;stroke-width:2.5}.system-checkbox__label{min-width:0}.system-checkbox.is-disabled{cursor:not-allowed;opacity:.58}
</style>
