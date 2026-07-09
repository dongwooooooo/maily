'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

const TOAST_DURATION = 3000

/** Undo-toast timer: shows on demand, auto-hides after TOAST_DURATION, cancellable. */
export function useAutoHideToast() {
  const [shown, setShown] = useState(false)
  const timerRef = useRef<number | null>(null)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const hide = useCallback(() => {
    clearTimer()
    setShown(false)
  }, [clearTimer])

  const show = useCallback(() => {
    clearTimer()
    setShown(true)
    timerRef.current = window.setTimeout(() => setShown(false), TOAST_DURATION)
  }, [clearTimer])

  useEffect(() => clearTimer, [clearTimer])

  return { shown, show, hide }
}
