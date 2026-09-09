/**
 * Shared count-up animation hook.
 *
 * Animates a numeric value from 0 to `target` inside a referenced
 * `<span>`, triggered when the element scrolls into view
 * (IntersectionObserver, threshold 0.5). Runs once per mount; the
 * `counted` ref guards against re-triggering.
 *
 * Reused by both the LandingPage hero stats and the Overview stat cards.
 */

import { useEffect, useRef } from 'react'

export function useCountUp(target: number, duration = 1200) {
  const ref = useRef<HTMLSpanElement>(null)
  const counted = useRef(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !counted.current) {
          counted.current = true
          const start = performance.now()
          const animate = (now: number) => {
            const elapsed = now - start
            const progress = Math.min(elapsed / duration, 1)
            const eased = 1 - Math.pow(1 - progress, 3)
            el.textContent = Math.round(eased * target).toLocaleString()
            if (progress < 1) requestAnimationFrame(animate)
          }
          requestAnimationFrame(animate)
        }
      },
      { threshold: 0.5 },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [target, duration])

  return ref
}
