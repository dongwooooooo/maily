/*
 * 정리 검토(10 cleanup) 응답 → 제안 칼럼 뷰모델 순수 변환.
 *
 * - 제안 카드 제목·계정 라벨은 CleanupProposal에 없어(message_id만)
 *   호출부가 메시지 상세로 만든 lookup 맵을 넘긴다.
 * - '규칙 제안' 카드(보드의 두 번째 카드 유형)는 rules API(F8) 소관 —
 *   이 화면은 cleanup 제안만 다룬다.
 * - 계정 kind는 백엔드에 없어 일괄 'work' (다른 화면과 동일 갭).
 */

import type { AppliedItem, Proposal, ProposalColumn } from './data/cleanup.mock'
import type { ActivityLogEntry, CleanupProposal } from './api'

const TITLE_FALLBACK = '[미확정: 제목 없는 메일 표시 문구]'
const ACCOUNT_FALLBACK = '[미확정: 계정 미상 표시 문구]'

interface MessageLookup {
  subject: string
  accountLabel: string
}

// 10 보드 확정 어휘 — before/after 상태 줄.
// 스키마상 before/after는 임의 JSON(Record<string, unknown>) — 형태를 신뢰하지
// 않고 방어한다. 제안 1건의 불량 데이터가 전체 목록 렌더를 깨면 안 된다.
function stateLine(state: unknown): string {
  if (typeof state !== 'object' || state === null) return ''
  const value = state as { is_archived?: unknown; labels?: unknown }
  const parts = [value.is_archived === true ? 'Archived' : 'Inbox']
  const labels = (Array.isArray(value.labels) ? value.labels : [])
    .filter((label): label is string => typeof label === 'string')
    .filter((label) => !['INBOX', 'UNREAD'].includes(label))
  if (labels.length > 0) parts.push(`Label: ${labels.join(', ')}`)
  return parts.join(' · ')
}

const ACTION_DESCRIPTIONS: Record<string, string> = {
  archive: '아카이브합니다.',
  mark_read: '읽음 처리합니다.',
  read_and_archive: '읽음 처리하고 아카이브합니다.',
}

function toProposal(item: CleanupProposal, lookup: Map<string, MessageLookup>): Proposal {
  return {
    id: item.id,
    title: lookup.get(item.message_id)?.subject ?? TITLE_FALLBACK,
    // 보드의 통수 배지('14통')는 CleanupProposal에 대응 필드가 없어 공란 —
    // 백엔드에 메시지 수 필드가 생기면 채운다.
    count: '',
    desc: ACTION_DESCRIPTIONS[item.proposed_action] ?? '[미확정: 정리 동작 설명 문구]',
    fromState: stateLine(item.before_state),
    toState: stateLine(item.after_state),
  }
}

export function toProposalColumns(
  proposals: CleanupProposal[],
  lookup: Map<string, MessageLookup>,
): ProposalColumn[] {
  const columns = new Map<string, ProposalColumn>()
  for (const item of proposals) {
    if (item.status !== 'pending') continue
    const label = lookup.get(item.message_id)?.accountLabel ?? ACCOUNT_FALLBACK
    let column = columns.get(label)
    if (!column) {
      column = { accountKind: 'work', label, proposals: [] }
      columns.set(label, column)
    }
    column.proposals.push(toProposal(item, lookup))
  }
  return [...columns.values()]
}

function formatOccurredAt(occurredAt: string): string {
  const date = new Date(occurredAt)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

// 보드의 '08:12 · 개인 계정' 중 계정 라벨은 ActivityLogEntry에 계정 필드가
// 없어 시각만 표기한다 — 백엔드 필드 추가 시 보강.
export function toAppliedItems(entries: ActivityLogEntry[]): AppliedItem[] {
  return entries
    .filter((entry) => entry.undone_at == null)
    .map((entry) => ({
      id: entry.id,
      text: entry.action_summary,
      when: formatOccurredAt(entry.occurred_at),
      undoAvailable: entry.undo_available,
    }))
}
