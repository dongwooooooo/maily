import { describe, expect, it } from 'vitest'
import { computeHasUrgentItems, hasUrgentItems, sections } from './briefing.mock'

describe('computeHasUrgentItems', () => {
  it('is false for an empty section list', () => {
    expect(computeHasUrgentItems([])).toBe(false)
  })

  it('is false when every section has count 0 or undefined', () => {
    expect(
      computeHasUrgentItems([
        { id: 'important', count: 0 },
        { id: 'reply' },
      ]),
    ).toBe(false)
  })

  it('is true when a non-passive section has a positive count', () => {
    expect(computeHasUrgentItems([{ id: 'important', count: 1 }])).toBe(true)
  })

  it('ignores 정리됨(organized) count even when positive', () => {
    expect(computeHasUrgentItems([{ id: 'organized', count: 18 }])).toBe(false)
  })

  it('ignores 완료(done) count even when positive', () => {
    expect(computeHasUrgentItems([{ id: 'done', count: 2 }])).toBe(false)
  })

  it('is true when at least one urgent section has items alongside passive sections', () => {
    expect(
      computeHasUrgentItems([
        { id: 'organized', count: 18 },
        { id: 'done', count: 2 },
        { id: 'approval', count: 1 },
      ]),
    ).toBe(true)
  })

  it('matches the real 오늘 브리핑 mock data (currently has urgent items)', () => {
    expect(hasUrgentItems).toBe(computeHasUrgentItems(sections))
    expect(hasUrgentItems).toBe(true)
  })
})
