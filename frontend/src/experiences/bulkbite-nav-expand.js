import { Flip } from "gsap/Flip"
import { gsap } from "gsap"

gsap.registerPlugin(Flip)

// =============================================================================
// region FLIP LAYOUT EXPERIENCE
// =============================================================================

export const mountFlipLayoutTransition = (root, options = {}) => {
  let active = null
  const selector = options.items ?? "[data-flip-id]"
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)")
  const transition = async (mutate) => {
    const items = gsap.utils.toArray(selector, root)
    const state = reduceMotion.matches ? null : Flip.getState(items)
    await mutate()
    active?.kill()
    active = state ? Flip.from(state, { duration: options.duration ?? 0.65, ease: options.ease ?? "power3.inOut", absolute: options.absolute ?? true, prune: true }) : null
    return active
  }
  root.desyiumFlipTransition = transition
  return { transition, destroy: () => { active?.kill(); delete root.desyiumFlipTransition } }
}

// endregion FLIP LAYOUT EXPERIENCE
