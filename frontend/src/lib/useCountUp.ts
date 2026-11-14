import { useEffect, useRef, useState } from 'react'

export function useCountUp(target: number, durationMs: number): number {
  const [prefersReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const skipAnimation = prefersReduced || durationMs === 0

  const [value, setValue] = useState(() => (skipAnimation ? target : 0))
  const [lastSkippedTarget, setLastSkippedTarget] = useState<number | null>(skipAnimation ? target : null)

  if (skipAnimation && lastSkippedTarget !== target) {
    setLastSkippedTarget(target)
    setValue(target)
  }

  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (skipAnimation) return
    startRef.current = null
    let frame: number
    const step = (timestamp: number) => {
      if (startRef.current == null) startRef.current = timestamp
      const elapsed = timestamp - startRef.current
      const progress = Math.min(elapsed / durationMs, 1)
      setValue(Math.round(target * progress))
      if (progress < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs, skipAnimation])

  return value
}
