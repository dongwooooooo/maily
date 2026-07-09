import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TOAST_DURATION, useAutoHideToast } from './useAutoHideToast'

describe('useAutoHideToast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts hidden', () => {
    const { result } = renderHook(() => useAutoHideToast())
    expect(result.current.shown).toBe(false)
  })

  it('show() reveals the toast', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    expect(result.current.shown).toBe(true)
  })

  it('auto-hides after TOAST_DURATION', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => vi.advanceTimersByTime(TOAST_DURATION))
    expect(result.current.shown).toBe(false)
  })

  it('stays shown just before TOAST_DURATION elapses', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => vi.advanceTimersByTime(TOAST_DURATION - 1))
    expect(result.current.shown).toBe(true)
  })

  it('hide() dismisses immediately and cancels the pending auto-hide', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => result.current.hide())
    expect(result.current.shown).toBe(false)

    // the original timer must be cleared — advancing past it must not throw
    // or otherwise resurrect a stale state update
    act(() => vi.advanceTimersByTime(TOAST_DURATION))
    expect(result.current.shown).toBe(false)
  })

  it('re-triggering show() resets the timer instead of stacking two hides', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => vi.advanceTimersByTime(TOAST_DURATION - 500))
    // second trigger arrives before the first would have fired
    act(() => result.current.show())
    // original timer's fire time has now passed, but the reset timer hasn't
    act(() => vi.advanceTimersByTime(500))
    expect(result.current.shown).toBe(true)
    // now the reset timer's own full duration elapses
    act(() => vi.advanceTimersByTime(TOAST_DURATION - 500))
    expect(result.current.shown).toBe(false)
  })

  it('clears the pending timer on unmount (no state update after unmount)', () => {
    const { result, unmount } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    unmount()
    expect(() => act(() => vi.advanceTimersByTime(TOAST_DURATION))).not.toThrow()
  })
})
