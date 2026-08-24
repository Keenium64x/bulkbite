<script setup>
import { CalendarDate, parseDate } from "@internationalized/date"
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-vue-next"
import {
  DatePickerCalendar,
  DatePickerCell,
  DatePickerCellTrigger,
  DatePickerContent,
  DatePickerGrid,
  DatePickerGridBody,
  DatePickerGridHead,
  DatePickerGridRow,
  DatePickerHeadCell,
  DatePickerHeader,
  DatePickerHeading,
  DatePickerNext,
  DatePickerPrev,
  DatePickerRoot,
  DatePickerTrigger,
} from "reka-ui"
import { computed, ref, watch } from "vue"

const props = defineProps({
  modelValue: { type: String, default: "" },
  label: { type: String, default: "" },
  placeholder: { type: String, default: "YYYY-MM-DD" },
  disabled: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
  clearable: { type: Boolean, default: true },
  error: { type: String, default: "" },
  description: { type: String, default: "" },
  min: { type: String, default: "" },
  max: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue", "change"])
const inputId = `date-picker-${Math.random().toString(36).slice(2, 10)}`
const inputValue = ref(props.modelValue || "")
const parseError = ref("")
const calendarValue = computed(() => toCalendarDate(props.modelValue))
const minValue = computed(() => toCalendarDate(props.min))
const maxValue = computed(() => toCalendarDate(props.max))
const errorMessage = computed(() => props.error || parseError.value)
const descriptionId = computed(() => props.description ? `${inputId}-description` : undefined)
const errorId = computed(() => errorMessage.value ? `${inputId}-error` : undefined)
const describedBy = computed(() => [descriptionId.value, errorId.value].filter(Boolean).join(" ") || undefined)

watch(() => props.modelValue, (value) => {
  inputValue.value = value || ""
  parseError.value = ""
})

function toCalendarDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return undefined
  try { return parseDate(value) } catch { return undefined }
}

function emitDate(value) {
  const nextValue = value?.toString?.() || ""
  inputValue.value = nextValue
  parseError.value = ""
  emit("update:modelValue", nextValue)
  emit("change", nextValue)
}

function commitTypedDate() {
  const typed = inputValue.value.trim()
  if (!typed && props.clearable) { emitDate(undefined); return }
  const parsed = toCalendarDate(typed)
  if (!parsed) { parseError.value = "Enter a valid date as YYYY-MM-DD."; return }
  if (minValue.value && parsed.compare(minValue.value) < 0) { parseError.value = `Choose ${props.min} or later.`; return }
  if (maxValue.value && parsed.compare(maxValue.value) > 0) { parseError.value = `Choose ${props.max} or earlier.`; return }
  emitDate(parsed)
}

function calendarPlaceholder() {
  const now = new Date()
  return calendarValue.value || new CalendarDate(now.getFullYear(), now.getMonth() + 1, now.getDate())
}
</script>

<template>
  <div class="system-date-picker" :data-invalid="errorMessage ? '' : undefined">
    <label v-if="label" class="system-date-picker__label" :for="inputId">{{ label }}</label>
    <DatePickerRoot :model-value="calendarValue" :placeholder="calendarPlaceholder()" :min-value="minValue" :max-value="maxValue" :disabled="disabled" :readonly="readonly" :required="required" :prevent-deselect="!clearable" :close-on-select="true" :week-starts-on="1" locale="en-ZA" @update:model-value="emitDate">
      <div class="system-date-picker__control">
        <input :id="inputId" v-model="inputValue" class="system-date-picker__input" inputmode="numeric" autocomplete="off" :placeholder="placeholder" :disabled="disabled" :readonly="readonly" :required="required" :aria-invalid="errorMessage ? 'true' : undefined" :aria-describedby="describedBy" @blur="commitTypedDate" @keydown.enter.prevent="commitTypedDate" />
        <DatePickerTrigger class="system-date-picker__trigger" :aria-label="label ? `Open ${label.toLowerCase()} calendar` : 'Open calendar'"><CalendarDays aria-hidden="true" /></DatePickerTrigger>
      </div>
      <DatePickerContent class="system-date-picker__popover" :side-offset="6" align="start" :collision-padding="12">
        <DatePickerCalendar v-slot="{ weekDays, grid }" class="system-date-picker__calendar" initial-focus fixed-weeks>
          <DatePickerHeader class="system-date-picker__header"><DatePickerPrev class="system-date-picker__nav"><ChevronLeft aria-hidden="true" /></DatePickerPrev><DatePickerHeading class="system-date-picker__heading" /><DatePickerNext class="system-date-picker__nav"><ChevronRight aria-hidden="true" /></DatePickerNext></DatePickerHeader>
          <DatePickerGrid v-for="month in grid" :key="month.value.toString()" class="system-date-picker__grid">
            <DatePickerGridHead><DatePickerGridRow><DatePickerHeadCell v-for="day in weekDays" :key="day" class="system-date-picker__weekday">{{ day }}</DatePickerHeadCell></DatePickerGridRow></DatePickerGridHead>
            <DatePickerGridBody><DatePickerGridRow v-for="(weekDates, index) in month.rows" :key="index"><DatePickerCell v-for="date in weekDates" :key="date.toString()" :date="date" class="system-date-picker__cell"><DatePickerCellTrigger :day="date" :month="month.value" class="system-date-picker__day" /></DatePickerCell></DatePickerGridRow></DatePickerGridBody>
          </DatePickerGrid>
        </DatePickerCalendar>
      </DatePickerContent>
    </DatePickerRoot>
    <p v-if="description" :id="descriptionId" class="system-date-picker__description">{{ description }}</p>
    <p v-if="errorMessage" :id="errorId" class="system-date-picker__error" role="alert">{{ errorMessage }}</p>
  </div>
</template>

<style scoped>
.system-date-picker{display:grid;min-width:0;gap:var(--spacing-3xs)}.system-date-picker__label{color:var(--theme-text);font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.system-date-picker__control{display:grid;grid-template-columns:minmax(0,1fr) 2.75rem;min-height:2.75rem;overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-field);box-shadow:inset 0 1px 0 color-mix(in oklch,var(--theme-surface-raised) 60%,transparent)}.system-date-picker__control:focus-within{outline:2px solid var(--theme-text);outline-offset:2px}.system-date-picker[data-invalid] .system-date-picker__control{border-color:var(--theme-error)}.system-date-picker__input{min-width:0;border:0;outline:0;padding:0 .8rem;background:transparent;color:var(--theme-text);line-height:1.25}.system-date-picker__input::placeholder{color:color-mix(in oklch,var(--theme-text-muted) 78%,var(--theme-field));opacity:1}.system-date-picker__trigger{display:grid;place-items:center;min-width:2.75rem;border:0;border-left:var(--border-width-1) solid var(--theme-border);background:var(--theme-secondary);color:var(--theme-text-muted)}.system-date-picker__trigger:hover{color:var(--theme-text)}.system-date-picker__trigger svg{width:1rem;height:1rem}.system-date-picker__input:disabled,.system-date-picker__trigger:disabled{cursor:not-allowed;color:var(--theme-text-muted);opacity:.72}.system-date-picker__description,.system-date-picker__error{margin:0;font-size:var(--font-size--2);line-height:var(--font-line-height-4)}.system-date-picker__description{color:var(--theme-text-muted)}.system-date-picker__error{color:var(--theme-error)}
:global(.system-date-picker__popover){z-index:90;width:19rem;max-width:calc(100vw - 1.5rem);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-popup);color:var(--theme-text);box-shadow:0 14px 32px color-mix(in oklch,var(--theme-text) 16%,transparent)}.system-date-picker__calendar{width:100%;padding:.75rem}.system-date-picker__header{display:grid;grid-template-columns:2.25rem minmax(0,1fr) 2.25rem;align-items:center;gap:.5rem;margin-bottom:.5rem}.system-date-picker__heading{text-align:center;font-weight:var(--font-weight-600)}.system-date-picker__nav{display:grid;place-items:center;width:2.25rem;height:2.25rem;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-button);background:var(--theme-secondary);color:var(--theme-text)}.system-date-picker__nav svg{width:1rem;height:1rem}.system-date-picker__grid{width:17.25rem;min-width:0;border-collapse:separate;border-spacing:2px;table-layout:fixed}.system-date-picker__weekday{width:2.25rem;height:1.75rem;padding:0;background:transparent;color:var(--theme-text-muted);text-align:center;font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.system-date-picker__cell{width:2.25rem;height:2.25rem;padding:0;border:0}.system-date-picker__day{display:grid;place-items:center;width:2.25rem;min-width:2.25rem;height:2.25rem;border-radius:var(--component-radius-button);color:var(--theme-text);font-variant-numeric:tabular-nums}.system-date-picker__day:hover{background:var(--theme-secondary)}.system-date-picker__day[data-selected]{background:var(--theme-primary);color:var(--theme-primary-foreground)}.system-date-picker__day[data-today]:not([data-selected]){box-shadow:inset 0 0 0 1px var(--theme-text-muted)}.system-date-picker__day[data-outside-view]{color:var(--theme-text-muted);opacity:.45}.system-date-picker__day[data-disabled],.system-date-picker__day[data-unavailable]{cursor:not-allowed;color:var(--theme-text-muted);opacity:.35}.system-date-picker__day[data-focused]{outline:2px solid var(--theme-text);outline-offset:-2px}@media(max-width:24rem){.system-date-picker__calendar{padding:.55rem}.system-date-picker__grid{width:15.5rem;border-spacing:1px}.system-date-picker__weekday,.system-date-picker__cell,.system-date-picker__day{width:2rem}.system-date-picker__day{min-width:2rem;height:2rem}}
</style>
