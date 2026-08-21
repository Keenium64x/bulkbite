<script setup>
import { computed } from "vue"
import { SystemCombobox, SystemOperationalButton } from "@/desyium"

// =============================================================================
// region LINKED RECORD FIELD STATION
// =============================================================================

const props = defineProps({
  modelValue: { type: [String, null], default: null },
  label: { type: String, required: true },
  description: { type: String, default: "" },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: "Choose a record" },
  disabled: { type: Boolean, default: false },
  invalid: { type: Boolean, default: false },
  error: { type: String, default: "" },
  loading: { type: Boolean, default: false },
  createLabel: { type: String, default: "Create new" },
  manageLabel: { type: String, default: "Manage records" },
})

const emit = defineEmits(["update:modelValue", "create", "manage"])
const fieldId = `linked-record-${Math.random().toString(36).slice(2, 10)}`
const descriptionId = computed(() => props.description ? `${fieldId}-description` : undefined)
const errorId = computed(() => props.error ? `${fieldId}-error` : undefined)
const describedBy = computed(() => [descriptionId.value, errorId.value].filter(Boolean).join(" ") || undefined)

// endregion LINKED RECORD FIELD STATION
</script>

<template>
  <div class="system-linked-record-field" :class="{ 'is-invalid': invalid || error }">
    <label class="system-linked-record-field__label" :for="fieldId">{{ label }}</label>
    <p v-if="description" :id="descriptionId" class="system-linked-record-field__description">{{ description }}</p>
    <SystemCombobox
      :id="fieldId"
      :model-value="modelValue"
      :options="options"
      :placeholder="placeholder"
      :disabled="disabled"
      :loading="loading"
      :aria-invalid="invalid || Boolean(error)"
      :aria-describedby="describedBy"
      trigger="button"
      variant="subtle"
      size="lg"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <template #empty="{ query }">
        <span>{{ query ? `No records match “${query}”.` : "No records available." }}</span>
      </template>
      <template #footer>
        <div class="system-linked-record-field__actions">
          <SystemOperationalButton variant="ghost" size="sm" @click="emit('manage')">{{ manageLabel }}</SystemOperationalButton>
          <SystemOperationalButton variant="subtle" size="sm" @click="emit('create')">{{ createLabel }}</SystemOperationalButton>
        </div>
      </template>
    </SystemCombobox>
    <p v-if="error" :id="errorId" class="system-linked-record-field__error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.system-linked-record-field{display:grid;align-content:start;gap:var(--spacing-3xs);min-width:0}.system-linked-record-field__label{color:var(--theme-text);font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.system-linked-record-field__description{margin:0;color:var(--theme-text-muted);font-size:var(--font-size--2);line-height:1.4}.system-linked-record-field :deep([data-slot="trigger"]){width:100%;min-height:2.75rem}.system-linked-record-field__actions{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-2xs);padding:var(--spacing-2xs);border-top:var(--border-width-1) solid var(--theme-border)}.system-linked-record-field__error{margin:0;color:var(--theme-error);font-size:var(--font-size--2);line-height:1.4}.system-linked-record-field.is-invalid :deep([data-slot="trigger"]){border-color:var(--theme-error)}
</style>
