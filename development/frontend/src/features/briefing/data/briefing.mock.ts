/*
 * Sample briefing data for the 03 keystone screen.
 * Copy mirrors design/boards/03-keystone-editorial.html exactly.
 * Sample email fields (subjects, summaries, senders) are fake-but-realistic
 * per CLAUDE.md — no lorem ipsum, UI labels are the board's fixed copy.
 */

export type AccountKind = 'personal' | 'work' | 'school'

export interface AccountLine {
  kind: AccountKind
  label: string
}

export interface MailCardItem {
  id: string
  title: string
  sender: string
  summary: string
  /** True only for the summary-off account state (no "요약" tag rendered before the text). */
  noSummaryTag?: boolean
  /** Muted "확인함"/"나중에" state — card reads but not Gmail-read-confirmed. */
  seen?: boolean
  /** State line shown under the summary when `seen` is set, e.g. "확인함 · 서비스에서 열람 · ...". */
  stateMeta?: string
  /** aria-label prefix for the seen state, e.g. '확인함' or '나중에'. */
  seenLabel?: string
}

export interface CompactItem {
  id: string
  title: string
  meta: string
  /** Prefixes `meta` with a success checkmark (e.g. "✓ Gmail에서 읽음"). */
  metaOk?: boolean
}

/** A run of cards under one account line inside a section. */
export interface CardGroup {
  account: AccountLine
  cards: MailCardItem[]
}

/** A run of compact rows under one account line inside a section. */
export interface CompactGroup {
  account: AccountLine
  items: CompactItem[]
}

export interface Section {
  id: string
  heading: string
  count?: number
  cardGroups?: CardGroup[]
  compactGroups?: CompactGroup[]
  showAddSection?: boolean
}

export type NavKey = 'briefing' | 'storage' | 'cleanup' | 'log' | 'settings'

export interface NavItem {
  key: NavKey
  label: string
  href: string
  count?: number
}

export interface SubNavItem {
  label: string
  target: string
  count?: number
  current?: boolean
}

export interface DetailBody {
  account: string
  accountKind: AccountKind
  title: string
  fromLine: string
  summary: string
  paragraphs: string[]
}

export const primaryNav: NavItem[] = [
  { key: 'briefing', label: '오늘 브리핑', href: '/', count: 8 },
  { key: 'storage', label: '보관함', href: '/storage' },
  { key: 'cleanup', label: '정리 검토', href: '/cleanup-review', count: 3 },
  { key: 'log', label: '활동 로그', href: '#activity-log' },
  { key: 'settings', label: '설정', href: '/settings' },
]

export const subNav: SubNavItem[] = [
  { label: '새 중요 항목', target: '#section-important', count: 4, current: true },
  { label: '답장 필요', target: '#section-reply', count: 1 },
  { label: '나중에 봐도 됨', target: '#section-later', count: 1 },
  { label: '정리됨', target: '#section-organized' },
  { label: '승인 필요', target: '#section-approval', count: 1 },
]

export const userName = 'dongwoo'

