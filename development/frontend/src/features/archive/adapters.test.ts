import { describe, expect, it } from 'vitest'

import type { ServiceLabel, UpcomingStorage } from './api'
import { toLabelGroups, toUpcomingGroups } from './adapters'

const upcoming: UpcomingStorage = {
  today: [
    { reminder_id: 'r-1', message_id: 'msg-1', remind_at: '2026-07-10T17:00:00+09:00' },
  ],
  tomorrow: [],
  this_week: [
    { reminder_id: 'r-2', message_id: 'msg-2', remind_at: '2026-07-13T09:00:00+09:00' },
  ],
}

describe('toUpcomingGroups', () => {
  it('maps the three fixed timeline groups with counts', () => {
    const groups = toUpcomingGroups(upcoming, new Map([['msg-1', 'PR 리뷰 요청']]))

    expect(groups.map((group) => group.heading)).toEqual(['오늘', '내일', '이번 주'])
    expect(groups[0].meta).toBe('1')
    expect(groups[1].meta).toBe('0')
    expect(groups[0].items[0].title).toBe('PR 리뷰 요청')
    expect(groups[0].items[0].state).toContain('재알림')
  })

  it('falls back to placeholder title when the message lookup is missing', () => {
    const groups = toUpcomingGroups(upcoming, new Map())

    expect(groups[0].items[0].title).toBe('[미확정: 제목 없는 메일 표시 문구]')
  })
})

describe('toLabelGroups', () => {
  it('maps service labels to headings without items (메시지 목록 API 부재)', () => {
    const labels: ServiceLabel[] = [
      {
        id: 'label-1',
        workspace_id: 'ws-1',
        connected_account_id: 'acc-1',
        name: '결제',
        gmail_label_id: null,
        gmail_label_name: null,
        hidden: false,
        order_index: 0,
        updated_at: '2026-07-10T09:00:00+09:00',
      },
    ]

    const groups = toLabelGroups(labels)

    expect(groups).toHaveLength(1)
    expect(groups[0].heading).toBe('결제')
    expect(groups[0].items).toEqual([])
  })

  it('hides hidden labels', () => {
    const labels: ServiceLabel[] = [
      {
        id: 'label-2',
        workspace_id: 'ws-1',
        connected_account_id: 'acc-1',
        name: '숨김 라벨',
        gmail_label_id: null,
        gmail_label_name: null,
        hidden: true,
        order_index: 0,
        updated_at: '2026-07-10T09:00:00+09:00',
      },
    ]

    expect(toLabelGroups(labels)).toEqual([])
  })
})
