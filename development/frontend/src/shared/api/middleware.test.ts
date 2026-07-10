import { beforeEach, describe, expect, it } from 'vitest'

import { authMiddleware } from './middleware'
import { getToken, setToken } from './token'

function onRequest(request: Request) {
  return authMiddleware.onRequest!({ request } as Parameters<
    NonNullable<typeof authMiddleware.onRequest>
  >[0])
}

function onResponse(response: Response) {
  return authMiddleware.onResponse!({ response } as Parameters<
    NonNullable<typeof authMiddleware.onResponse>
  >[0])
}

describe('authMiddleware', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('attaches the bearer token when present', async () => {
    setToken('jwt-abc')
    const request = new Request('http://127.0.0.1:8000/briefing/today')

    const result = (await onRequest(request)) as Request

    expect(result.headers.get('Authorization')).toBe('Bearer jwt-abc')
  })

  it('leaves the header off when no token stored', async () => {
    const request = new Request('http://127.0.0.1:8000/briefing/today')

    const result = (await onRequest(request)) as Request

    expect(result.headers.get('Authorization')).toBeNull()
  })

  it('clears the token on a 401 response', async () => {
    setToken('jwt-expired')

    await onResponse(new Response(null, { status: 401 }))

    expect(getToken()).toBeNull()
  })

  it('keeps the token on non-401 responses', async () => {
    setToken('jwt-abc')

    await onResponse(new Response(null, { status: 500 }))

    expect(getToken()).toBe('jwt-abc')
  })
})
