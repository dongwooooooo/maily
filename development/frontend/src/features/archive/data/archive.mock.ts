/*
 * 07 storage 화면의 뷰모델 타입·고정 카피.
 * 예정/라벨 목록 데이터는 F5에서 실제 API(archive/api.ts + adapters.ts)로
 * 교체되어 삭제됐다. 상세 패널 정적 샘플(storageDetail)은 F5 후속에서 교체.
 */

import type { AccountKind, DetailBody } from '@/features/briefing/types'

export interface TimelineItem {
  id: string
  accountKind: AccountKind
  title: string
  state: string
  /** 클릭 시 상세를 열 대상 메시지 — 라벨 그룹처럼 대상이 없으면 null. */
  messageId?: string | null
}

export interface TimelineGroup {
  id: string
  heading: string
  meta: string
  items: TimelineItem[]
}

export const addLabelCopy = '+ 새 라벨 만들기'

/** 07 storage 상세 패널 정적 샘플 — F5(보관함 API 연결)에서 실데이터로 교체. */
export const storageDetail: DetailBody = {
  messageId: null,
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
