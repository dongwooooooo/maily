/**
 * 에러 응답 정규화 — 백엔드 봉투 {"error": {code, message, request_id, details?}}
 * 를 ApiError로 변환한다 (_integration-contract.md §6).
 * FastAPI 기본 {"detail": [...]} 형식은 백엔드가 밖으로 내보내지 않지만,
 * 프록시·게이트웨이 등 중간 계층 응답에 대비해 방어적으로 처리한다.
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: unknown

  constructor(input: {
    status: number
    code: string
    message: string
    requestId: string | null
    details?: unknown
  }) {
    super(input.message)
    this.name = 'ApiError'
    this.status = input.status
    this.code = input.code
    this.requestId = input.requestId
    this.details = input.details ?? null
  }
}

interface ErrorEnvelope {
  error: {
    code: string
    message: string
    request_id?: string | null
    details?: unknown
  }
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== 'object' || body === null || !('error' in body)) return false
  const error = (body as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  )
}

export function toApiError(status: number, body: unknown): ApiError {
  if (isErrorEnvelope(body)) {
    return new ApiError({
      status,
      code: body.error.code,
      message: body.error.message,
      requestId: body.error.request_id ?? null,
      details: body.error.details,
    })
  }

  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    return new ApiError({
      status,
      code: Array.isArray(detail) ? 'validation_error' : 'unknown_error',
      message: typeof detail === 'string' ? detail : 'Request failed',
      requestId: null,
      details: detail,
    })
  }

  return new ApiError({
    status,
    code: 'unknown_error',
    message: typeof body === 'string' && body ? body : 'Request failed',
    requestId: null,
  })
}
