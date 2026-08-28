import { runtimeConfig } from "@/config/runtime"
import { computed, onBeforeUnmount, onMounted, reactive } from "vue"


// =============================================================================
// region NATIVE PULL TO REFRESH STATION
// =============================================================================

const REFRESH_THRESHOLD = 80
const REVEAL_THRESHOLD = 24
const MAX_PULL_DISTANCE = 116
const OUTCOME_HOLD_MS = 800

export const NATIVE_REFRESH_REPLAY_EVENT = "bulkbite:native-refresh-replay"

export const pullToRefreshState = reactive({
  distance: 0,
  pulling: false,
  refreshing: false,
  outcome: "",
})

export const pullToRefreshArmed = computed(() => pullToRefreshState.distance >= REFRESH_THRESHOLD)
export const pullToRefreshProgress = computed(() => Math.min(pullToRefreshState.distance / REFRESH_THRESHOLD, 1))

let activeRefresh = null
let outcomeTimer = null

export function createNativePullController(refresh) {
  let touchStartX = null
  let touchStartY = null
  let tracking = false
  let scrollSurface = null

  function handleTouchStart(event) {
    if (!runtimeConfig.isNative || pullToRefreshState.refreshing || event.touches.length !== 1 || shouldIgnoreTarget(event.target)) return
    scrollSurface = resolveScrollSurface(event.target)
    if (!isScrollSurfaceAtTop(scrollSurface)) return
    clearOutcome()
    touchStartX = event.touches[0].clientX
    touchStartY = event.touches[0].clientY
    tracking = true
  }

  function handleTouchMove(event) {
    if (!tracking || touchStartY === null || event.touches.length !== 1) return
    const horizontalDistance = Math.abs(event.touches[0].clientX - touchStartX)
    const verticalDistance = event.touches[0].clientY - touchStartY
    if (horizontalDistance > Math.max(12, Math.abs(verticalDistance) * 0.8)) {
      resetPull()
      return
    }
    if (verticalDistance <= 0 || !isScrollSurfaceAtTop(scrollSurface)) {
      resetPull()
      return
    }
    event.preventDefault()
    pullToRefreshState.distance = Math.min(MAX_PULL_DISTANCE, Math.round(verticalDistance * 0.5))
    pullToRefreshState.pulling = pullToRefreshState.distance >= REVEAL_THRESHOLD
  }

  async function handleTouchEnd() {
    if (!tracking) return false
    const shouldRefresh = pullToRefreshArmed.value
    stopTracking()
    if (!shouldRefresh) {
      resetPull()
      return false
    }
    pullToRefreshState.refreshing = true
    pullToRefreshState.pulling = false
    pullToRefreshState.distance = REFRESH_THRESHOLD
    let outcome = "success"
    try {
      activeRefresh ||= Promise.resolve().then(refresh).finally(() => { activeRefresh = null })
      if ((await activeRefresh) === false) outcome = "error"
    } catch {
      outcome = "error"
    } finally {
      pullToRefreshState.refreshing = false
      showOutcome(outcome)
    }
    return true
  }

  function stopTracking() {
    tracking = false
    touchStartX = null
    touchStartY = null
    scrollSurface = null
  }

  function resetPull() {
    stopTracking()
    pullToRefreshState.pulling = false
    if (!pullToRefreshState.refreshing && !pullToRefreshState.outcome) pullToRefreshState.distance = 0
  }

  return { handleTouchStart, handleTouchMove, handleTouchEnd, resetPull }
}

export function useNativePullToRefresh(refresh) {
  const controller = createNativePullController(refresh)
  onMounted(() => {
    if (!runtimeConfig.isNative) return
    window.addEventListener("touchstart", controller.handleTouchStart, { passive: true })
    window.addEventListener("touchmove", controller.handleTouchMove, { passive: false })
    window.addEventListener("touchend", controller.handleTouchEnd, { passive: true })
    window.addEventListener("touchcancel", controller.resetPull, { passive: true })
  })
  onBeforeUnmount(() => {
    window.removeEventListener("touchstart", controller.handleTouchStart)
    window.removeEventListener("touchmove", controller.handleTouchMove)
    window.removeEventListener("touchend", controller.handleTouchEnd)
    window.removeEventListener("touchcancel", controller.resetPull)
    controller.resetPull()
    clearOutcome()
  })
}

function resolveScrollSurface(target) {
  let element = target instanceof Element ? target : null
  while (element && element !== document.body && element !== document.documentElement) {
    const { overflowY } = window.getComputedStyle(element)
    if (/(auto|scroll|overlay)/.test(overflowY) && element.scrollHeight > element.clientHeight + 1) return element
    element = element.parentElement
  }
  return document.scrollingElement || document.documentElement
}

function isScrollSurfaceAtTop(scrollSurface) {
  if (!scrollSurface) return window.scrollY <= 1
  const isRoot = scrollSurface === document.documentElement || scrollSurface === document.body
  return (isRoot ? window.scrollY : scrollSurface.scrollTop) <= 1
}

function shouldIgnoreTarget(target) {
  return target instanceof Element && Boolean(target.closest("input, textarea, select, [contenteditable='true'], [data-native-pull-ignore]"))
}

function showOutcome(outcome) {
  pullToRefreshState.pulling = false
  pullToRefreshState.outcome = outcome
  pullToRefreshState.distance = REFRESH_THRESHOLD
  if (outcome === "success") window.dispatchEvent(new CustomEvent(NATIVE_REFRESH_REPLAY_EVENT))
  window.clearTimeout(outcomeTimer)
  outcomeTimer = window.setTimeout(clearOutcome, OUTCOME_HOLD_MS)
}

function clearOutcome() {
  window.clearTimeout(outcomeTimer)
  outcomeTimer = null
  pullToRefreshState.outcome = ""
  if (!pullToRefreshState.refreshing && !pullToRefreshState.pulling) pullToRefreshState.distance = 0
}


// endregion NATIVE PULL TO REFRESH STATION
