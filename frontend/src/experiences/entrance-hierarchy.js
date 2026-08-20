import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

// =============================================================================
// region ENTRANCE HIERARCHY EXPERIENCE
// =============================================================================

export const mountEntranceHierarchy = (root, options = {}) => {
  const items = gsap.utils.toArray(options.items ?? "[data-experience-item]", root)
  if (!items.length) return () => {}
  const media = gsap.matchMedia(root)
  media.add({ reduceMotion: "(prefers-reduced-motion: reduce)", narrow: "(max-width: 767px)" }, (context) => {
    const { reduceMotion, narrow } = context.conditions
    if (reduceMotion) return gsap.set(items, { clearProps: "all" })
    gsap.from(items, { autoAlpha: 0, y: narrow ? 18 : 32, duration: narrow ? 0.55 : 0.75, stagger: 0.08, ease: "power3.out", scrollTrigger: { trigger: root, start: "clamp(top 82%)", once: true } })
  })
  return () => media.revert()
}

// endregion ENTRANCE HIERARCHY EXPERIENCE
