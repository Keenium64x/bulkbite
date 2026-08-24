<script setup>
import { computed, ref } from "vue"
import { FilePlus2, RotateCcw, Trash2 } from "lucide-vue-next"
import { SystemOperationalButton } from "@/desyium"

// =============================================================================
// region PRIVATE MULTI-FILE UPLOAD
// =============================================================================

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  accept: { type: String, default: "image/*,.pdf" },
  label: { type: String, default: "Add files" },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "uploaded", "complete", "error"])
const input = ref(null)
const queue = ref([])
const uploading = computed(() => queue.value.some((row) => row.status === "uploading"))

function chooseFiles() {
  if (!props.disabled) input.value?.click()
}

async function addFiles(event) {
  const files = [...(event.target.files || [])]
  event.target.value = ""
  const rows = files.map((file) => ({ id: `${file.name}-${file.size}-${crypto.randomUUID()}`, file, name: file.name, progress: 0, status: "queued", error: "" }))
  queue.value.push(...rows)
  const uploadedFiles = []
  const accumulatedFiles = [...props.modelValue]
  for (const row of rows) {
    const uploaded = await uploadFile(row)
    if (uploaded) {
      uploadedFiles.push(uploaded)
      accumulatedFiles.push(uploaded)
      emit("update:modelValue", [...accumulatedFiles])
    }
  }
  if (uploadedFiles.length) emit("complete", [...accumulatedFiles])
}

function uploadFile(row) {
  row.status = "uploading"
  row.error = ""
  return new Promise((resolve) => {
    const request = new XMLHttpRequest()
    request.open("POST", "/api/method/upload_file")
    request.setRequestHeader("X-Frappe-CSRF-Token", window.csrf_token || window.boot?.csrf_token || "")
    request.upload.addEventListener("progress", (event) => {
      row.progress = event.lengthComputable ? Math.round((event.loaded / event.total) * 100) : 0
    })
    request.addEventListener("load", () => {
      try {
        const payload = JSON.parse(request.responseText || "{}")
        if (request.status < 200 || request.status >= 300 || !payload.message?.file_url) throw new Error(payload.exception || "The file could not be uploaded.")
        const uploaded = { file_url: payload.message.file_url, file_name: payload.message.file_name || row.name }
        row.status = "complete"
        row.progress = 100
        emit("uploaded", uploaded)
        resolve(uploaded)
        return
      } catch (error) {
        row.status = "error"
        row.error = error.message
        emit("error", error)
      }
      resolve(null)
    })
    request.addEventListener("error", () => {
      row.status = "error"
      row.error = "The upload connection failed."
      emit("error", new Error(row.error))
      resolve(null)
    })
    const body = new FormData()
    body.append("file", row.file)
    body.append("is_private", "1")
    request.send(body)
  })
}

async function retryFile(row) {
  const uploaded = await uploadFile(row)
  if (!uploaded) return
  const accumulatedFiles = [...props.modelValue, uploaded]
  emit("update:modelValue", accumulatedFiles)
  emit("complete", accumulatedFiles)
}

function removeUploaded(index) {
  if (!props.disabled) emit("update:modelValue", props.modelValue.filter((_, rowIndex) => rowIndex !== index))
}

// endregion PRIVATE MULTI-FILE UPLOAD
</script>

<template>
  <div class="system-multi-file-uploader">
    <input ref="input" class="system-multi-file-uploader__input" type="file" :accept="accept" multiple :disabled="disabled" @change="addFiles" />
    <SystemOperationalButton variant="outline" :disabled="disabled || uploading" @click="chooseFiles"><FilePlus2 aria-hidden="true" />{{ uploading ? "Uploading files" : label }}</SystemOperationalButton>
    <ul v-if="modelValue.length || queue.length" class="system-multi-file-uploader__list" aria-live="polite">
      <li v-for="(file, index) in modelValue" :key="file.file_url"><div><strong>{{ file.file_name }}</strong><small>Private evidence</small></div><SystemOperationalButton variant="ghost" :disabled="disabled" :label="`Remove ${file.file_name}`" @click="removeUploaded(index)"><Trash2 aria-hidden="true" /></SystemOperationalButton></li>
      <li v-for="row in queue.filter(item => item.status !== 'complete')" :key="row.id"><div><strong>{{ row.name }}</strong><small>{{ row.status === "error" ? row.error : `${row.progress}% uploaded` }}</small></div><SystemOperationalButton v-if="row.status === 'error'" variant="ghost" :label="`Retry ${row.name}`" @click="retryFile(row)"><RotateCcw aria-hidden="true" /></SystemOperationalButton></li>
    </ul>
  </div>
</template>

<style scoped>
.system-multi-file-uploader{display:grid;gap:var(--spacing-xs)}.system-multi-file-uploader__input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}.system-multi-file-uploader__list{display:grid;margin:0;padding:0;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden;list-style:none}.system-multi-file-uploader__list li{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:var(--spacing-xs);min-height:3.5rem;padding:var(--spacing-xs) var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.system-multi-file-uploader__list li:last-child{border-bottom:0}.system-multi-file-uploader__list strong,.system-multi-file-uploader__list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.system-multi-file-uploader__list small{margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.system-multi-file-uploader__list :deep(button){width:2.75rem!important;min-width:2.75rem!important;padding:0!important}.system-multi-file-uploader__list :deep(svg){width:1rem!important;height:1rem!important}
</style>
