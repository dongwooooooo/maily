/*
 * 오늘 브리핑 뷰모델 타입 — 03 keystone 보드의 화면 구조.
 * 데이터는 briefing/api.ts + adapters.ts가 백엔드 응답에서 만들어 채운다
 * (F4 이전에는 briefing.mock.ts의 정적 샘플이 이 타입을 채웠다).
 */

export type AccountKind = 'personal' | 'work' | 'school'

export interface AccountLine {
  kind: AccountKind
  label: string
}

export interface MailCardItem {
  id: string
  /** briefing_item_states용 백엔드 briefing item id. */
  briefingItemId: string
  /** GET /messages/{id}용 메시지 id. */
  messageId: string
  title: string
  sender: string
  summary: string
  /** True only for the summary-off account state (no "요약" tag rendered before the text). */
  noSummaryTag?: boolean
  /** Muted "확인함"/"나중에" state — card reads but not Gmail-read-confirmed. */
  seen?: boolean
  /** State line shown under the summary when `seen` is set. */
  stateMeta?: string
  /** aria-label prefix for the seen state — 현재 어댑터는 '확인함'만 만든다
   * ('나중에'는 remind_later 파생 상태가 API에 실릴 때 추가). */
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

export interface DetailBody {
  account: string
  accountKind: AccountKind
  title: string
  fromLine: string
  summary: string
  paragraphs: string[]
  gmailUrl: string
}
