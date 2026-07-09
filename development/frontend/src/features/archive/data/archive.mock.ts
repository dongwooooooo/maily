/*
 * Sample data for the 07 storage ("보관함") screen.
 * Copy mirrors design/boards/v1/current/07-storage.html exactly.
 */

import type { AccountKind } from '@/features/briefing/data/briefing.mock'

export interface TimelineItem {
  id: string
  accountKind: AccountKind
  title: string
  state: string
}

export interface TimelineGroup {
  id: string
  heading: string
  meta: string
  items: TimelineItem[]
}

export const upcomingGroups: TimelineGroup[] = [
  {
    id: 'today',
    heading: '오늘',
    meta: '2',
    items: [
      { id: 'meeting-schedule', accountKind: 'work', title: '미팅 일정 조율', state: '17:00 재알림' },
      { id: 'alumni-fee', accountKind: 'personal', title: '동창회 회비 안내', state: '20:00 재알림' },
    ],
  },
  {
    id: 'tomorrow',
    heading: '내일',
    meta: '1',
    items: [
      { id: 'invoice-2024-118', accountKind: 'work', title: '인보이스 #2024-118', state: '기한 · 7월 7일' },
    ],
  },
  {
    id: 'this-week',
    heading: '이번 주',
    meta: '1',
    items: [
      { id: 'contract-sign', accountKind: 'work', title: '계약서 서명 요청', state: '기한 · 금요일' },
    ],
  },
]

export const labelGroups: TimelineGroup[] = [
  {
    id: 'payments',
    heading: '결제',
    meta: '12개 · 규칙 자동 분류',
    items: [
      { id: 'card-payment-confirm', accountKind: 'personal', title: '카드 결제 확인 안내', state: 'Inbox' },
      { id: 'telecom-june', accountKind: 'personal', title: '6월 통신요금 청구서', state: '확인됨' },
    ],
  },
  {
    id: 'to-read',
    heading: '읽어볼 것',
    meta: '5개',
    items: [
      { id: 'newsletter-highlight', accountKind: 'personal', title: '주간 뉴스레터 하이라이트', state: 'Archived' },
    ],
  },
]

export const addLabelCopy = '+ 새 라벨 만들기'
