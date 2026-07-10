/*
 * 백엔드 응답 → 03 keystone 뷰모델 순수 변환.
 *
 * 섹션 분류는 [미정]이라(백엔드 briefing_items.section — db-schema.md
 * "열린 결정") 현재 전 카드가 fake_section 단일 값으로 온다. 값 집합이
 * 확정되면 SECTION_HEADINGS만 갱신한다. 미지의 값은 내부 문자열을
 * 노출하지 않고 [미확정] 제목으로 묶는다.
 *
 * 계정 kind(work/personal/school 아바타 구분)는 백엔드에 아직 없어
 * 일괄 'work'로 둔다 — 계정 메타 확장 시 여기서 매핑.
 *
 * AccountBriefingGroup의 status/syncing(계정 상태·동기화 중 표시)은 F4에서
 * 의도적으로 미소비 — 계정 상태 표시는 설정 화면(F6) 연결 때 목록 상단
 * 배지와 함께 결정한다. 그 전까지 비정상 계정도 동일하게 렌더된다.
 */

import type { CompactGroup, DetailBody, MailCardItem, Section } from './types'
import type { AccountBriefingGroup, BriefingCard, MessageDetailResponse } from './api'

const SECTION_HEADINGS: Record<string, string> = {
  fake_section: '새 중요 항목',
}

const UNKNOWN_SECTION_HEADING = '[미확정: 섹션 이름]'
const DONE_SECTION_HEADING = '완료'

// 03 keystone 보드 확정 카피 — 확인함 상태 라인.
const SEEN_STATE_META = '확인함 · 서비스에서 열람 · Gmail 읽음 상태는 변경하지 않았습니다'

export function formatReceivedAt(receivedAt: string | null): string {
  if (!receivedAt) return ''
  const date = new Date(receivedAt)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function toMailCard(item: BriefingCard): MailCardItem {
  const received = formatReceivedAt(item.received_at)
  return {
    id: item.id,
    briefingItemId: item.id,
    messageId: item.message_id,
    title: item.subject ?? '[미확정: 제목 없는 메일 표시 문구]',
    sender: [item.sender, received].filter(Boolean).join(' · '),
    summary: item.summary_text ?? item.snippet ?? '',
    noSummaryTag: item.summary_text == null,
    ...(item.seen
      ? { seen: true, seenLabel: '확인함', stateMeta: SEEN_STATE_META }
      : {}),
  }
}

export function toSections(groups: AccountBriefingGroup[]): Section[] {
  const cardSections = new Map<string, Section>()
  const doneGroups: CompactGroup[] = []

  for (const group of groups) {
    const account = { kind: 'work' as const, label: group.gmail_address }
    const activeCards = group.items.filter((item) => !item.done)
    const doneCards = group.items.filter((item) => item.done)

    for (const item of activeCards) {
      const heading = SECTION_HEADINGS[item.section] ?? UNKNOWN_SECTION_HEADING
      let section = cardSections.get(heading)
      if (!section) {
        section = { id: item.section, heading, count: 0, cardGroups: [] }
        cardSections.set(heading, section)
      }
      let cardGroup = section.cardGroups!.find(
        (candidate) => candidate.account.label === account.label,
      )
      if (!cardGroup) {
        cardGroup = { account, cards: [] }
        section.cardGroups!.push(cardGroup)
      }
      cardGroup.cards.push(toMailCard(item))
      section.count = (section.count ?? 0) + 1
    }

    if (doneCards.length > 0) {
      doneGroups.push({
        account,
        items: doneCards.map((item) => ({
          id: item.id,
          title: item.subject ?? '[미확정: 제목 없는 메일 표시 문구]',
          meta: DONE_SECTION_HEADING,
        })),
      })
    }
  }

  const sections = [...cardSections.values()]
  if (doneGroups.length > 0) {
    sections.push({
      id: 'done',
      heading: DONE_SECTION_HEADING,
      count: doneGroups.reduce((total, group) => total + group.items.length, 0),
      compactGroups: doneGroups,
    })
  }
  return sections
}

export const PASSIVE_SECTION_IDS = ['organized', 'done']

/** True when any urgent-derived section (excludes 정리됨/완료, which are already resolved) has items. */
export function computeHasUrgentItems(sectionList: Pick<Section, 'id' | 'count'>[]): boolean {
  return sectionList.some(
    (section) => !PASSIVE_SECTION_IDS.includes(section.id) && (section.count ?? 0) > 0,
  )
}

export function toDetailBody(detail: MessageDetailResponse, accountLabel: string): DetailBody {
  const received = formatReceivedAt(detail.received_at)
  return {
    account: accountLabel,
    accountKind: 'work',
    title: detail.subject ?? '[미확정: 제목 없는 메일 표시 문구]',
    fromLine: [detail.sender, received].filter(Boolean).join(' · '),
    summary: detail.summary_text ?? '',
    paragraphs: detail.excerpt_text ? [detail.excerpt_text] : [],
    gmailUrl: detail.gmail_url,
  }
}
