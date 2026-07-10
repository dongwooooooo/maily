/**
 * API 클라이언트 — openapi-fetch + 생성 타입(schema.d.ts).
 *
 * - 타입 갱신: 백엔드에서 `python scripts/export_openapi.py` 후 여기서
 *   `pnpm codegen:api` (_integration-contract.md §6)
 * - 인증: Authorization: Bearer 헤더(쿠키 미사용) — fetch credentials 기본값
 *   유지. 401 응답 시 토큰 폐기(만료·위조 — 가드가 /login으로 보낸다)
 * - 에러: openapi-fetch의 { data, error } 결과에서 error를 toApiError로
 *   정규화해 쓴다(errors.ts)
 */

import 'client-only'

import createClient from 'openapi-fetch'

import { authMiddleware } from './middleware'
import type { paths } from './schema'

const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL
if (!configuredBaseUrl && process.env.NODE_ENV === 'production') {
  // 배포 빌드에서 env 누락 시 모든 요청이 조용히 loopback으로 가는 사고 방지.
  console.error('NEXT_PUBLIC_API_BASE_URL 미설정 — 프로덕션 빌드에 필수')
}

export const API_BASE_URL = configuredBaseUrl ?? 'http://127.0.0.1:8000'

export const apiClient = createClient<paths>({ baseUrl: API_BASE_URL })
apiClient.use(authMiddleware)
