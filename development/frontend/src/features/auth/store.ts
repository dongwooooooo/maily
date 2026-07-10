/**
 * 세션 스토어 — 토큰은 shared/api/token.ts(localStorage)가 원본이고,
 * 이 스토어는 화면 리렌더용 미러다. 로그인/로그아웃은 반드시 이 스토어의
 * 액션을 통해 이뤄져야 토큰 저장과 상태가 어긋나지 않는다.
 */

import { create } from 'zustand'

import { clearToken, getToken, setToken } from '@/shared/api/token'

export interface SessionState {
  token: string | null
  userId: string | null
  workspaceId: string | null
  setSession: (session: { token: string; userId: string; workspaceId: string }) => void
  clearSession: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  // 초기값은 localStorage의 토큰 — 새로고침 후에도 세션이 이어진다.
  token: getToken(),
  userId: null,
  workspaceId: null,
  setSession: ({ token, userId, workspaceId }) => {
    setToken(token)
    set({ token, userId, workspaceId })
  },
  clearSession: () => {
    clearToken()
    set({ token: null, userId: null, workspaceId: null })
  },
}))
