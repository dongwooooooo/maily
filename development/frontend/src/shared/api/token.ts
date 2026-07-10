/**
 * 세션 JWT 저장 — POC 기준 localStorage.
 * XSS 노출 리스크는 POC 범위에서 수용하고, 운영 전환 시 httpOnly 쿠키로
 * 이전한다(Task15 부채 목록). 서버 컴포넌트/SSR에서는 window가 없으므로
 * 항상 null을 반환한다.
 */

const STORAGE_KEY = 'maily.session.token'

// localStorage는 사파리 구버전 프라이빗 모드·쿼터 초과에서 접근 자체가 throw
// 할 수 있다 — 저장 실패는 "미로그인"과 동일하게 조용히 처리한다.
export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, token)
  } catch {
    // no-op — 다음 getToken()이 null을 돌려 가드가 /login으로 보낸다.
  }
}

export function clearToken(): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // no-op
  }
}
