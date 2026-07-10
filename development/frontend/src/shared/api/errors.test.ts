import { describe, expect, it } from 'vitest'

import { ApiError, toApiError } from './errors'

describe('toApiError', () => {
  it('parses the maily error envelope', () => {
    const error = toApiError(409, {
      error: {
        code: 'conflict',
        message: '이미 처리된 요청',
        request_id: 'rid-1',
        details: { command_id: 'abc' },
      },
    })

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(409)
    expect(error.code).toBe('conflict')
    expect(error.message).toBe('이미 처리된 요청')
    expect(error.requestId).toBe('rid-1')
    expect(error.details).toEqual({ command_id: 'abc' })
  })

  it('defaults request_id to null when the envelope omits it', () => {
    const error = toApiError(404, {
      error: { code: 'not_found', message: 'gmail source not found' },
    })

    expect(error.code).toBe('not_found')
    expect(error.requestId).toBeNull()
  })

  it('falls back on the fastapi default detail array', () => {
    const error = toApiError(422, {
      detail: [{ loc: ['body', 'id_token'], msg: 'Field required', type: 'missing' }],
    })

    expect(error.code).toBe('validation_error')
    expect(error.status).toBe(422)
    expect(Array.isArray(error.details)).toBe(true)
  })

  it('handles a non-json or unknown body without throwing', () => {
    const error = toApiError(502, 'Bad Gateway')

    expect(error.code).toBe('unknown_error')
    expect(error.status).toBe(502)
    expect(error.requestId).toBeNull()
  })
})
