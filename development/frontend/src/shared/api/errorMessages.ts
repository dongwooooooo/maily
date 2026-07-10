/**
 * 에러 코드 → 사용자 노출 한국어 카피.
 *
 * 코드 목록의 단일 근거는 백엔드 app/core/errors.py. 카피 즉흥 생성 금지
 * 규칙(CLAUDE.md)에 따라 확정 문구가 나오기 전에는 전부 [미확정] placeholder다
 * — 확정되면 design/copy-principles.md에서 옮겨 채운다.
 * 에러 코드 원문은 사용자에게 노출하지 않는다(개발자용 — 콘솔·로깅 전용).
 */

import type { ApiError } from './errors'

export const BACKEND_ERROR_CODES = [
  'internal_error',
  'not_found',
  'conflict',
  'validation_error',
  'unauthorized',
  'forbidden',
  'external_service_error',
] as const

type BackendErrorCode = (typeof BACKEND_ERROR_CODES)[number]

const MESSAGES: Record<BackendErrorCode, string> = {
  internal_error: '[미확정: 서버 오류 일반 안내 문구]',
  not_found: '[미확정: 대상 없음 안내 문구]',
  conflict: '[미확정: 이미 처리된 요청 안내 문구]',
  validation_error: '[미확정: 입력값 오류 안내 문구]',
  unauthorized: '[미확정: 로그인 필요 안내 문구]',
  forbidden: '[미확정: 권한 없음 안내 문구]',
  external_service_error: '[미확정: Gmail 연동 오류 안내 문구]',
}

const FALLBACK_MESSAGE = '[미확정: 알 수 없는 오류 안내 문구]'

function isBackendErrorCode(code: string): code is BackendErrorCode {
  return (BACKEND_ERROR_CODES as readonly string[]).includes(code)
}

export function errorMessageFor(error: ApiError): string {
  return isBackendErrorCode(error.code) ? MESSAGES[error.code] : FALLBACK_MESSAGE
}
