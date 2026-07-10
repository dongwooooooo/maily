/**
 * Google Identity Services(GIS) 로그인 훅.
 *
 * 흐름: GIS 스크립트 로드 → initialize(client_id, callback) → 공식 버튼
 * render → 사용자가 로그인하면 credential(id_token) 수신 →
 * POST /auth/google/callback → 자체 JWT 저장 → 오늘 브리핑(/)으로 이동.
 *
 * 커스텀 버튼으로는 id_token을 받을 수 없어(GIS 정책) 공식 renderButton을
 * 쓴다 — 01-login.html 목업의 자체 버튼과 시각이 다른 점은 알려진 차이.
 */

'use client'

import { useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'

import { apiClient } from '@/shared/api/client'
import { toApiError } from '@/shared/api/errors'

import { useSessionStore } from './store'

interface GoogleCredentialResponse {
  credential: string
}

interface GoogleIdApi {
  initialize: (config: {
    client_id: string
    callback: (response: GoogleCredentialResponse) => void
  }) => void
  renderButton: (
    parent: HTMLElement,
    options: { theme?: string; size?: string; text?: string; width?: number },
  ) => void
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleIdApi } }
  }
}

export const GIS_SCRIPT_SRC = 'https://accounts.google.com/gsi/client'

export function useGoogleLogin() {
  const router = useRouter()
  const setSession = useSessionStore((state) => state.setSession)
  const [error, setError] = useState(false)

  const handleCredential = useCallback(
    async ({ credential }: GoogleCredentialResponse) => {
      const { data, error, response } = await apiClient.POST('/auth/google/callback', {
        body: { id_token: credential },
      })
      if (error) {
        // 에러 코드는 개발자용 — 화면에는 카피만 노출하고 코드는 콘솔로.
        console.error('로그인 실패', toApiError(response.status, error))
        setError(true)
        return
      }
      setSession({
        token: data.token,
        userId: data.user_id,
        workspaceId: data.workspace_id,
      })
      router.replace('/')
    },
    [router, setSession],
  )

  const renderGoogleButton = useCallback(
    (container: HTMLElement) => {
      const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
      if (!clientId) {
        console.error('NEXT_PUBLIC_GOOGLE_CLIENT_ID 미설정 — .env.local 확인')
        setError(true)
        return
      }
      const googleId = window.google?.accounts.id
      if (!googleId) {
        console.error('GIS 스크립트 미로드 상태에서 renderButton 호출')
        setError(true)
        return
      }
      // dev Strict Mode의 mount→unmount→mount에서 onReady가 두 번 불려도
      // 같은 컨테이너에 중복 주입하지 않는다.
      if (container.childElementCount > 0) return
      googleId.initialize({ client_id: clientId, callback: handleCredential })
      // 목업 .google-btn은 카드 전폭(340px) — GIS width는 고정 px만 지원.
      googleId.renderButton(container, { theme: 'outline', size: 'large', width: 340 })
    },
    [handleCredential],
  )

  return { renderGoogleButton, error }
}
