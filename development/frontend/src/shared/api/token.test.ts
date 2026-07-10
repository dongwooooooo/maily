import { beforeEach, describe, expect, it } from 'vitest'

import { clearToken, getToken, setToken } from './token'

describe('session token storage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('round-trips a token', () => {
    setToken('jwt-abc')
    expect(getToken()).toBe('jwt-abc')
  })

  it('returns null when nothing stored', () => {
    expect(getToken()).toBeNull()
  })

  it('clears the token', () => {
    setToken('jwt-abc')
    clearToken()
    expect(getToken()).toBeNull()
  })

  it('returns null instead of throwing when localStorage is unavailable', () => {
    const original = window.localStorage.getItem
    window.localStorage.getItem = () => {
      throw new DOMException('quota', 'QuotaExceededError')
    }
    try {
      expect(getToken()).toBeNull()
    } finally {
      window.localStorage.getItem = original
    }
  })
})
