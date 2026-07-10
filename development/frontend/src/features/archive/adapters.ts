/*
 * 보관함(07 storage) 응답 → 타임라인 뷰모델 순수 변환.
 *
 * - upcoming 항목(UpcomingReminderEntry)에는 제목이 없어(message_id만)
 *   호출부가 메시지 상세를 조회해 titles 맵으로 넘긴다.
 * - 라벨 탭은 라벨 목록만 실데이터 — 라벨별 메시지 목록 API가 아직 없어
 *   items는 비워 둔다(백엔드 추가 시 여기서 채움).
 * - 계정 kind는 백엔드에 없어 일괄 'work' (briefing adapters와 동일 갭).
 */

import type { ServiceLabel, UpcomingReminderEntry, UpcomingStorage } from './api'
import type { TimelineGroup, TimelineItem } from './data/archive.mock'

const TITLE_FALLBACK = '[미확정: 제목 없는 메일 표시 문구]'

// 보드(07-storage)의 '기한 · 7월 7일' 레인은 마감(기한) 개념인데, 백엔드
// UpcomingStorage는 재알림(reminder)만 실어 준다 — 기한 필드가 API에 생기기
// 전까지 전 항목을 '재알림' 표기로 렌더한다. 오늘 버킷은 보드대로 시간만.
function formatRemindAt(remindAt: string, bucket: 'today' | 'later'): string {
  const date = new Date(remindAt)
  if (Number.isNaN(date.getTime())) return ''
  const formatted = new Intl.DateTimeFormat(
    'ko-KR',
    bucket === 'today'
      ? { hour: '2-digit', minute: '2-digit', hour12: false }
      : { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false },
  ).format(date)
  return `${formatted} 재알림`
}

function toTimelineItems(
  entries: UpcomingReminderEntry[],
  titles: Map<string, string>,
  bucket: 'today' | 'later',
): TimelineItem[] {
  return entries.map((entry) => ({
    id: entry.reminder_id,
    accountKind: 'work',
    title: titles.get(entry.message_id) ?? TITLE_FALLBACK,
    state: formatRemindAt(entry.remind_at, bucket),
    messageId: entry.message_id,
  }))
}

export function toUpcomingGroups(
  upcoming: UpcomingStorage,
  titles: Map<string, string>,
): TimelineGroup[] {
  const buckets: {
    id: string
    heading: string
    entries: UpcomingReminderEntry[]
    bucket: 'today' | 'later'
  }[] = [
    { id: 'today', heading: '오늘', entries: upcoming.today, bucket: 'today' },
    { id: 'tomorrow', heading: '내일', entries: upcoming.tomorrow, bucket: 'later' },
    { id: 'this-week', heading: '이번 주', entries: upcoming.this_week, bucket: 'later' },
  ]
  return buckets.map(({ id, heading, entries, bucket }) => ({
    id,
    heading,
    meta: String(entries.length),
    items: toTimelineItems(entries, titles, bucket),
  }))
}

export function toLabelGroups(labels: ServiceLabel[]): TimelineGroup[] {
  return labels
    .filter((label) => !label.hidden)
    .map((label) => ({
      id: label.id,
      heading: label.name,
      meta: '',
      items: [],
    }))
}
