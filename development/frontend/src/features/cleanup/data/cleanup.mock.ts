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

export const proposalColumns: ProposalColumn[] = [
  {
    accountKind: 'personal',
    label: '개인 계정',
    proposals: [
      {
        id: 'newsletter-cleanup',
        title: '매일경제 뉴스레터 정리',
        count: '14통',
        desc: 'Newsletter 라벨을 적용하고 아카이브합니다.',
        fromState: 'Inbox',
        toState: 'Archived · Label: Newsletter',
      },
      {
        id: 'newsletter-rule',
        title: '규칙 제안: 매일경제 뉴스레터 자동 정리',
        count: '최근 3회 승인',
        desc: '같은 정리를 최근 2주간 3번 승인했습니다. 다음부터는 승인 없이 자동으로 적용할까요?',
        fromState: '지금은 변경 없음',
        toState: '승인 시 자동 정리 규칙 생성 · 활동 로그와 되돌리기 제공',
      },
    ],
  },
  {
    accountKind: 'work',
    label: '업무 계정',
    proposals: [
      {
        id: 'github-cleanup',
        title: 'GitHub 알림 정리',
        count: '12통',
        desc: 'GitHub 라벨을 적용합니다. 아카이브는 하지 않습니다.',
        fromState: 'Inbox',
        toState: 'Inbox · Label: GitHub',
      },
    ],
  },
]

export interface AppliedItem {
  id: string
  text: string
  when: string
}

export const appliedToday: AppliedItem[] = [
  {
    id: 'newsletter-applied',
    text: '뉴스레터 18통에 Newsletter 라벨을 적용하고 아카이브했습니다.',
    when: '08:12 · 개인 계정',
  },
]

export const undoAppliedToastCopy = 'Gmail 변경을 되돌렸습니다. 라벨과 아카이브가 원복되었습니다.'
