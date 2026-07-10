import { beforeEach, describe, expect, it } from 'vitest'

import { getToken } from '@/shared/api/token'

import { useSessionStore } from './store'

describe('useSessionStore', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useSessionStore.getState().clearSession()
  })

  it('setSession stores the token in both store and localStorage', () => {
    useSessionStore.getState().setSession({
      token: 'jwt-abc',
      userId: 'user-1',
      workspaceId: 'ws-1',
    })

    expect(useSessionStore.getState().token).toBe('jwt-abc')
    expect(useSessionStore.getState().workspaceId).toBe('ws-1')
    expect(getToken()).toBe('jwt-abc')
  })

  it('clearSession wipes both store and localStorage', () => {
    useSessionStore.getState().setSession({
      token: 'jwt-abc',
      userId: 'user-1',
      workspaceId: 'ws-1',
    })

    useSessionStore.getState().clearSession()

    expect(useSessionStore.getState().token).toBeNull()
    expect(getToken()).toBeNull()
  })
})
