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

  it('처음엔 숨겨진 상태다', () => {
    const { result } = renderHook(() => useAutoHideToast())
    expect(result.current.shown).toBe(false)
  })

  it('show() 호출하면 토스트가 보인다', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    expect(result.current.shown).toBe(true)
  })

  it('TOAST_DURATION 지나면 자동으로 숨겨진다', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => vi.advanceTimersByTime(TOAST_DURATION))
    expect(result.current.shown).toBe(false)
  })

  it('TOAST_DURATION 되기 직전까지는 계속 보인다', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => vi.advanceTimersByTime(TOAST_DURATION - 1))
    expect(result.current.shown).toBe(true)
  })

  it('hide()는 즉시 숨기고 예정된 자동-hide 타이머도 취소한다', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => result.current.hide())
    expect(result.current.shown).toBe(false)

    // 원래 타이머가 확실히 정리됐는지 확인 — 지나도 에러 없고
    // 상태가 되살아나지도 않아야 함
    act(() => vi.advanceTimersByTime(TOAST_DURATION))
    expect(result.current.shown).toBe(false)
  })

  it('show()를 다시 호출하면 이전 타이머 대신 새로 리셋된다 (경합 케이스)', () => {
    const { result } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    act(() => vi.advanceTimersByTime(TOAST_DURATION - 500))
    // 첫 타이머 만료 전에 두 번째 트리거 발생
    act(() => result.current.show())
    // 원래 타이머 만료 시점은 지났지만, 리셋된 타이머는 아직 안 지남
    act(() => vi.advanceTimersByTime(500))
    expect(result.current.shown).toBe(true)
    // 리셋된 타이머의 전체 duration이 지금 다 지남
    act(() => vi.advanceTimersByTime(TOAST_DURATION - 500))
    expect(result.current.shown).toBe(false)
  })

  it('unmount 시 대기 중이던 타이머가 정리된다 (unmount 후 상태 업데이트 없음)', () => {
    const { result, unmount } = renderHook(() => useAutoHideToast())
    act(() => result.current.show())
    unmount()
    expect(() => act(() => vi.advanceTimersByTime(TOAST_DURATION))).not.toThrow()
  })
})
