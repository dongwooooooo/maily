'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'

import { apiClient } from '@/shared/api/client'

import { useSessionStore } from './store'

/** 미로그인 가드 — 전 화면을 감싼다(root layout).
 *
 * /login 밖: 토큰 부재 → /login. 토큰 존재 → GET /auth/session 검증,
 * 401이면 middleware가 토큰을 이미 폐기했으므로 /login으로 보낸다.
 * 검증 완료 전에는 화면을 그리지 않는다(깜빡임 방지).
 * /login: 유효 토큰이면 이미 로그인 상태 — 오늘 브리핑(/)으로 보낸다. */
export default function SessionGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const token = useSessionStore((state) => state.token)
  const clearSession = useSessionStore((state) => state.clearSession)
  const [verified, setVerified] = useState(false)

  const isLoginRoute = pathname === '/login'

  useEffect(() => {
    if (!token) {
      if (!isLoginRoute) router.replace('/login')
      return
    }
    let cancelled = false
    apiClient.GET('/auth/session').then(({ error }) => {
      if (cancelled) return
      if (error) {
        clearSession()
        if (!isLoginRoute) router.replace('/login')
        return
      }
      if (isLoginRoute) {
        router.replace('/')
        return
      }
      setVerified(true)
    })
    return () => {
      cancelled = true
    }
  }, [isLoginRoute, token, router, clearSession])

  if (isLoginRoute) return <>{children}</>
  if (!verified) return null
  return <>{children}</>
}