export const sections: Section[] = [
  {
    id: 'important',
    heading: '새 중요 항목',
    count: 4,
    cardGroups: [
      {
        account: { kind: 'work', label: '업무 계정' },
        cards: [
          {
            id: 'pr-review',
            title: 'PR 리뷰 요청',
            sender: '김지현 · 오늘 09:12',
            summary: '금요일까지 결제 플로우 PR 리뷰를 요청합니다.',
          },
          {
            id: 'invoice',
            title: '인보이스 #2024-118',
            sender: '외주사 · 어제 18:44',
            summary: '6월분 인보이스입니다. 금액 확인 부탁드립니다.',
          },
          {
            id: 'contract',
            title: '계약서 서명 요청',
            sender: '리걸팀 · 어제 15:02',
            summary: '위탁 계약서 전자서명을 이번 주 내 완료해 주세요.',
          },
        ],
      },
      {
        account: { kind: 'personal', label: '개인 계정' },
        cards: [
          {
            id: 'card-payment',
            title: '카드 결제 확인 안내',
            sender: '현대카드 · 오늘 07:55',
            summary: '7월 2일 45,000원 정기 결제가 승인되었습니다.',
            seen: true,
            stateMeta: '확인함 · 서비스에서 열람 · Gmail 읽음 상태는 변경하지 않았습니다',
            seenLabel: '확인함',
          },
        ],
      },
    ],
  },
  {
    id: 'reply',
    heading: '답장 필요',
    count: 1,
    cardGroups: [
      {
        account: { kind: 'work', label: '업무 계정' },
        cards: [
          {
            id: 'meeting',
            title: '미팅 일정 조율',
            sender: '박서준 · 어제 19:20',
            summary: '다음 주 화/수 중 킥오프 미팅 가능 시간을 요청합니다.',
            seen: true,
            stateMeta: '읽음 확정 없음 · 오늘 17:00에 다시 알림',
            seenLabel: '나중에',
          },
        ],
      },
    ],
  },
  {
    id: 'done',
    heading: '완료',
    count: 2,
    compactGroups: [
      {
        account: { kind: 'work', label: '업무 계정' },
        items: [{ id: 'weekly-report', title: '주간 리포트 제출 확인', meta: 'Gmail에서 읽음', metaOk: true }],
      },
      {
        account: { kind: 'personal', label: '개인 계정' },
        items: [{ id: 'card-statement-june', title: '6월 카드 명세서 확인', meta: '완료 · 오늘 08:40' }],
      },
    ],
  },
  {
    id: 'later',
    heading: '나중에 봐도 됨',
    count: 1,
    cardGroups: [
      {
        account: { kind: 'school', label: 'school@gmail.com' },
        cards: [
          {
            id: 'notice',
            title: '7월 학사 일반 공지',
            sender: '학사지원팀 · 어제 17:30',
            summary: '요약이 꺼진 계정입니다. 필요하면 Gmail에서 원문을 확인합니다.',
            noSummaryTag: true,
          },
        ],
      },
    ],
  },
  {
    id: 'organized',
    heading: '정리됨',
    compactGroups: [
      {
        account: { kind: 'personal', label: '개인 계정' },
        items: [{ id: 'newsletter', title: '뉴스레터 묶음', meta: '18개' }],
      },
      {
        account: { kind: 'work', label: '업무 계정' },
        items: [{ id: 'github', title: 'GitHub 알림 묶음', meta: '12개' }],
      },
    ],
  },
  {
    id: 'approval',
    heading: '승인 필요',
    count: 1,
    compactGroups: [
      {
        account: { kind: 'work', label: '업무 계정' },
        items: [{ id: 'label-proposal', title: '새 라벨 제안: 채용', meta: '6개' }],
      },
    ],
  },
]

const PASSIVE_SECTION_IDS = ['organized', 'done']

/** True when any urgent-derived section (excludes 정리됨/완료, which are already resolved) has items. */
export const hasUrgentItems = sections.some(
  (section) => !PASSIVE_SECTION_IDS.includes(section.id) && (section.count ?? 0) > 0,
)

export interface DigestItem {
  value: string
  label: string
  warn?: boolean
}

export const emptyBriefingCopy = {
  heading: '오늘 급하게 확인할 메일은 없습니다',
  lede: '새 중요한 메일은 이곳에 표시되거나 알림으로 알려드립니다.',
}

export const emptyDigest: DigestItem[] = [
  { value: '18건', label: '오늘 정리됨' },
  { value: '09:24', label: '최근 동기화' },
  { value: '12:00', label: '다음 확인 예정' },
  { value: '3개', label: '연결 계정 · 권한 필요 1', warn: true },
]

export interface EmptyLink {
  label: string
  href: string
}

export const emptyLinks: EmptyLink[] = [
  { label: '보관함 보기', href: '/storage' },
  { label: '알림 설정 확인', href: '/settings' },
]

export const myZoneLabel = '내 섹션'

export const mySections: Section[] = [
  {
    id: 'payments',
    heading: '결제',
    compactGroups: [
      {
        account: { kind: 'personal', label: '개인 계정' },
        items: [{ id: 'telecom', title: '6월 통신요금 청구서', meta: '확인됨' }],
      },
    ],
    showAddSection: true,
  },
]

export const detail: DetailBody = {
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
}

export const toastCopy = {
  message: 'Gmail에서도 읽음 처리했습니다.',
  undo: '되돌리기',
  close: '닫기',
}
