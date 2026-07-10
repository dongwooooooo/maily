import { describe, expect, it } from 'vitest'

import { ApiError } from './errors'
import { BACKEND_ERROR_CODES, errorMessageFor } from './errorMessages'

describe('errorMessageFor', () => {
  it('covers every backend error code', () => {
    // app/core/errors.py의 코드 7종 — 백엔드에 코드가 추가되면 이 배열과
    // 매핑을 함께 갱신해야 한다.
    expect(BACKEND_ERROR_CODES).toEqual([
      'internal_error',
      'not_found',
      'conflict',
      'validation_error',
      'unauthorized',
      'forbidden',
      'external_service_error',
    ])
    for (const code of BACKEND_ERROR_CODES) {
      const message = errorMessageFor(
        new ApiError({ status: 500, code, message: 'x', requestId: null }),
      )
      expect(message, code).toBeTruthy()
    }
  })

  it('falls back for unknown codes without leaking the raw code', () => {
    const message = errorMessageFor(
      new ApiError({ status: 502, code: 'unknown_error', message: 'x', requestId: null }),
    )
    // 에러 코드 원문이 그대로 리턴되면 "코드 비노출" 원칙 위반 — 리터럴로 고정.
    expect(message).toBe('[미확정: 알 수 없는 오류 안내 문구]')
  })
})
