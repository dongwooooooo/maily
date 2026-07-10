/*
 * Sample data for the 07 storage ("보관함") screen.
 * Copy mirrors design/boards/v1/current/07-storage.html exactly.
 */

import type { AccountKind, DetailBody } from '@/features/briefing/types'

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
      {
        id: 'meeting-schedule',
        accountKind: 'work',
        title: '미팅 일정 조율',
        state: '17:00 재알림',
      },
      {
        id: 'alumni-fee',
        accountKind: 'personal',
        title: '동창회 회비 안내',
        state: '20:00 재알림',
      },
    ],
  },
  {
    id: 'tomorrow',
    heading: '내일',
    meta: '1',
    items: [
      {
        id: 'invoice-2024-118',
        accountKind: 'work',
        title: '인보이스 #2024-118',
        state: '기한 · 7월 7일',
      },
    ],
  },
  {
    id: 'this-week',
    heading: '이번 주',
    meta: '1',
    items: [
      {
        id: 'contract-sign',
        accountKind: 'work',
        title: '계약서 서명 요청',
        state: '기한 · 금요일',
      },
    ],
  },
]

export const labelGroups: TimelineGroup[] = [
  {
    id: 'payments',
    heading: '결제',
    meta: '12개 · 규칙 자동 분류',
    items: [
      {
        id: 'card-payment-confirm',
        accountKind: 'personal',
        title: '카드 결제 확인 안내',
        state: 'Inbox',
      },
      {
        id: 'telecom-june',
        accountKind: 'personal',
        title: '6월 통신요금 청구서',
        state: '확인됨',
      },
    ],
  },
  {
    id: 'to-read',
    heading: '읽어볼 것',
    meta: '5개',
    items: [
      {
        id: 'newsletter-highlight',
        accountKind: 'personal',
        title: '주간 뉴스레터 하이라이트',
        state: 'Archived',
      },
    ],
  },
]

export const addLabelCopy = '+ 새 라벨 만들기'

/** 07 storage 상세 패널 정적 샘플 — F5(보관함 API 연결)에서 실데이터로 교체. */
export const storageDetail: DetailBody = {
  account: '업무 계정',
  accountKind: 'work',
  title: 'PR 리뷰 요청',
  fromLine: '김지현 <jihyun@company.com> · 오늘 09:12',
  summary: '금요일까지 결제 플로우 PR 리뷰를 요청합니다. 관련 이슈 482번 링크가 포함되어 있습니다.',
  paragraphs: [
    '안녕하세요. 금요일 배포 전에 결제 플로우 PR을 한 번 더 봐주면 좋겠습니다.',
    '특히 쿠폰 적용 후 총액 계산과 실패 케이스 메시지를 확인해 주세요. 리뷰가 가능하면 오늘 오후까지 코멘트를 남겨주세요.',
    '급한 수정이 있으면 내일 오전 배포 전에 반영하겠습니다.',
  ],
  gmailUrl: 'https://mail.google.com/',
}
