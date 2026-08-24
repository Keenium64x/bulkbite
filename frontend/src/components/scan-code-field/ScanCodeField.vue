<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import { BrowserMultiFormatReader } from "@zxing/browser"
import { Camera, CameraOff, ScanBarcode, ScanLine } from "lucide-vue-next"
import { SystemFormControl, SystemOperationalButton } from "@/desyium"

// =============================================================================
// region SCAN CODE CAPTURE STATION
// =============================================================================

const props = defineProps({
  modelValue: { type: String, default: "" },
  label: { type: String, default: "QR or barcode" },
  disabled: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  autofocus: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "scan"])
const input = ref(null)
const video = ref(null)
const cameraActive = ref(false)
const cameraStarting = ref(false)
const cameraCapturing = ref(false)
const cameraError = ref("")
const cameraSupported = typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia)
let stream = null
const decoder = new BrowserMultiFormatReader()

function submit() {
  const code = String(props.modelValue || "").trim()
  if (!code || props.disabled || props.busy) return
  emit("scan", code)
}

function focus() {
  input.value?.$el?.querySelector?.("input")?.focus()
}

async function startCamera() {
  cameraError.value = ""
  if (!cameraSupported) {
    cameraError.value = "Camera access needs a supported browser on localhost or HTTPS."
    return
  }
  if (cameraActive.value || cameraStarting.value) return
  cameraStarting.value = true
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    })
    cameraActive.value = true
    await nextTick()
    if (!video.value) throw new Error("Camera preview was not mounted.")
    video.value.srcObject = stream
    await video.value.play()
  } catch (caught) {
    stopCamera()
    if (caught?.name === "NotAllowedError") cameraError.value = "Camera permission was not granted. Allow camera access in the browser, then try again."
    else if (caught?.name === "NotFoundError") cameraError.value = "No camera was found on this device."
    else if (caught?.name === "NotReadableError") cameraError.value = "The camera is already in use by another app or browser tab."
    else cameraError.value = "The camera could not start. Use localhost or HTTPS, then check the browser camera permission."
  } finally {
    cameraStarting.value = false
  }
}

async function captureBarcode() {
  if (!cameraActive.value || !video.value || cameraCapturing.value) return
  cameraCapturing.value = true
  cameraError.value = ""
  try {
    if (!video.value.videoWidth || !video.value.videoHeight) {
      throw new Error("The camera is not ready yet.")
    }
    const canvas = document.createElement("canvas")
    canvas.width = video.value.videoWidth
    canvas.height = video.value.videoHeight
    const context = canvas.getContext("2d", { willReadFrequently: true })
    if (!context) throw new Error("The camera frame could not be read.")
    context.drawImage(video.value, 0, 0, canvas.width, canvas.height)
    const result = decoder.decodeFromCanvas(canvas)
    const value = result?.getText?.() || String(result?.text || "")
    if (!value) throw new Error("No barcode value was found.")
    emit("update:modelValue", value)
    stopCamera()
    await nextTick()
    emit("scan", value)
  } catch (caught) {
    cameraError.value = "No barcode was found in that capture. Fill the frame with one code, hold still, and capture again."
  } finally {
    cameraCapturing.value = false
  }
}

function stopCamera() {
  cameraActive.value = false
  cameraStarting.value = false
  stream?.getTracks().forEach((track) => track.stop())
  stream = null
  if (video.value) video.value.srcObject = null
}

onMounted(() => { if (props.autofocus) focus() })
onBeforeUnmount(stopCamera)
defineExpose({ focus, stopCamera })

// endregion SCAN CODE CAPTURE STATION
</script>

<template>
  <div class="system-scan-code-field">
    <form class="system-scan-code-field__entry" @submit.prevent="submit">
      <SystemFormControl ref="input" :model-value="modelValue" :label="label" placeholder="Scan or type code" size="lg" :disabled="disabled || busy" autocomplete="off" inputmode="text" @update:model-value="emit('update:modelValue', $event)" />
      <SystemOperationalButton type="submit" theme="blue" variant="solid" size="lg" :loading="busy" :disabled="disabled || !String(modelValue).trim()">
        <ScanBarcode aria-hidden="true" />
        Find item
      </SystemOperationalButton>
      <SystemOperationalButton v-if="!cameraActive" type="button" variant="outline" size="lg" :loading="cameraStarting" :disabled="disabled" @click="startCamera">
        <Camera aria-hidden="true" />
        Scan with camera
      </SystemOperationalButton>
    </form>
    <p>USB and Bluetooth scanners work here as keyboard input. Scan codes keep their leading zeroes.</p>
    <p v-if="!cameraSupported">Camera access is unavailable in this browser. Hardware scanners and typed codes still work.</p>
    <p v-if="cameraError" class="system-scan-code-field__error" role="alert">{{ cameraError }}</p>
    <div v-if="cameraActive" class="system-scan-code-field__camera" role="region" aria-label="Live barcode camera">
      <video ref="video" muted playsinline autoplay aria-label="Camera preview for QR or barcode scanning" />
      <p>Fill the camera view with one QR code or barcode, hold still, then capture it.</p>
      <div class="system-scan-code-field__camera-actions">
        <SystemOperationalButton type="button" theme="blue" variant="solid" size="lg" :loading="cameraCapturing" @click="captureBarcode">
          <ScanLine aria-hidden="true" />
          Capture barcode
        </SystemOperationalButton>
        <SystemOperationalButton type="button" variant="outline" size="lg" @click="stopCamera">
          <CameraOff aria-hidden="true" />
          Cancel
        </SystemOperationalButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.system-scan-code-field{display:grid;gap:var(--spacing-2xs);min-width:0}.system-scan-code-field__entry{display:grid;grid-template-columns:minmax(14rem,1fr) auto auto;gap:var(--spacing-xs);align-items:end}.system-scan-code-field__entry :deep(svg),.system-scan-code-field__camera-actions :deep(svg){width:1rem;height:1rem}.system-scan-code-field>p,.system-scan-code-field__camera p{margin:0;color:var(--theme-text-muted);font-size:var(--font-size--2)}.system-scan-code-field__error{color:var(--theme-error)!important}.system-scan-code-field__camera{display:grid;gap:var(--spacing-xs);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-secondary)}.system-scan-code-field__camera video{display:block;width:100%;max-height:22rem;border-radius:var(--component-radius-field);background:var(--theme-text);object-fit:cover}.system-scan-code-field__camera-actions{display:flex;flex-wrap:wrap;gap:var(--spacing-xs)}@media(max-width:52rem){.system-scan-code-field__entry{grid-template-columns:1fr 1fr}.system-scan-code-field__entry>*:first-child{grid-column:1/-1}}@media(max-width:34rem){.system-scan-code-field__entry{grid-template-columns:1fr}.system-scan-code-field__entry>*:first-child{grid-column:auto}.system-scan-code-field__camera-actions>*{width:100%}}
</style>
