/**
 * openapi-fetch 미들웨어 — client.ts에서 배선한다.
 * client.ts는 `import 'client-only'` 가드 때문에 vitest(node)에서 import할 수
 * 없으므로, 테스트 가능한 로직은 이 파일에 둔다.
 */

import type { Middleware } from 'openapi-fetch'

import { clearToken, getToken } from './token'

export const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = getToken()
    if (token) {
      request.headers.set('Authorization', `Bearer ${token}`)
    }
    return request
  },
  onResponse({ response }) {
    // 401 = 세션 만료·무효 — 토큰을 폐기해 가드가 /login으로 보내게 한다.
    if (response.status === 401) {
      clearToken()
    }
    return response
  },
}
