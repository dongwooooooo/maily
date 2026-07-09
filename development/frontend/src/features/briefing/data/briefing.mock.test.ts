import { describe, expect, it } from 'vitest'
import { computeHasUrgentItems, hasUrgentItems, sections } from './briefing.mock'

describe('computeHasUrgentItems', () => {
  it('섹션 목록이 비어있으면 false다', () => {
    expect(computeHasUrgentItems([])).toBe(false)
  })

  it('모든 섹션의 count가 0이거나 없으면 false다', () => {
    expect(
      computeHasUrgentItems([
        { id: 'important', count: 0 },
        { id: 'reply' },
      ]),
    ).toBe(false)
  })

  it('정리됨/완료가 아닌 섹션에 count가 있으면 true다', () => {
    expect(computeHasUrgentItems([{ id: 'important', count: 1 }])).toBe(true)
  })

  it('정리됨(organized) count는 양수여도 무시한다', () => {
    expect(computeHasUrgentItems([{ id: 'organized', count: 18 }])).toBe(false)
  })

  it('완료(done) count는 양수여도 무시한다', () => {
    expect(computeHasUrgentItems([{ id: 'done', count: 2 }])).toBe(false)
  })

  it('정리됨/완료 섞여있어도 긴급 섹션에 항목 있으면 true다', () => {
    expect(
      computeHasUrgentItems([
        { id: 'organized', count: 18 },
        { id: 'done', count: 2 },
        { id: 'approval', count: 1 },
      ]),
    ).toBe(true)
  })

  it('실제 오늘 브리핑 mock 데이터와 결과가 일치한다 (현재 긴급 항목 있음)', () => {
    expect(hasUrgentItems).toBe(computeHasUrgentItems(sections))
    expect(hasUrgentItems).toBe(true)
  })
})
