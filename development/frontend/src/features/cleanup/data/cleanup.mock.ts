/*
 * 10 정리 검토 화면의 뷰모델 타입·고정 카피.
 * 제안·적용 로그 데이터는 F7에서 실제 API(cleanup/api.ts + adapters.ts)로
 * 교체되어 삭제됐다.
 */

import type { AccountKind } from '@/features/briefing/types'

export interface Proposal {
  id: string
  title: string
  count: string
  desc: string
  fromState: string
  toState: string
}

export interface ProposalColumn {
  accountKind: AccountKind
  label: string
  proposals: Proposal[]
}

export interface AppliedItem {
  id: string
  text: string
  when: string
  undoAvailable: boolean
}

export const undoAppliedToastCopy = 'Gmail 변경을 되돌렸습니다. 라벨과 아카이브가 원복되었습니다.'
