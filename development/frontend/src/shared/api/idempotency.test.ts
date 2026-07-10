import { describe, expect, it } from 'vitest'

import { newIdempotencyKey } from './idempotency'

describe('newIdempotencyKey', () => {
  it('returns a uuid v4 string', () => {
    expect(newIdempotencyKey()).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    )
  })

  it('returns a fresh key every call', () => {
    const keys = new Set(Array.from({ length: 50 }, () => newIdempotencyKey()))
    expect(keys.size).toBe(50)
  })
})
