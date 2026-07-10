import { describe, expect, it } from 'vitest'

import type { AccountBriefingGroup, MessageDetailResponse } from './api'
import { computeHasUrgentItems, formatReceivedAt, toDetailBody, toSections } from './adapters'

function card(overrides: Partial<AccountBriefingGroup['items'][number]> = {}) {
  return {
    id: 'item-1',
    connected_account_id: 'acc-1',
    message_id: 'msg-1',
    section: 'fake_section',
    subject: 'PR 리뷰 요청',
    sender: '김지현',
    snippet: '금요일까지 결제 플로우 PR 리뷰를 요청합니다.',
    summary_text: '금요일까지 결제 플로우 PR 리뷰를 요청합니다.',
    importance_band: null,
    received_at: '2026-07-10T09:12:00+09:00',
    seen: false,
    done: false,
    rebuilt_at: '2026-07-10T09:15:00+09:00',
    ...overrides,
  }
}

function group(
  items: AccountBriefingGroup['items'],
  overrides: Partial<AccountBriefingGroup> = {},
): AccountBriefingGroup {
  return {
    connected_account_id: 'acc-1',
    gmail_address: 'work@gmail.com',
    status: 'connected',
    syncing: false,
    items,
    ...overrides,
  }
}

describe('toSections', () => {
  it('maps fake_section cards into the 새 중요 항목 section grouped by account', () => {
    const sections = toSections([group([card()])])

    expect(sections).toHaveLength(1)
    const [section] = sections
    expect(section.heading).toBe('새 중요 항목')
    expect(section.count).toBe(1)
    expect(section.cardGroups).toHaveLength(1)
    expect(section.cardGroups![0].account.label).toBe('work@gmail.com')
    const [mailCard] = section.cardGroups![0].cards
    expect(mailCard.title).toBe('PR 리뷰 요청')
    expect(mailCard.briefingItemId).toBe('item-1')
    expect(mailCard.messageId).toBe('msg-1')
  })

  it('routes done cards into a 완료 compact section', () => {
    const sections = toSections([group([card({ id: 'item-2', done: true })])])

    const doneSection = sections.find((section) => section.heading === '완료')
    expect(doneSection).toBeDefined()
    expect(doneSection!.compactGroups![0].items[0].title).toBe('PR 리뷰 요청')
    // done 카드는 카드 섹션에 중복 표시되지 않는다.
    expect(sections.filter((section) => section.heading === '새 중요 항목')).toHaveLength(0)
  })

  it('marks seen cards with the confirmed 확인함 state line', () => {
    const sections = toSections([group([card({ seen: true })])])

    const [mailCard] = sections[0].cardGroups![0].cards
    expect(mailCard.seen).toBe(true)
    expect(mailCard.seenLabel).toBe('확인함')
    expect(mailCard.stateMeta).toContain('Gmail 읽음 상태는 변경하지 않았습니다')
  })

  it('falls back to a summary-off card when summary_text is null', () => {
    const sections = toSections([group([card({ summary_text: null })])])

    const [mailCard] = sections[0].cardGroups![0].cards
    expect(mailCard.noSummaryTag).toBe(true)
    expect(mailCard.summary).toBe('금요일까지 결제 플로우 PR 리뷰를 요청합니다.')
  })

  it('keeps unknown section values visible without leaking the raw value', () => {
    const sections = toSections([group([card({ section: 'mystery_section' })])])

    expect(sections[0].heading).toBe('[미확정: 섹션 이름]')
  })

  it('keeps accounts separate inside one section', () => {
    const sections = toSections([
      group([card()]),
      group([card({ id: 'item-3', message_id: 'msg-3' })], {
        connected_account_id: 'acc-2',
        gmail_address: 'personal@gmail.com',
      }),
    ])

    expect(sections[0].cardGroups).toHaveLength(2)
    expect(sections[0].count).toBe(2)
  })
})

describe('toDetailBody', () => {
  it('maps message detail to the detail pane view model', () => {
    const detail: MessageDetailResponse = {
      id: 'msg-1',
      connected_account_id: 'acc-1',
      gmail_message_id: 'g-1',
      gmail_thread_id: 't-1',
      gmail_url: 'https://mail.google.com/mail/u/0/#inbox/t-1',
      subject: 'PR 리뷰 요청',
      sender: '김지현 <jihyun@company.com>',
      received_at: '2026-07-10T09:12:00+09:00',
      summary_text: '금요일까지 결제 플로우 PR 리뷰를 요청합니다.',
      excerpt_text: '안녕하세요. 금요일 배포 전에 결제 플로우 PR을 한 번 더 봐주면 좋겠습니다.',
      importance_band: null,
      done: false,
    }

    const body = toDetailBody(detail, 'work@gmail.com')

    expect(body.title).toBe('PR 리뷰 요청')
    expect(body.account).toBe('work@gmail.com')
    expect(body.fromLine).toContain('김지현')
    expect(body.summary).toBe('금요일까지 결제 플로우 PR 리뷰를 요청합니다.')
    expect(body.paragraphs).toHaveLength(1)
    expect(body.gmailUrl).toContain('mail.google.com')
  })
})

describe('computeHasUrgentItems', () => {
  it('섹션 목록이 비어있으면 false다', () => {
    expect(computeHasUrgentItems([])).toBe(false)
  })

  it('모든 섹션의 count가 0이거나 없으면 false다', () => {
    expect(computeHasUrgentItems([{ id: 'important', count: 0 }, { id: 'reply' }])).toBe(false)
  })

  it('정리됨/완료가 아닌 섹션에 count가 있으면 true다', () => {
    expect(computeHasUrgentItems([{ id: 'important', count: 1 }])).toBe(true)
  })

  it('정리됨(organized)/완료(done) count는 양수여도 무시한다', () => {
    expect(
      computeHasUrgentItems([
        { id: 'organized', count: 18 },
        { id: 'done', count: 2 },
      ]),
    ).toBe(false)
  })

  it('완료만 있는 API 응답에서 빈 상태로 판정된다', () => {
    const sections = toSections([group([card({ done: true })])])
    expect(computeHasUrgentItems(sections)).toBe(false)
  })

  it('완료 섹션과 활성 섹션이 섞여 있으면 true다', () => {
    const sections = toSections([group([card(), card({ id: 'item-9', done: true })])])
    expect(computeHasUrgentItems(sections)).toBe(true)
  })
})

describe('formatReceivedAt', () => {
  it('formats an ISO timestamp as HH:MM with date', () => {
    expect(formatReceivedAt('2026-07-10T09:12:00+09:00')).toMatch(/09:12/)
  })

  it('returns an empty string for null', () => {
    expect(formatReceivedAt(null)).toBe('')
  })
})
